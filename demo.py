#!/usr/bin/env python3
"""
Demo script: run the pipeline end-to-end WITHOUT sending any emails.

Usage:
    python demo.py                                     Auto-scrape pipeline (no emails sent)
    python demo.py --company "OpenAI"                  Target a specific company (dry run)
    python demo.py --company "Anthropic" --role "AI Engineer"
    python demo.py --company "Scale AI" --domain "scale.com"
    python demo.py --company "Mistral" --contacts 3

What it does:
  Auto-scrape mode (default):
    - Scrapes last-24h posts from X.com, LinkedIn, and news sites
    - Creates leads in Notion
    - Researches contacts and drafts emails
    - Prints sample drafts to the console
    - DOES NOT send any emails

  Company mode (--company):
    - Searches LinkedIn People for hiring managers / managers at the company
    - Finds 5 relevant contacts and their emails
    - Stores contacts in Notion
    - Drafts personalized cold emails
    - Prints drafts to the console
    - DOES NOT send any emails
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("demo")

    parser = argparse.ArgumentParser(
        description="Demo run - everything except actually sending emails"
    )
    parser.add_argument(
        "--company",
        type=str,
        default="",
        help="Target a specific company (e.g. 'OpenAI'). Searches LinkedIn for managers, finds emails, drafts cold emails.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="",
        help="Role to reference in emails (used with --company, e.g. 'ML Engineer')",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="",
        help="Company domain override (used with --company, e.g. 'openai.com')",
    )
    parser.add_argument(
        "--contacts",
        type=int,
        default=5,
        help="Number of contacts to find (used with --company, default: 5)",
    )
    args = parser.parse_args()

    # ---- Company-targeted outreach (dry run) ----
    if args.company:
        from agents.tools import run_company_outreach

        logger.info(
            "=== DEMO: Company outreach for %s (no emails will be sent) ===",
            args.company,
        )
        try:
            result = asyncio.run(
                run_company_outreach(
                    company_name=args.company,
                    role=args.role,
                    domain_override=args.domain,
                    dry_run=True,
                    num_contacts=args.contacts,
                )
            )

            print("\n=== RESULTS ===\n")
            print(f"Company:           {result['company']}")
            print(f"Contacts found:    {result['contacts_found']}")
            print(f"Emails discovered: {result['emails_found']}")
            print(f"Stored in Notion:  {result['emails_stored_notion']}")
            print(f"Drafts created:    {result['drafts_created']}")

            if result["contacts"]:
                print("\n=== CONTACTS ===\n")
                for c in result["contacts"]:
                    print(
                        f"  {c['name']} | {c['role_title']} | {c['email']} "
                        f"({c['confidence']}) | {c['linkedin_url']}"
                    )

            if result["emails_found"] == 0:
                logger.warning(
                    "No emails found. Try --domain or check LinkedIn session."
                )
                sys.exit(1)

        except Exception as exc:
            logger.error("Company outreach failed: %s", exc, exc_info=True)
            sys.exit(1)

        return

    # ---- Auto-scrape pipeline (dry run -- no emails sent) ----
    from agents.tools import (
        scrape_all_sources,
        process_and_store_leads,
        research_contacts,
        draft_cold_emails,
    )

    logger.info("=== DEMO RUN: scraping sources (no emails will be sent) ===")
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
