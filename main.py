#!/usr/bin/env python3
"""
Entry point for the AI Cold Outreach Pipeline.

Usage:
    python main.py --run-now                          Run the full auto-scrape pipeline once
    python main.py --schedule                         Run as a daily scheduler (6 AM)
    python main.py --contacts-only                    Scrape top posts -> leads -> contacts/emails in Notion
    python main.py --company "OpenAI"                 Target a specific company (find managers, email them)
    python main.py --company "Anthropic" --role "AI Engineer"
    python main.py --company "Scale AI" --domain "scale.com"
    python main.py --company "Mistral" --contacts 3
    python main.py --linkedin-url "https://www.linkedin.com/in/USERNAME/" --domain "openai.com"
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment before anything else
load_dotenv(Path(__file__).parent / ".env")

from agents.crew import run_pipeline
from agents.tools import run_company_outreach
from agents.tools import scrape_all_sources, process_and_store_leads, research_contacts
from find_email_from_linkedin_profile import run_lookup
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", mode="a"),
    ],
)
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(
        description="AI Cold Outreach Pipeline - Automated hiring/funding lead generation"
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the full auto-scrape pipeline once immediately",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start the scheduler (runs daily at configured time)",
    )
    parser.add_argument(
        "--contacts-only",
        action="store_true",
        help="Scrape top posts, research contacts/emails, and store in Notion (no drafting/sending)",
    )
    parser.add_argument(
        "--company",
        type=str,
        default="",
        help="Target a specific company: search LinkedIn for managers, find emails, store in Notion, and send cold emails",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="",
        help="Role to reference in cold emails (used with --company, e.g. 'ML Engineer')",
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
        help="Number of contacts to find per company (used with --company, default: 5)",
    )
    parser.add_argument(
        "--top-posts",
        type=int,
        default=20,
        help="Top posts to process in contacts-only mode (default: 20)",
    )
    parser.add_argument(
        "--linkedin-url",
        type=str,
        default="",
        help="Direct LinkedIn profile URL mode: resolve best email for this profile and save to Notion Contacts DB",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Use visible browser (helps if LinkedIn checkpoint/verification appears)",
    )

    args = parser.parse_args()

    if (
        not args.run_now
        and not args.schedule
        and not args.contacts_only
        and not args.company
        and not args.linkedin_url
    ):
        parser.print_help()
        sys.exit(1)

    # ---- Scrape -> lead -> contact/email (store in Notion only) ----
    if args.contacts_only:
        logger.info("Running contacts-only mode (no drafting/sending)...")
        try:
            posts = scrape_all_sources.run()
            logger.info("Scraped %d raw posts", len(posts))
            if args.top_posts > 0:
                posts = posts[: args.top_posts]
            logger.info("Processing top %d posts", len(posts))

            leads = process_and_store_leads.run(posts)
            logger.info("Stored %d new leads", len(leads))

            if not leads:
                logger.info("No new leads found.")
                return

            contacts = research_contacts.run(leads)
            logger.info("Stored %d contacts in Notion", len(contacts))
            if not contacts:
                logger.warning("No contacts/emails found.")
                sys.exit(1)
        except Exception as exc:
            logger.error("Contacts-only mode failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

    # ---- Direct LinkedIn profile email lookup (always saves to Notion) ----
    if args.linkedin_url:
        logger.info("Starting direct LinkedIn profile lookup for: %s", args.linkedin_url)
        try:
            result = asyncio.run(
                run_lookup(
                    linkedin_url=args.linkedin_url,
                    company_override=args.company,
                    domain_override=args.domain,
                    headful=args.headful,
                    save_notion=True,
                )
            )
            logger.info(
                "Resolved email: %s (%s confidence, method=%s)",
                result.get("email", ""),
                result.get("confidence", "low"),
                result.get("method", ""),
            )
            if not result.get("email"):
                logger.warning(
                    "No email resolved for profile. Try passing --domain and --headful."
                )
                sys.exit(1)
        except Exception as exc:
            logger.error("LinkedIn profile lookup failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

    # ---- Company-targeted outreach (sends emails) ----
    if args.company:
        logger.info("Starting company-targeted outreach for: %s", args.company)
        try:
            result = asyncio.run(
                run_company_outreach(
                    company_name=args.company,
                    role=args.role,
                    domain_override=args.domain,
                    dry_run=False,
                    num_contacts=args.contacts,
                )
            )
            if result["emails_found"] == 0:
                logger.warning(
                    "No emails found for %s. Try --domain or check LinkedIn session.",
                    args.company,
                )
                sys.exit(1)
        except Exception as exc:
            logger.error("Company outreach failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

    # ---- Auto-scrape pipeline ----
    if args.run_now:
        logger.info("Running full auto-scrape pipeline now...")
        try:
            result = run_pipeline()
            logger.info("Pipeline result: %s", result)
        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            sys.exit(1)

    if args.schedule:
        logger.info("Starting scheduler...")
        start_scheduler()


if __name__ == "__main__":
    main()
