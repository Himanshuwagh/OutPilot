#!/usr/bin/env python3
"""
Demo script: run the pipeline end-to-end WITHOUT sending any emails.

Usage:
    python demo.py

What it does:
  - Scrapes last-24h posts
  - Creates leads in Notion
  - Researches contacts and drafts emails
  - Prints a few sample drafts to the console
  - DOES NOT send any emails
"""

import logging
from pathlib import Path

from dotenv import load_dotenv

from agents.tools import (
    scrape_all_sources,
    process_and_store_leads,
    research_contacts,
    draft_cold_emails,
)


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("demo")

    logger.info("=== DEMO RUN: scraping sources (no emails will be sent) ===")
    # CrewAI @tool objects must be invoked via .run(...)
    posts = scrape_all_sources.run()
    logger.info("Scraped %d raw posts", len(posts))

    logger.info("=== Processing and storing leads in Notion ===")
    leads = process_and_store_leads.run(posts)
    logger.info("Stored %d new leads", len(leads))

    if not leads:
        logger.info("No new leads found. Exiting demo.")
        return

    logger.info("=== Researching contacts for leads ===")
    contacts = research_contacts.run(leads)
    logger.info("Found %d contacts", len(contacts))

    if not contacts:
        logger.info("No contacts found. Exiting demo.")
        return

    logger.info("=== Drafting cold emails (Groq) ===")
    drafts = draft_cold_emails.run(contacts)
    logger.info("Drafted %d emails (none will be sent in demo mode)", len(drafts))

    # Show a few example drafts
    print("\n=== SAMPLE DRAFTS (first 3) ===\n")
    for draft in drafts[:3]:
        print(f"To: {draft.get('to_email', '')}")
        print(f"Subject: {draft.get('subject', '')}")
        print()
        print(draft.get("body", ""))
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    main()

