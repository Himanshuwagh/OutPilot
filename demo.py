#!/usr/bin/env python3
"""
Demo script: run the pipeline end-to-end WITHOUT sending any emails.

Usage:
    python demo.py                                     Scrape top posts -> find contacts/emails -> store in Notion
    python demo.py --company "OpenAI"                  Target a specific company (dry run)
    python demo.py --company "Anthropic" --role "AI Engineer"
    python demo.py --company "Scale AI" --domain "scale.com"
    python demo.py --company "Mistral" --contacts 3
    python demo.py --company-linkedin-url "https://www.linkedin.com/company/openai/" --contacts 5 --domain openai.com
    python demo.py --linkedin-url "https://www.linkedin.com/in/USERNAME/" --domain "openai.com"

What it does:
  Auto-scrape mode (default):
    - Scrapes last-24h posts from X.com, LinkedIn, and news sites
    - Keeps top N posts (default 20)
    - Creates leads in Notion
    - Finds company LinkedIn page from each lead
    - Scrapes People tab + profile pages to resolve emails
    - Stores contacts in Notion
    - DOES NOT send any emails

  Company mode (--company):
    - Searches LinkedIn People for hiring managers / managers at the company
    - Finds 5 relevant contacts and their emails
    - Stores contacts in Notion
    - Drafts personalized cold emails
    - Prints drafts to the console
    - DOES NOT send any emails

  Profile mode (--linkedin-url):
    - Opens one LinkedIn profile URL
    - Resolves best possible email
    - Saves contact in Notion Contacts DB automatically
    - DOES NOT send any emails

  Company page mode (--company-linkedin-url):
    - Opens company LinkedIn page + People tab
    - Opens employee profiles and resolves emails
    - Stops after N profiles (default 5)
    - Saves contacts in Notion Contacts DB automatically
    - DOES NOT send any emails
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from storage.notion_client import NotionStorage


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
        "--company-linkedin-url",
        type=str,
        default="",
        help="Company-page flow: LinkedIn company URL -> People -> profile emails -> save to Notion",
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
    parser.add_argument(
        "--top-posts",
        type=int,
        default=20,
        help="Top posts to process in auto mode (default: 20)",
    )
    parser.add_argument(
        "--linkedin-url",
        type=str,
        default="",
        help="Direct profile mode: find best email from a LinkedIn profile URL and save to Notion",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Use visible browser (helps if LinkedIn verification/checkpoint appears)",
    )
    args = parser.parse_args()

    # Clear all Notion tables before this run
    try:
        notion = NotionStorage()
        notion.clear_all_tables()
    except Exception as exc:
        logger.warning("Could not clear Notion tables (skipping): %s", exc)

    # ---- Company LinkedIn URL flow (always saves to Notion) ----
    if args.company_linkedin_url:
        from run_company_people_email_probe import run_probe

        logger.info(
            "=== DEMO: Company-page flow (People -> profiles -> emails -> Notion) ==="
        )
        try:
            rows = asyncio.run(
                run_probe(
                    company_url=args.company_linkedin_url,
                    limit=max(1, args.contacts),
                    domain_override=args.domain,
                    headful=args.headful,
                    save_notion=True,
                )
            )
            print("\n=== COMPANY PAGE RESULTS ===\n")
            print(f"Profiles processed: {len(rows)}")
            print("(Saved in Notion Contacts DB if not duplicate)\n")
            for i, r in enumerate(rows, start=1):
                print(f"{i}. {r.get('name', '')}")
                print(f"   LinkedIn:   {r.get('linkedin_url', '')}")
                print(f"   Email:      {r.get('email', '')}")
                print(f"   Confidence: {r.get('confidence', 'low')}")
                print(f"   Method:     {r.get('method', '')}")
                print("")
            if not rows:
                logger.warning(
                    "No emails resolved from company page. Try --headful and pass --domain."
                )
                sys.exit(1)
        except Exception as exc:
            logger.error("Company-page flow failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

    # ---- Direct LinkedIn profile lookup (always saves to Notion) ----
    if args.linkedin_url:
        from find_email_from_linkedin_profile import run_lookup

        logger.info(
            "=== DEMO: LinkedIn profile email lookup (auto-save to Notion) ==="
        )
        try:
            out = asyncio.run(
                run_lookup(
                    linkedin_url=args.linkedin_url,
                    company_override=args.company,
                    domain_override=args.domain,
                    headful=args.headful,
                    save_notion=True,
                )
            )
            print("\n=== LINKEDIN PROFILE RESULT ===\n")
            print(f"Name:       {out.get('name', '')}")
            print(f"Company:    {out.get('company', '')}")
            print(f"Domain:     {out.get('domain', '')}")
            print(f"LinkedIn:   {out.get('linkedin_url', '')}")
            print("")
            print(f"Best email: {out.get('email', '')}")
            print(f"Confidence: {out.get('confidence', '')}")
            print(f"Method:     {out.get('method', '')}")
            print("\nSaved in Notion Contacts DB (if not duplicate).")
            if not out.get("email"):
                logger.warning(
                    "No email resolved. Try passing --domain and/or --headful."
                )
                sys.exit(1)
        except Exception as exc:
            logger.error("Profile lookup failed: %s", exc, exc_info=True)
            sys.exit(1)
        return

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
    )
    from research.company_people_probe import (
        run_probe,
        discover_company_linkedin_url,
        is_valid_company_name,
    )

    logger.info("=== DEMO RUN: scrape X.com + LinkedIn (funding + job posts) -> leads -> contacts/emails ===")
    posts = scrape_all_sources.run()
    n_x = sum(1 for p in posts if p.get("platform") == "x.com")
    n_li = sum(1 for p in posts if p.get("platform") == "linkedin")
    n_other = len(posts) - n_x - n_li
    n_fund = sum(1 for p in posts if p.get("scrape_type") == "funding")
    n_job = sum(1 for p in posts if p.get("scrape_type") in {"job", "hiring"})
    n_enriched = sum(1 for p in posts if p.get("author_company"))
    logger.info(
        "Scraped %d raw posts (x.com=%d, linkedin=%d, other=%d | funding=%d, job/hiring=%d, profile_resolved=%d)",
        len(posts), n_x, n_li, n_other, n_fund, n_job, n_enriched,
    )

    if args.top_posts > 0:
        posts = posts[: args.top_posts]
    logger.info("Processing top %d posts", len(posts))

    logger.info("=== Processing and storing leads in Notion ===")
    leads = process_and_store_leads.run(posts)
    logger.info("Stored %d new leads", len(leads))

    if not leads:
        logger.info("No new leads found. Exiting demo.")
        return

    logger.info("=== Company-page people/email probe for leads ===")
    companies = []
    seen = set()
    for lead in leads:
        company = (lead.get("company_name") or "").strip()
        if not company or company in seen:
            continue
        seen.add(company)
        companies.append(company)

    total_contacts = 0
    for company in companies:
        if not is_valid_company_name(company):
            logger.info("Skipping '%s' — looks like a person name or too short.", company)
            continue
        company_url = discover_company_linkedin_url(company)
        if not company_url:
            logger.info(
                "HTTP search found no URL for '%s'; will try browser fallback in run_probe.",
                company,
            )
        else:
            logger.info("Company-page probe: %s -> %s", company, company_url)
        try:
            rows = asyncio.run(
                run_probe(
                    company_url=company_url,
                    limit=max(1, args.contacts),
                    domain_override="",
                    headful=args.headful,
                    save_notion=True,
                    company_name_hint=company,
                )
            )
        except Exception as exc:
            logger.warning("Probe failed for '%s': %s", company, exc)
            continue
        total_contacts += len(rows)
        logger.info("Resolved %d contacts for %s", len(rows), company)

    if total_contacts == 0:
        logger.info(
            "No contacts found from any company probe (Notion Contacts DB will be empty). Exiting demo."
        )
        return

    print("\n=== AUTO MODE RESULTS ===\n")
    print(f"Top posts processed:   {len(posts)}")
    funding_leads = sum(1 for l in leads if l.get("post_type") == "funding")
    job_leads = sum(1 for l in leads if l.get("post_type") in {"hiring", "both"})
    print(f"Leads from funding:    {funding_leads}")
    print(f"Leads from job posts:  {job_leads}")
    print(f"Total leads stored:    {len(leads)}")
    print(f"Recruiter contacts:    {total_contacts}")
    print("\n(Check logs above for 'Saved N contact(s) to Notion' to see actual Notion saves.)")


if __name__ == "__main__":
    main()
