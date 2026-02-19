"""
LinkedIn People Finder: search for HR / recruiters / managers at a target company.
Reuses the LinkedIn Playwright session from the post scraper.

Major design decisions:
 - Two search passes: first a role-specific search, then a broader company-only
   search as fallback so we always return at least some people.
 - Multiple CSS selector strategies for parsing cards because LinkedIn constantly
   changes their markup.
 - Role filtering is lenient in "managers" mode — if the strict filter finds
   fewer than the target, a second pass accepts anyone at the company.
"""

import logging
import re
from typing import Optional
from urllib.parse import quote

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

ROLE_FILTERS = [
    "recruiter", "recruiting", "talent acquisition", "talent partner",
    "hiring manager", "hr ", "hr manager", "human resources",
    "people operations", "people partner",
    "head of talent", "head of recruiting", "head of people",
    "staffing", "sourcer", "sourcing",
    "engineering manager", "head of engineering",
]

MANAGER_FILTERS = [
    "recruiter", "recruiting", "talent acquisition", "talent partner",
    "hiring manager", "hr ", "hr manager", "human resources",
    "people operations", "people partner",
    "head of talent", "head of recruiting", "head of people",
    "staffing", "sourcer", "sourcing",
    "engineering manager", "head of engineering",
    "head of ai", "head of ml",
    "director of engineering", "director of ai", "director of ml",
]

# Selectors to try (LinkedIn changes markup frequently)
CARD_SELECTORS = [
    "li.reusable-search__result-container",
    "div.entity-result",
    "ul.reusable-search__entity-result-list li",
    "main li",
    "li.search-result",
    "div.search-result__wrapper",
    "li[class*='result']",
]

NAME_SELECTORS = [
    "span.entity-result__title-text a span[aria-hidden='true']",
    "span.entity-result__title-text a span[dir='ltr']",
    "span.entity-result__title-text a",
    "a.app-aware-link span[aria-hidden='true']",
    "a[href*='/in/'] span",
    "a[href*='/in/']",
]

LINK_SELECTORS = [
    "span.entity-result__title-text a[href*='/in/']",
    "a.app-aware-link[href*='/in/']",
    "a[href*='/in/']",
]

TITLE_SELECTORS = [
    "div.entity-result__primary-subtitle",
    "p.entity-result__summary",
    "div.entity-result__summary",
    "p.subline-level-1",
    "div.search-result__info div.subline-level-1",
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

    async def find_contacts(self, company_name: str, search_mode: str = "default") -> list[dict]:
        """
        Search LinkedIn People for relevant contacts at the given company.

        Two-pass strategy:
          Pass 1 — role-specific query (managers/recruiters)
          Pass 2 — broad company-only query if Pass 1 found fewer than target

        Returns list of dicts with: name, role_title, linkedin_url, company_name
        """
        if not self.check_quota():
            return []

        contacts: list[dict] = []
        seen_urls: set[str] = set()

        # ---- Pass 1: role-specific search ----
        if search_mode == "managers":
            query = (
                f'"{company_name}" "hiring manager" OR "engineering manager" '
                f'OR "recruiter" OR "talent acquisition" OR "director of engineering"'
            )
            role_filter = MANAGER_FILTERS
        else:
            query = (
                f'"{company_name}" recruiter OR "talent acquisition" '
                f'OR "hiring manager" OR "engineering manager" OR HR'
            )
            role_filter = ROLE_FILTERS

        logger.info(
            "[linkedin-people] Pass 1: role-specific search at %s (mode=%s)",
            company_name, search_mode,
        )
        pass1 = await self._search_and_collect(
            query, company_name, role_filter,
            contacts, seen_urls, strict_filter=True,
        )
        contacts = pass1

        # ---- Pass 2: broad company search (still filtered to relevant roles) ----
        if len(contacts) < self.contacts_per_company:
            logger.info(
                "[linkedin-people] Pass 2: broad search for %s (have %d, need %d)",
                company_name, len(contacts), self.contacts_per_company,
            )
            broad_query = f'"{company_name}" recruiter OR "talent" OR "hiring" OR "HR"'
            pass2 = await self._search_and_collect(
                broad_query, company_name, role_filter,
                contacts, seen_urls, strict_filter=True,
            )
            contacts = pass2

        logger.info(
            "[linkedin-people] Found %d contacts at %s", len(contacts), company_name,
        )
        return contacts

    async def _search_and_collect(
        self,
        query: str,
        company_name: str,
        role_filter: list[str],
        existing: list[dict],
        seen_urls: set[str],
        strict_filter: bool,
    ) -> list[dict]:
        """Execute a LinkedIn People search and collect results."""
        if not self.check_quota():
            return existing

        encoded = quote(query)
        url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
        )

        logger.info("[linkedin-people] Navigating to: %s", url[:120])
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(3, 6)
        self.increment_quota()

        # Wait for results to render
        for sel in CARD_SELECTORS[:2]:
            try:
                await self.page.wait_for_selector(sel, timeout=8_000)
                break
            except Exception:
                continue

        contacts = list(existing)

        for page_num in range(1, 4):
            if len(contacts) >= self.contacts_per_company:
                break

            cards = await self._find_cards()

            if not cards:
                logger.warning(
                    "[linkedin-people] No result cards found on page %d "
                    "(may be logged out or LinkedIn changed layout)",
                    page_num,
                )
                # Detect challenge/checkpoint pages explicitly.
                try:
                    body = (await self.page.inner_text("body")).lower()
                    if any(k in body for k in ["checkpoint", "verify", "security verification", "unusual activity"]):
                        logger.warning(
                            "[linkedin-people] LinkedIn checkpoint/verification detected. "
                            "Session may require manual verification in non-headless mode."
                        )
                except Exception:
                    pass

                # Fallback extraction: parse raw /in/ links directly from page.
                fallback_people = await self._extract_people_from_links(company_name)
                if fallback_people:
                    logger.info(
                        "[linkedin-people] Fallback link extraction found %d candidates on page %d",
                        len(fallback_people),
                        page_num,
                    )
                    for parsed in fallback_people:
                        if len(contacts) >= self.contacts_per_company:
                            break
                        li_url = parsed.get("linkedin_url", "")
                        if li_url and li_url in seen_urls:
                            continue
                        title = parsed.get("role_title", "")
                        if strict_filter and not self._matches_role_filter(title, role_filter):
                            continue
                        if li_url:
                            seen_urls.add(li_url)
                        parsed["company_name"] = company_name
                        contacts.append(parsed)
                        logger.info(
                            "[linkedin-people]   + %s | %s",
                            parsed.get("name", ""),
                            parsed.get("role_title", ""),
                        )
                    if len(contacts) >= self.contacts_per_company:
                        break

                # Capture the page for debugging
                try:
                    page_text = await self.page.inner_text("body")
                    snippet = page_text[:500].replace("\n", " ")
                    logger.debug("[linkedin-people] Page body snippet: %s", snippet)
                except Exception:
                    pass
                break

            logger.info(
                "[linkedin-people] Page %d: found %d cards", page_num, len(cards),
            )

            parsed_on_page = 0
            for card in cards:
                if len(contacts) >= self.contacts_per_company:
                    break

                try:
                    parsed = await self._parse_person_card(card)
                    if not parsed:
                        continue

                    li_url = parsed.get("linkedin_url", "")
                    if li_url and li_url in seen_urls:
                        continue

                    title = parsed.get("role_title", "")

                    if strict_filter:
                        if not self._matches_role_filter(title, role_filter):
                            continue

                    if li_url:
                        seen_urls.add(li_url)
                    parsed["company_name"] = company_name
                    contacts.append(parsed)
                    parsed_on_page += 1
                    logger.info(
                        "[linkedin-people]   + %s | %s",
                        parsed["name"], parsed["role_title"],
                    )

                except Exception as exc:
                    logger.debug("[linkedin-people] Parse error: %s", exc)

            # If card parser couldn't extract anyone, fall back to raw /in/ links.
            if parsed_on_page == 0 and len(contacts) < self.contacts_per_company:
                fallback_people = await self._extract_people_from_links(company_name)
                if fallback_people:
                    logger.info(
                        "[linkedin-people] Card parsing yielded 0; fallback extracted %d profiles",
                        len(fallback_people),
                    )
                    for parsed in fallback_people:
                        if len(contacts) >= self.contacts_per_company:
                            break
                        li_url = parsed.get("linkedin_url", "")
                        if li_url and li_url in seen_urls:
                            continue
                        title = parsed.get("role_title", "")
                        if strict_filter and not self._matches_role_filter(title, role_filter):
                            continue
                        if li_url:
                            seen_urls.add(li_url)
                        parsed["company_name"] = company_name
                        contacts.append(parsed)
                        logger.info(
                            "[linkedin-people]   + %s | %s",
                            parsed.get("name", ""),
                            parsed.get("role_title", ""),
                        )

            if len(contacts) >= self.contacts_per_company:
                break

            # Try next page
            next_btn = await self.page.query_selector(
                "button.artdeco-pagination__button--next:not([disabled])"
            )
            if not next_btn:
                break
            await next_btn.click()
            await self.random_delay(3, 6)
            self.increment_quota()

        return contacts

    async def _find_cards(self) -> list:
        """Try multiple CSS selectors to find result cards."""
        for sel in CARD_SELECTORS:
            cards = await self.page.query_selector_all(sel)
            if cards:
                return cards
        return []

    async def _extract_people_from_links(self, company_name: str) -> list[dict]:
        """
        Fallback parser when LinkedIn result-card selectors fail.
        Extracts /in/ links and nearby text from the page.
        """
        script = """
        (() => {
          const anchors = Array.from(document.querySelectorAll('a[href*="/in/"]'));
          const seen = new Set();
          const rows = [];
          for (const a of anchors) {
            let href = a.getAttribute('href') || '';
            if (!href.includes('/in/')) continue;
            if (href.startsWith('/')) href = 'https://www.linkedin.com' + href;
            href = href.split('?')[0];
            if (seen.has(href)) continue;
            seen.add(href);

            const name = (a.textContent || '').trim();
            const container = a.closest('li, div, article, section') || a.parentElement;
            const text = ((container && container.textContent) || '').replace(/\\s+/g, ' ').trim();
            rows.push({ href, name, text });
          }
          return rows.slice(0, 200);
        })();
        """
        try:
            rows = await self.page.evaluate(script)
        except Exception:
            return []

        people: list[dict] = []
        for row in rows or []:
            href = (row.get("href") or "").strip()
            if not href or "/in/" not in href:
                continue

            name = (row.get("name") or "").strip()
            text = (row.get("text") or "").strip()
            if not name:
                # Infer name from profile slug.
                slug = href.rstrip("/").split("/in/")[-1]
                slug = slug.split("/")[0]
                slug = re.sub(r"[-_]+", " ", slug)
                slug = re.sub(r"\d+", "", slug).strip()
                name = slug.title() if slug else ""
            if not name:
                continue

            # Infer role as line after name in nearby text, else fallback to text snippet.
            role_title = ""
            if text:
                # Remove duplicated name in text then keep short prefix.
                cleaned = text.replace(name, "").strip(" -|")
                role_title = cleaned[:120]

            people.append(
                {
                    "name": name,
                    "role_title": role_title,
                    "linkedin_url": href,
                    "company_name": company_name,
                }
            )

        # Dedup by URL
        dedup: dict[str, dict] = {}
        for p in people:
            dedup[p["linkedin_url"]] = p
        return list(dedup.values())

    async def _parse_person_card(self, card) -> Optional[dict]:
        """Extract name, title, and profile URL from a search result card."""

        # First extract URL so we can infer name from slug if needed.
        linkedin_url = ""
        for sel in LINK_SELECTORS:
            el = await card.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                if "/in/" in href:
                    if href.startswith("/"):
                        href = f"https://www.linkedin.com{href}"
                    linkedin_url = href.split("?")[0]
                    break

        # ---- Name ----
        name = ""
        for sel in NAME_SELECTORS:
            el = await card.query_selector(sel)
            if el:
                name = (await el.inner_text()).strip()
                if name and name.lower() != "linkedin member":
                    break
                name = ""

        # Fallback: infer name from profile slug when visible name selector fails.
        if not name and linkedin_url:
            slug = linkedin_url.rstrip("/").split("/in/")[-1].split("/")[0]
            slug = re.sub(r"[-_]+", " ", slug)
            slug = re.sub(r"\d+", "", slug).strip()
            if slug:
                name = slug.title()

        if not name:
            # Last resort: first text line from the card.
            try:
                text = (await card.inner_text()).strip()
                first_line = text.split("\n")[0].strip() if text else ""
                if first_line and len(first_line) <= 80:
                    name = first_line
            except Exception:
                pass

        if not name:
            return None

        # Clean name: remove emojis, extra whitespace, accreditations
        name = re.sub(r"[^\w\s\-'.À-ÿ]", "", name, flags=re.UNICODE).strip()
        name = re.sub(r"\s+", " ", name)

        if not name or name.lower() == "linkedin member":
            return None

        # ---- Role/Title ----
        role_title = ""
        for sel in TITLE_SELECTORS:
            el = await card.query_selector(sel)
            if el:
                role_title = (await el.inner_text()).strip()
                if role_title:
                    break

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

    @staticmethod
    def _matches_role_filter(title: str, filters: list[str]) -> bool:
        """Check if the person's title matches any of the given role filters."""
        lower = title.lower()
        return any(role in lower for role in filters)
