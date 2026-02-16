#!/usr/bin/env python3
"""
One-time setup: create all required properties on Notion databases.
Run this ONCE before running demo.py or main.py.

Usage:
    python setup_notion.py
"""

import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from notion_client import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_notion")


def setup_database(client: Client, db_id: str, db_name: str, properties: dict) -> None:
    """Retrieve a database, find missing properties, and add them."""
    logger.info("--- Setting up '%s' (ID: %s) ---", db_name, db_id)

    try:
        db = client.databases.retrieve(database_id=db_id)
    except Exception as exc:
        logger.error("  FAILED to retrieve database: %s", exc)
        return

    existing = db.get("properties", {})
    logger.info("  Existing properties: %s", list(existing.keys()))

    # Notion auto-creates a title property; find its actual name
    title_prop_name = None
    for name, prop in existing.items():
        if prop.get("type") == "title":
            title_prop_name = name
            break

    # Figure out what our schema wants the title to be called
    desired_title_name = None
    for name, prop in properties.items():
        if "title" in prop:
            desired_title_name = name
            break

    # If the existing title has a different name, rename it
    if title_prop_name and desired_title_name and title_prop_name != desired_title_name:
        logger.info("  Renaming title property '%s' -> '%s'", title_prop_name, desired_title_name)
        try:
            client.databases.update(
                database_id=db_id,
                properties={
                    title_prop_name: {"name": desired_title_name},
                },
            )
            logger.info("  Title renamed successfully.")
        except Exception as exc:
            logger.error("  Failed to rename title: %s", exc)

    # Now add all non-title properties that are missing
    to_add = {}
    # Re-fetch after possible rename
    try:
        db = client.databases.retrieve(database_id=db_id)
    except Exception:
        pass
    existing = set(db.get("properties", {}).keys())

    for prop_name, prop_config in properties.items():
        if prop_name not in existing:
            # Skip title — it should already exist (possibly renamed)
            if "title" in prop_config:
                continue
            to_add[prop_name] = prop_config

    if not to_add:
        logger.info("  All properties already exist. Nothing to add.")
        return

    logger.info("  Adding properties: %s", list(to_add.keys()))
    try:
        client.databases.update(
            database_id=db_id,
            properties=to_add,
        )
        logger.info("  SUCCESS: Properties added.")
    except Exception as exc:
        logger.error("  FAILED to add properties: %s", exc)


def main():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        logger.error("NOTION_TOKEN not set in .env")
        sys.exit(1)

    client = Client(auth=token)

    leads_id = os.getenv("NOTION_LEADS_DB_ID", "")
    contacts_id = os.getenv("NOTION_CONTACTS_DB_ID", "")
    outreach_id = os.getenv("NOTION_OUTREACH_DB_ID", "")

    if not all([leads_id, contacts_id, outreach_id]):
        logger.error("One or more NOTION_*_DB_ID values are missing from .env")
        sys.exit(1)

    # Leads DB
    setup_database(client, leads_id, "Leads", {
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

    # Contacts DB
    setup_database(client, contacts_id, "Contacts", {
        "Name": {"title": {}},
        "Email": {"email": {}},
        "Role/Title": {"rich_text": {}},
        "Email Confidence": {"select": {"options": [
            {"name": "high"}, {"name": "medium"}, {"name": "low"},
        ]}},
        "LinkedIn URL": {"url": {}},
    })

    # Outreach DB
    setup_database(client, outreach_id, "Outreach", {
        "Subject": {"title": {}},
        "Email Draft": {"rich_text": {}},
        "Status": {"select": {"options": [
            {"name": "draft"}, {"name": "approved"},
            {"name": "sent"}, {"name": "bounced"}, {"name": "replied"},
        ]}},
        "Sent At": {"date": {}},
    })

    logger.info("\n=== DONE. All databases are ready. ===")
    logger.info("You can now run: python demo.py")


if __name__ == "__main__":
    main()
