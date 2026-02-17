#!/usr/bin/env python3
"""
Find best possible work email from a LinkedIn profile URL.

This script:
1) Opens the LinkedIn profile using your persisted LinkedIn session
2) Extracts name/headline/company hints from the page
3) Resolves company domain (or uses --domain override)
4) Runs AccurateEmailFinder scoring to pick the best candidate email

Usage:
  python find_email_from_linkedin_profile.py --linkedin-url "https://www.linkedin.com/in/example/"
  python find_email_from_linkedin_profile.py --linkedin-url "..." --company "OpenAI"
  python find_email_from_linkedin_profile.py --linkedin-url "..." --domain "openai.com"
  python find_email_from_linkedin_profile.py --linkedin-url "..." --save-notion
"""

import argparse
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from research.accurate_email_finder import AccurateEmailFinder
from research.domain_finder import DomainFinder
from scrapers.base_scraper import BaseScraper
from storage.notion_client import NotionStorage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("linkedin_profile_email")


class LinkedInProfileProbe(BaseScraper):
    PLATFORM = "linkedin"

    async def scrape(self) -> list[dict]:
        return []

    async def read_profile(self, linkedin_url: str) -> dict:
        await self.ensure_logged_in("https://www.linkedin.com/feed/", "feed")
        await self.page.goto(linkedin_url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(2, 4)

        page_text = ""
        try:
            page_text = await self.page.inner_text("body")
        except Exception:
            pass
        lower = page_text.lower()
        if any(x in lower for x in ["checkpoint", "verify", "security verification"]):
            raise RuntimeError(
                "LinkedIn checkpoint/verification detected. Run with --headful and solve challenge."
            )

        name = await self._first_text(
            [
                "h1",
                "h1.text-heading-xlarge",
                "main h1",
                "h1.inline",
            ]
        )
        headline = await self._first_text(
            [
                "div.text-body-medium.break-words",
                "div.text-body-medium",
                "main section div.text-body-medium",
            ]
        )

        # Best-effort company inference from headline, e.g. "... at OpenAI"
        company = self._infer_company_from_headline(headline or "")

        # JSON-LD fallback (some profile pages expose Person schema)
        if not name or not company:
            meta = await self._extract_jsonld_person()
            if not name:
                name = meta.get("name", "") or name
            if not company:
                company = meta.get("worksFor", "") or company

        name = self._clean_name(name)
        return {
            "name": name,
            "headline": (headline or "").strip(),
            "company": (company or "").strip(),
            "linkedin_url": linkedin_url,
        }

    async def _first_text(self, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if not el:
                    continue
                txt = (await el.inner_text()).strip()
                if txt:
                    return txt
            except Exception:
                continue
        return ""

    async def _extract_jsonld_person(self) -> dict:
        script = """
        (() => {
          const tags = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
          for (const tag of tags) {
            try {
              const data = JSON.parse(tag.textContent || '{}');
              const arr = Array.isArray(data) ? data : [data];
              for (const item of arr) {
                if (!item || item['@type'] !== 'Person') continue;
                const worksFor = item.worksFor && (item.worksFor.name || item.worksFor['@id']) || '';
                return { name: item.name || '', worksFor };
              }
            } catch (_) {}
          }
          return {};
        })();
        """
        try:
            return await self.page.evaluate(script)
        except Exception:
            return {}

    @staticmethod
    def _infer_company_from_headline(headline: str) -> str:
        # Handle common formats: "... at OpenAI", "... @ OpenAI"
        m = re.search(r"\bat\s+([A-Z][A-Za-z0-9 .&-]{1,80})$", headline.strip())
        if m:
            return m.group(1).strip()
        m = re.search(r"@\s*([A-Z][A-Za-z0-9 .&-]{1,80})$", headline.strip())
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _clean_name(name: str) -> str:
        name = re.sub(r"\s+", " ", name or "").strip()
        return re.sub(r"[^\w\s\-'.À-ÿ]", "", name).strip()


async def run_lookup(
    linkedin_url: str,
    company_override: str = "",
    domain_override: str = "",
    headful: bool = False,
    save_notion: bool = False,
) -> dict:
    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)
    li_cfg = cfg["scraping"]["linkedin"]
    headless = False if headful else cfg["scraping"].get("headless", True)

    probe = LinkedInProfileProbe(
        browser_data_dir=li_cfg["browser_data_dir"],
        headless=headless,
        daily_quota=li_cfg["daily_action_quota"],
    )

    profile = {}
    try:
        await probe.start()
        profile = await probe.read_profile(linkedin_url)
    finally:
        try:
            await probe.stop()
        except Exception:
            pass

    name = profile.get("name", "")
    if not name:
        raise RuntimeError("Could not extract name from LinkedIn profile page.")

    company = company_override or profile.get("company", "")
    domain = domain_override
    if not domain:
        if not company:
            raise RuntimeError(
                "Could not infer company from profile. Pass --company or --domain."
            )
        domain = DomainFinder().find_domain(company) or ""
    if not domain:
        raise RuntimeError(
            "Could not resolve company domain. Pass --domain explicitly."
        )

    finder = AccurateEmailFinder()
    result = finder.find_best_email(
        full_name=name,
        company_domain=domain,
        company_name=company,
        linkedin_url=linkedin_url,
    )

    output = {
        "name": name,
        "company": company,
        "domain": domain,
        "linkedin_url": linkedin_url,
        "email": result.get("email", ""),
        "confidence": result.get("confidence", "low"),
        "method": result.get("method", ""),
        "candidates": result.get("all_candidates", []),
        "headline": profile.get("headline", ""),
    }

    if save_notion and output["email"]:
        notion = NotionStorage()
        notion.ensure_schemas()
        if not notion.contact_exists(output["email"]):
            notion.add_contact(
                {
                    "name": output["name"],
                    "email": output["email"],
                    "role_title": output.get("headline", ""),
                    "company_name": output.get("company", ""),
                    "email_confidence": output.get("confidence", "low"),
                    "linkedin_url": output.get("linkedin_url", ""),
                }
            )

    return output


def main() -> None:
    load_dotenv(Path(__file__).parent / ".env")

    parser = argparse.ArgumentParser(
        description="Find best possible email from LinkedIn profile URL"
    )
    parser.add_argument("--linkedin-url", required=True, help="LinkedIn profile URL")
    parser.add_argument(
        "--company",
        default="",
        help="Company name override (recommended if headline doesn't contain company)",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="Company domain override (most reliable), e.g. openai.com",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Open visible browser for LinkedIn challenge/manual verification",
    )
    parser.add_argument(
        "--save-notion",
        action="store_true",
        help="Save resolved contact to Notion Contacts DB",
    )
    args = parser.parse_args()

    out = asyncio.run(
        run_lookup(
            linkedin_url=args.linkedin_url,
            company_override=args.company,
            domain_override=args.domain,
            headful=args.headful,
            save_notion=args.save_notion,
        )
    )

    print("\n=== LINKEDIN EMAIL LOOKUP ===\n")
    print(f"Name:       {out.get('name', '')}")
    print(f"Company:    {out.get('company', '')}")
    print(f"Domain:     {out.get('domain', '')}")
    print(f"Headline:   {out.get('headline', '')}")
    print(f"LinkedIn:   {out.get('linkedin_url', '')}")
    print("")
    print(f"Best email: {out.get('email', '')}")
    print(f"Confidence: {out.get('confidence', '')}")
    print(f"Method:     {out.get('method', '')}")
    print("")
    print("Candidates:")
    for c in out.get("candidates", []):
        marker = " <- selected" if c == out.get("email", "") else ""
        print(f"  - {c}{marker}")


if __name__ == "__main__":
    main()
