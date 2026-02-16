"""
LinkedIn People Finder: search for HR / recruiters / managers at a target company.
Reuses the LinkedIn Playwright session from the post scraper.
"""

import logging
import re
from typing import Optional
from urllib.parse import quote

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROLE_FILTERS = [
    "hr", "recruiter", "talent", "hiring manager",
    "engineering manager", "head of engineering",
    "cto", "founder", "co-founder", "vp engineering",
    "people operations", "talent acquisition",
]


class ContactFinder(BaseScraper):
    """Find HR/hiring contacts at a company via LinkedIn People search."""

    PLATFORM = "linkedin"

    def __init__(
        self,
        browser_data_dir: str = "./browser_data/linkedin",
        headless: bool = True,
        contacts_per_company: int = 5,
        daily_quota: int = 80,
    ):
        super().__init__(browser_data_dir, headless=headless, daily_quota=daily_quota)
        self.contacts_per_company = contacts_per_company

    async def scrape(self) -> list[dict]:
        """Not used directly; use find_contacts instead."""
        return []

    async def find_contacts(self, company_name: str) -> list[dict]:
        """
        Search LinkedIn People for relevant contacts at the given company.
        Returns list of dicts with: name, role_title, linkedin_url
        """
        if not self.check_quota():
            return []

        query = f'"{company_name}" recruiter OR HR OR "hiring manager" OR "engineering manager"'
        encoded = quote(query)
        url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
        )

        logger.info("[linkedin-people] Searching contacts at: %s", company_name)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(3, 6)
        self.increment_quota()

        contacts: list[dict] = []
        seen_urls: set[str] = set()

        cards = await self.page.query_selector_all(
            "li.reusable-search__result-container"
        )
        if not cards:
            cards = await self.page.query_selector_all(
                "div.entity-result"
            )

        for card in cards:
            if len(contacts) >= self.contacts_per_company:
                break

            try:
                parsed = await self._parse_person_card(card)
                if not parsed:
                    continue

                if not self._is_relevant_role(parsed.get("role_title", "")):
                    continue

                li_url = parsed.get("linkedin_url", "")
                if li_url in seen_urls:
                    continue
                seen_urls.add(li_url)
                contacts.append(parsed)

            except Exception as exc:
                logger.debug("[linkedin-people] Parse error: %s", exc)

        logger.info(
            "[linkedin-people] Found %d contacts at %s", len(contacts), company_name
        )
        return contacts

    async def _parse_person_card(self, card) -> Optional[dict]:
        """Extract name, title, and profile URL from a search result card."""
        name_el = await card.query_selector(
            "span.entity-result__title-text a span[aria-hidden='true'], "
            "span.entity-result__title-text a"
        )
        name = (await name_el.inner_text()).strip() if name_el else ""
        if not name or name.lower() == "linkedin member":
            return None

        link_el = await card.query_selector(
            "span.entity-result__title-text a[href*='/in/']"
        )
        linkedin_url = ""
        if link_el:
            href = await link_el.get_attribute("href") or ""
            if href.startswith("/"):
                href = f"https://www.linkedin.com{href}"
            linkedin_url = href.split("?")[0]

        title_el = await card.query_selector(
            "div.entity-result__primary-subtitle"
        )
        role_title = (await title_el.inner_text()).strip() if title_el else ""

        return {
            "name": name,
            "role_title": role_title,
            "linkedin_url": linkedin_url,
        }

    @staticmethod
    def _is_relevant_role(title: str) -> bool:
        """Check if the person's title matches our target roles."""
        lower = title.lower()
        return any(role in lower for role in ROLE_FILTERS)
