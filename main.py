#!/usr/bin/env python3
"""
Entry point for the AI Cold Outreach Pipeline.

Usage:
    python main.py --run-now                          Run the full auto-scrape pipeline once
    python main.py --schedule                         Run as a daily scheduler (6 AM)
    python main.py --company "OpenAI"                 Target a specific company (find managers, email them)
    python main.py --company "Anthropic" --role "AI Engineer"
    python main.py --company "Scale AI" --domain "scale.com"
    python main.py --company "Mistral" --contacts 3
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

    args = parser.parse_args()

    if not args.run_now and not args.schedule and not args.company:
        parser.print_help()
        sys.exit(1)

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
