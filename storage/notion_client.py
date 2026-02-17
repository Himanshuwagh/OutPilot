"""
Notion client for managing Leads, Contacts, and Outreach databases.
Uses the official notion-client SDK (free).
Auto-creates all required database properties on first run.
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from notion_client import Client

logger = logging.getLogger(__name__)


def _hash_fingerprint(text: str) -> str:
    """Generate a short SHA-256 fingerprint from text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class NotionStorage:
    """CRUD operations for all three Notion databases."""

    def __init__(self):
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise ValueError("NOTION_TOKEN not set in environment")
        self.client = Client(auth=token)

        self.leads_db_id = os.getenv("NOTION_LEADS_DB_ID", "")
        self.contacts_db_id = os.getenv("NOTION_CONTACTS_DB_ID", "")
        self.outreach_db_id = os.getenv("NOTION_OUTREACH_DB_ID", "")

        self._schemas_ensured = False

    # ------------------------------------------------------------------
    # Schema auto-creation
    # ------------------------------------------------------------------

    def ensure_schemas(self) -> None:
        """Create all required properties on each database if they don't exist yet."""
        if self._schemas_ensured:
            return

        if self.leads_db_id:
            self._ensure_db_properties(self.leads_db_id, {
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
            self._ensure_db_properties(self.contacts_db_id, {
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
            self._ensure_db_properties(self.outreach_db_id, {
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

    def _ensure_db_properties(self, database_id: str, required: dict) -> None:
        """Add any missing properties to a Notion database."""
        try:
            db = self.client.databases.retrieve(database_id=database_id)
        except Exception as exc:
            logger.error("Cannot retrieve database %s: %s", database_id, exc)
            return

        existing = set(db.get("properties", {}).keys())
        to_add = {}

        for prop_name, prop_config in required.items():
            if prop_name not in existing:
                to_add[prop_name] = prop_config

        if not to_add:
            logger.info("Database %s: all properties already exist.", database_id)
            return

        try:
            self.client.databases.update(
                database_id=database_id,
                properties=to_add,
            )
            logger.info(
                "Database %s: created properties: %s",
                database_id,
                ", ".join(to_add.keys()),
            )
        except Exception as exc:
            logger.error("Failed to update database %s: %s", database_id, exc)

    # ------------------------------------------------------------------
    # Leads DB
    # ------------------------------------------------------------------

    def load_recent_fingerprints(self, days: int = 7) -> set[str]:
        """Batch-load all fingerprints from the last N days into a set for O(1) dedup."""
        self.ensure_schemas()

        if not self.leads_db_id:
            return set()

        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        fingerprints: set[str] = set()
        start_cursor: Optional[str] = None

        while True:
            resp = self.client.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
                page_size=100,
            )

            found_any_in_db = False
            for page in resp.get("results", []):
                parent = page.get("parent", {})
                if parent.get("type") != "database_id" or parent.get("database_id") != self.leads_db_id:
                    continue
                found_any_in_db = True

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
        """Check if a lead for this company already exists within the window."""
        if not self.leads_db_id:
            return False

        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        start_cursor: Optional[str] = None

        while True:
            resp = self.client.search(
                query=company_name,
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
                page_size=50,
            )

            for page in resp.get("results", []):
                parent = page.get("parent", {})
                if parent.get("type") != "database_id" or parent.get("database_id") != self.leads_db_id:
                    continue

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
        """
        Insert a new lead into Notion.

        Expected keys: company_name, source_link, post_type, role, funding_amount,
                        platform, fingerprint
        Returns the page ID.
        """
        self.ensure_schemas()

        source_link = data.get("source_link", "") or None
        linkedin_url_val = data.get("linkedin_url", "") or None

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

        page = self.client.pages.create(
            parent={"database_id": self.leads_db_id},
            properties=properties,
        )
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

    def add_contact(self, data: dict) -> str:
        """
        Insert a contact.

        Expected keys: name, email, role_title, lead_page_id, email_confidence,
                        linkedin_url, company_name
        """
        self.ensure_schemas()

        email_val = data.get("email", "") or None
        linkedin_val = data.get("linkedin_url", "") or None
        company_name = data.get("company_name", "") or ""

        properties: dict = {
            "Name": {"title": [{"text": {"content": data.get("name", "")}}]},
            "Role/Title": {"rich_text": [{"text": {"content": data.get("role_title", "")}}]},
            "Email Confidence": {"select": {"name": data.get("email_confidence", "low")}},
        }

        if company_name:
            properties["Company Name"] = {"rich_text": [{"text": {"content": company_name}}]}
        if email_val:
            properties["Email"] = {"email": email_val}
        if linkedin_val:
            properties["LinkedIn URL"] = {"url": linkedin_val}

        page = self.client.pages.create(
            parent={"database_id": self.contacts_db_id},
            properties=properties,
        )
        logger.info("Created contact: %s at %s (%s)", data.get("name"), company_name, page["id"])
        return page["id"]

    def contact_exists(self, email: str) -> bool:
        """Check if a contact with this email already exists."""
        if not self.contacts_db_id or not email:
            return False

        start_cursor: Optional[str] = None

        while True:
            resp = self.client.search(
                query=email,
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
                page_size=50,
            )

            for page in resp.get("results", []):
                parent = page.get("parent", {})
                if parent.get("type") != "database_id" or parent.get("database_id") != self.contacts_db_id:
                    continue
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
        """
        Insert an outreach draft.

        Expected keys: subject, contact_page_id, email_draft
        """
        self.ensure_schemas()

        properties: dict = {
            "Subject": {"title": [{"text": {"content": data.get("subject", "")}}]},
            "Email Draft": {"rich_text": [{"text": {"content": data.get("email_draft", "")[:2000]}}]},
            "Status": {"select": {"name": "draft"}},
        }

        page = self.client.pages.create(
            parent={"database_id": self.outreach_db_id},
            properties=properties,
        )
        logger.info("Created outreach draft: %s", page["id"])
        return page["id"]

    def update_outreach_status(self, page_id: str, status: str) -> None:
        props: dict = {"Status": {"select": {"name": status}}}
        if status == "sent":
            props["Sent At"] = {"date": {"start": datetime.utcnow().isoformat()}}
        self.client.pages.update(page_id=page_id, properties=props)

    def get_pending_outreach(self) -> list[dict]:
        """Return all outreach entries with status 'draft'."""
        if not self.outreach_db_id:
            return []

        results = []
        start_cursor: Optional[str] = None

        while True:
            resp = self.client.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
                page_size=50,
            )

            for page in resp.get("results", []):
                parent = page.get("parent", {})
                if parent.get("type") != "database_id" or parent.get("database_id") != self.outreach_db_id:
                    continue

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
        """Retrieve the email for a contact page."""
        if not contact_page_id:
            return ""
        page = self.client.pages.retrieve(page_id=contact_page_id)
        return page["properties"].get("Email", {}).get("email", "") or ""

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_new_leads(self) -> list[dict]:
        """Return all leads with status 'new'."""
        if not self.leads_db_id:
            return []

        results = []
        start_cursor: Optional[str] = None

        while True:
            resp = self.client.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
                page_size=50,
            )

            for page in resp.get("results", []):
                parent = page.get("parent", {})
                if parent.get("type") != "database_id" or parent.get("database_id") != self.leads_db_id:
                    continue

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
