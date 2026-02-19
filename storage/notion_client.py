"""
Notion client for managing Leads, Contacts, and Outreach databases.
Uses the official notion-client SDK (notion-client >= 3.0.0).

Notion API version 2025-09-03 stores properties on **data sources** rather
than databases.  Every database has one or more data sources; we resolve the
first data source from each database and use it for all property / page ops.
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from notion_client import Client

logger = logging.getLogger(__name__)


def _hash_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize_notion_id(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return str(raw).replace("-", "").lower().strip()


def _notion_id_with_hyphens(raw: Optional[str]) -> str:
    s = _normalize_notion_id(raw)
    if not s or len(s) != 32:
        return (raw or "").strip()
    return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"


class NotionStorage:
    """CRUD operations for Leads, Contacts, and Outreach databases."""

    def __init__(self):
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise ValueError("NOTION_TOKEN not set in environment")
        self.client = Client(auth=token)

        self.leads_db_id = os.getenv("NOTION_LEADS_DB_ID", "")
        self.contacts_db_id = os.getenv("NOTION_CONTACTS_DB_ID", "")
        self.outreach_db_id = os.getenv("NOTION_OUTREACH_DB_ID", "")

        self._ds_cache: dict[str, str] = {}
        self._schemas_ensured = False

    # ------------------------------------------------------------------
    # Data-source helpers (API 2025-09-03)
    # ------------------------------------------------------------------

    def _resolve_data_source_id(self, database_id: str) -> str:
        """Return the first data_source_id for a database.  Cached."""
        db_key = _normalize_notion_id(database_id)
        if db_key in self._ds_cache:
            return self._ds_cache[db_key]

        db_id = _notion_id_with_hyphens(database_id)
        try:
            db = self.client.request(path=f"databases/{db_id}", method="get")
            ds_list = db.get("data_sources", [])
            if ds_list:
                ds_id = ds_list[0]["id"]
                self._ds_cache[db_key] = ds_id
                return ds_id
        except Exception as exc:
            logger.error("Cannot resolve data_source for database %s: %s", database_id, exc)
        return ""

    def _get_ds_property_names(self, database_id: str) -> set[str]:
        """Return set of property names on the data source for this database."""
        ds_id = self._resolve_data_source_id(database_id)
        if not ds_id:
            return set()
        try:
            ds = self.client.data_sources.retrieve(data_source_id=ds_id)
            return set(ds.get("properties", {}).keys())
        except Exception as exc:
            logger.warning("Could not retrieve data source %s: %s", ds_id, exc)
            return set()

    def _ensure_ds_properties(self, database_id: str, required: dict) -> None:
        """Add missing properties to the data source for a database."""
        ds_id = self._resolve_data_source_id(database_id)
        if not ds_id:
            logger.error("No data source found for database %s; cannot ensure properties.", database_id)
            return

        existing = self._get_ds_property_names(database_id)
        to_add = {k: v for k, v in required.items() if k not in existing}

        if not to_add:
            logger.info("Data source %s: all properties already exist.", ds_id)
            return

        try:
            self.client.data_sources.update(
                data_source_id=ds_id,
                properties=to_add,
            )
            logger.info(
                "Data source %s: created properties: %s",
                ds_id,
                ", ".join(to_add.keys()),
            )
        except Exception as exc:
            logger.error("Failed to update data source %s: %s", ds_id, exc)

    def _query_data_source(self, database_id: str, **kwargs) -> dict:
        """Query the data source for a database (paginated list of pages)."""
        ds_id = self._resolve_data_source_id(database_id)
        if not ds_id:
            return {"results": [], "has_more": False}
        return self.client.data_sources.query(data_source_id=ds_id, **kwargs)

    def _create_page(self, database_id: str, properties: dict) -> dict:
        """Create a page in the data source for a database."""
        ds_id = self._resolve_data_source_id(database_id)
        if not ds_id:
            raise RuntimeError(f"No data source found for database {database_id}")
        return self.client.pages.create(
            parent={"data_source_id": ds_id},
            properties=properties,
        )

    # ------------------------------------------------------------------
    # Schema auto-creation
    # ------------------------------------------------------------------

    def ensure_schemas(self) -> None:
        if self._schemas_ensured:
            return

        if self.leads_db_id:
            self._ensure_ds_properties(self.leads_db_id, {
                "Company Name": {"title": {}},
                "Source Link": {"url": {}},
                "Post Type": {"select": {"options": [
                    {"name": "hiring"}, {"name": "funding"}, {"name": "both"},
                ]}},
                "Role": {"rich_text": {}},
                "Funding Amount": {"rich_text": {}},
                "Platform": {"select": {"options": [
                    {"name": "x.com"}, {"name": "linkedin"},
                    {"name": "techcrunch"}, {"name": "google_news"},
                ]}},
                "Date Found": {"date": {}},
                "Status": {"select": {"options": [
                    {"name": "new"}, {"name": "researching"},
                    {"name": "contacted"}, {"name": "replied"},
                ]}},
                "Fingerprint": {"rich_text": {}},
            })

        if self.contacts_db_id:
            self._ensure_ds_properties(self.contacts_db_id, {
                "Name": {"title": {}},
                "Email": {"email": {}},
                "Role/Title": {"rich_text": {}},
                "Company Name": {"rich_text": {}},
                "Email Confidence": {"select": {"options": [
                    {"name": "high"}, {"name": "medium"}, {"name": "low"},
                ]}},
                "LinkedIn URL": {"url": {}},
            })

        if self.outreach_db_id:
            self._ensure_ds_properties(self.outreach_db_id, {
                "Subject": {"title": {}},
                "Email Draft": {"rich_text": {}},
                "Status": {"select": {"options": [
                    {"name": "draft"}, {"name": "approved"},
                    {"name": "sent"}, {"name": "bounced"}, {"name": "replied"},
                ]}},
                "Sent At": {"date": {}},
            })

        self._schemas_ensured = True
        logger.info("All Notion database schemas verified/created.")

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_database(self, database_id: str, label: str) -> int:
        if not database_id:
            return 0
        total = 0
        start_cursor: Optional[str] = None
        try:
            while True:
                kwargs: dict = {"page_size": 100}
                if start_cursor:
                    kwargs["start_cursor"] = start_cursor
                resp = self._query_data_source(database_id, **kwargs)
                for page in resp.get("results", []):
                    page_id = page.get("id")
                    if not page_id:
                        continue
                    try:
                        self.client.pages.update(page_id=page_id, archived=True)
                        total += 1
                    except Exception as exc:
                        logger.debug("Could not archive page %s: %s", page_id, exc)
                if not resp.get("has_more"):
                    break
                start_cursor = resp.get("next_cursor")
            if total > 0:
                logger.info("Cleared %s: archived %d page(s).", label, total)
        except Exception as exc:
            logger.warning("Could not clear %s: %s", label, exc)
        return total

    def clear_all_tables(self) -> None:
        self.ensure_schemas()
        n_leads = self._clear_database(self.leads_db_id, "Leads")
        n_contacts = self._clear_database(self.contacts_db_id, "Contacts")
        n_outreach = self._clear_database(self.outreach_db_id, "Outreach")
        logger.info(
            "Notion clean complete: Leads=%d, Contacts=%d, Outreach=%d page(s) archived.",
            n_leads, n_contacts, n_outreach,
        )

    # ------------------------------------------------------------------
    # Leads DB
    # ------------------------------------------------------------------

    def load_recent_fingerprints(self, days: int = 7) -> set[str]:
        self.ensure_schemas()
        if not self.leads_db_id:
            return set()

        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        fingerprints: set[str] = set()
        start_cursor: Optional[str] = None

        while True:
            kwargs: dict = {"page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = self._query_data_source(self.leads_db_id, **kwargs)

            for page in resp.get("results", []):
                props = page.get("properties", {})
                date_prop = props.get("Date Found", {}).get("date", {}) or {}
                date_str = date_prop.get("start")
                if not date_str or date_str < since:
                    continue
                fp_prop = props.get("Fingerprint", {})
                rich = fp_prop.get("rich_text", [])
                if rich:
                    fingerprints.add(rich[0]["plain_text"])

            if not resp.get("has_more"):
                break
            start_cursor = resp.get("next_cursor")

        logger.info("Loaded %d fingerprints from Notion (last %d days)", len(fingerprints), days)
        return fingerprints

    def lead_exists_by_company(self, company_name: str, days: int = 7, post_type: Optional[str] = None) -> bool:
        if not self.leads_db_id:
            return False

        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        start_cursor: Optional[str] = None

        while True:
            kwargs: dict = {"page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = self._query_data_source(self.leads_db_id, **kwargs)

            for page in resp.get("results", []):
                props = page.get("properties", {})
                title_parts = props.get("Company Name", {}).get("title", [])
                existing_name = title_parts[0]["plain_text"] if title_parts else ""
                if existing_name != company_name:
                    continue
                date_prop = props.get("Date Found", {}).get("date", {}) or {}
                date_str = date_prop.get("start")
                if not date_str or date_str < since:
                    continue
                if post_type:
                    pt = props.get("Post Type", {}).get("select", {}).get("name", "")
                    if pt != post_type:
                        continue
                return True

            if not resp.get("has_more"):
                break
            start_cursor = resp.get("next_cursor")

        return False

    def add_lead(self, data: dict) -> str:
        self.ensure_schemas()

        source_link = data.get("source_link", "") or None

        properties: dict = {
            "Company Name": {"title": [{"text": {"content": data.get("company_name", "Unknown")}}]},
            "Post Type": {"select": {"name": data.get("post_type", "hiring")}},
            "Role": {"rich_text": [{"text": {"content": data.get("role", "")}}]},
            "Funding Amount": {"rich_text": [{"text": {"content": data.get("funding_amount", "")}}]},
            "Platform": {"select": {"name": data.get("platform", "x.com")}},
            "Date Found": {"date": {"start": datetime.utcnow().date().isoformat()}},
            "Status": {"select": {"name": "new"}},
            "Fingerprint": {"rich_text": [{"text": {"content": data.get("fingerprint", "")}}]},
        }
        if source_link:
            properties["Source Link"] = {"url": source_link}

        page = self._create_page(self.leads_db_id, properties)
        logger.info("Created lead: %s (%s)", data.get("company_name"), page["id"])
        return page["id"]

    def update_lead_status(self, page_id: str, status: str) -> None:
        self.client.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": status}}},
        )

    # ------------------------------------------------------------------
    # Contacts DB
    # ------------------------------------------------------------------

    def _get_contacts_property_names(self) -> set[str]:
        """Return property names from the Contacts data source."""
        if not self.contacts_db_id:
            return set()
        props = self._get_ds_property_names(self.contacts_db_id)
        if props:
            return props
        return {"Name", "Email", "Role/Title", "Company Name", "Email Confidence", "LinkedIn URL"}

    def add_contact(self, data: dict) -> str:
        self.ensure_schemas()
        if not self.contacts_db_id:
            raise ValueError("NOTION_CONTACTS_DB_ID not set in environment")

        existing = self._get_contacts_property_names()

        email_val = data.get("email", "") or None
        linkedin_val = data.get("linkedin_url", "") or None
        company_name = data.get("company_name", "") or ""

        properties: dict = {}

        if "Name" in existing:
            properties["Name"] = {"title": [{"text": {"content": data.get("name", "") or "Unknown"}}]}
        if "Role/Title" in existing:
            properties["Role/Title"] = {"rich_text": [{"text": {"content": data.get("role_title", "")}}]}
        if "Email Confidence" in existing:
            properties["Email Confidence"] = {"select": {"name": data.get("email_confidence", "low")}}

        if company_name:
            if "Company Name" in existing:
                properties["Company Name"] = {"rich_text": [{"text": {"content": company_name}}]}
            elif "Company" in existing:
                properties["Company"] = {"rich_text": [{"text": {"content": company_name}}]}

        if email_val and "Email" in existing:
            properties["Email"] = {"email": email_val}

        if linkedin_val:
            if "LinkedIn URL" in existing:
                properties["LinkedIn URL"] = {"url": linkedin_val}
            elif "Linkedin" in existing:
                properties["Linkedin"] = {"url": linkedin_val}
            elif "LinkedIn" in existing:
                properties["LinkedIn"] = {"url": linkedin_val}

        if not properties:
            raise ValueError("Contacts data source has none of the expected properties")

        page = self._create_page(self.contacts_db_id, properties)
        logger.info("Created contact: %s at %s (%s)", data.get("name"), company_name, page["id"])
        return page["id"]

    def contact_exists(self, email: str) -> bool:
        if not self.contacts_db_id or not email:
            return False

        start_cursor: Optional[str] = None
        while True:
            kwargs: dict = {"page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = self._query_data_source(self.contacts_db_id, **kwargs)

            for page in resp.get("results", []):
                props = page.get("properties", {})
                existing_email = props.get("Email", {}).get("email", "") or ""
                if existing_email.lower() == email.lower():
                    return True

            if not resp.get("has_more"):
                break
            start_cursor = resp.get("next_cursor")
        return False

    # ------------------------------------------------------------------
    # Outreach DB
    # ------------------------------------------------------------------

    def add_outreach(self, data: dict) -> str:
        self.ensure_schemas()

        properties: dict = {
            "Subject": {"title": [{"text": {"content": data.get("subject", "")}}]},
            "Email Draft": {"rich_text": [{"text": {"content": data.get("email_draft", "")[:2000]}}]},
            "Status": {"select": {"name": "draft"}},
        }

        page = self._create_page(self.outreach_db_id, properties)
        logger.info("Created outreach draft: %s", page["id"])
        return page["id"]

    def update_outreach_status(self, page_id: str, status: str) -> None:
        props: dict = {"Status": {"select": {"name": status}}}
        if status == "sent":
            props["Sent At"] = {"date": {"start": datetime.utcnow().isoformat()}}
        self.client.pages.update(page_id=page_id, properties=props)

    def get_pending_outreach(self) -> list[dict]:
        if not self.outreach_db_id:
            return []

        results = []
        start_cursor: Optional[str] = None

        while True:
            kwargs: dict = {"page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = self._query_data_source(self.outreach_db_id, **kwargs)

            for page in resp.get("results", []):
                props = page.get("properties", {})
                status = props.get("Status", {}).get("select", {}).get("name", "")
                if status != "draft":
                    continue
                subject_parts = props.get("Subject", {}).get("title", [])
                draft_parts = props.get("Email Draft", {}).get("rich_text", [])
                contact_rel = props.get("Contact", {}).get("relation", [])
                results.append({
                    "page_id": page["id"],
                    "subject": subject_parts[0]["plain_text"] if subject_parts else "",
                    "email_draft": draft_parts[0]["plain_text"] if draft_parts else "",
                    "contact_page_id": contact_rel[0]["id"] if contact_rel else "",
                })

            if not resp.get("has_more"):
                break
            start_cursor = resp.get("next_cursor")

        return results

    def get_contact_email(self, contact_page_id: str) -> str:
        if not contact_page_id:
            return ""
        page = self.client.pages.retrieve(page_id=contact_page_id)
        return page["properties"].get("Email", {}).get("email", "") or ""

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_new_leads(self) -> list[dict]:
        if not self.leads_db_id:
            return []

        results = []
        start_cursor: Optional[str] = None

        while True:
            kwargs: dict = {"page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            resp = self._query_data_source(self.leads_db_id, **kwargs)

            for page in resp.get("results", []):
                props = page.get("properties", {})
                status = props.get("Status", {}).get("select", {}).get("name", "")
                if status != "new":
                    continue
                title_parts = props.get("Company Name", {}).get("title", [])
                role_parts = props.get("Role", {}).get("rich_text", [])
                funding_parts = props.get("Funding Amount", {}).get("rich_text", [])
                source = props.get("Source Link", {}).get("url", "")
                post_type = props.get("Post Type", {}).get("select", {}).get("name", "")
                platform = props.get("Platform", {}).get("select", {}).get("name", "")
                results.append({
                    "page_id": page["id"],
                    "company_name": title_parts[0]["plain_text"] if title_parts else "Unknown",
                    "role": role_parts[0]["plain_text"] if role_parts else "",
                    "funding_amount": funding_parts[0]["plain_text"] if funding_parts else "",
                    "source_link": source,
                    "post_type": post_type,
                    "platform": platform,
                })

            if not resp.get("has_more"):
                break
            start_cursor = resp.get("next_cursor")

        return results
