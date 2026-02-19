#!/usr/bin/env python3
"""
Company LinkedIn -> People -> Profile -> Best email (terminal logs).
"""

import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from research.company_people_probe import run_probe


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")

    parser = argparse.ArgumentParser(
        description="Company LinkedIn -> People -> Profiles -> best emails"
    )
    parser.add_argument("--company-url", required=True, help="LinkedIn company URL")
    parser.add_argument("--limit", type=int, default=5, help="Profiles to process")
    parser.add_argument(
        "--domain",
        default="",
        help="Company domain override (recommended), e.g. openai.com",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Use visible browser for LinkedIn verification/challenges",
    )
    args = parser.parse_args()

    rows = asyncio.run(
        run_probe(
            company_url=args.company_url,
            limit=max(1, args.limit),
            domain_override=args.domain,
            headful=args.headful,
        )
    )

    print("\n=== COMPANY PEOPLE EMAIL PROBE RESULTS ===\n")
    print(f"Profiles processed: {len(rows)}")
    print("")
    for i, r in enumerate(rows, start=1):
        print(f"{i}. {r['name']}")
        print(f"   Headline:   {r.get('headline', '')}")
        print(f"   LinkedIn:   {r.get('linkedin_url', '')}")
        print(f"   Email:      {r.get('email', '')}")
        print(f"   Confidence: {r.get('confidence', '')}")
        print(f"   Method:     {r.get('method', '')}")
        print("")


if __name__ == "__main__":
    main()
