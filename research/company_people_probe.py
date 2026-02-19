"""
Reusable company-page LinkedIn people probe.

Used in two places:
- CLI utility scripts (manual debugging/probing)
- Automatic pipeline fallback when normal LinkedIn people search returns 0
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import unquote, urlparse, parse_qs

import requests
import yaml
from bs4 import BeautifulSoup

from research.accurate_email_finder import AccurateEmailFinder
from research.company_variants import get_company_name_variants
from research.domain_finder import DomainFinder
from scrapers.base_scraper import BaseScraper
from storage.notion_client import NotionStorage

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# Common single first names — used to filter out person-name leads.
_COMMON_FIRST_NAMES = {
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "mary", "patricia", "jennifer", "linda",
    "barbara", "elizabeth", "susan", "jessica", "sarah", "karen", "lauryn",
    "laura", "emily", "emma", "olivia", "ava", "sophia", "isabella", "mia",
    "charlotte", "amelia", "harper", "evelyn", "abigail", "emily", "ella",
    "daniel", "matthew", "anthony", "mark", "donald", "steven", "paul",
    "andrew", "joshua", "kevin", "brian", "george", "timothy", "ronald",
    "edward", "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas",
    "eric", "jonathan", "stephen", "larry", "justin", "scott", "brandon",
    "raymond", "frank", "gregory", "samuel", "benjamin", "patrick",
    "jack", "alex", "peter", "henry", "adam", "nathan", "zachary", "tyler",
    "noah", "ethan", "liam", "mason", "oliver", "lucas", "aiden", "carter",
    "sebastian", "finn", "owen", "julian", "gabriel", "angel", "dylan",
    "ryan", "leo", "aaron", "eli",
}

# Company name suffixes that confirm it is a company, not a person.
_COMPANY_SUFFIXES = {
    "ai", "inc", "llc", "ltd", "corp", "technologies", "tech", "labs",
    "solutions", "systems", "group", "platform", "platforms", "health",
    "finance", "capital", "ventures", "studio", "studios",
}


def is_valid_company_name(name: str) -> bool:
    """
    Return False if the name looks like a person's first name or is too
    short/generic to be a meaningful company name.
    """
    name = name.strip()
    if len(name) < 3:
        return False
    words = name.lower().split()
    if not words:
        return False
    # Single-word names that match a known first name are probably persons.
    if len(words) == 1 and words[0] in _COMMON_FIRST_NAMES:
        return False
    # Single short word with no company suffix signals — likely a person.
    if len(words) == 1 and len(words[0]) <= 6:
        # Allow if it has a digit (e.g. "h2o") or matches a company suffix.
        has_digit = any(c.isdigit() for c in words[0])
        is_suffix = words[0] in _COMPANY_SUFFIXES
        if not has_digit and not is_suffix:
            return False
    return True


def _extract_linkedin_company_url(text: str) -> str:
    """
    Extract a LinkedIn company URL from arbitrary text/href, handling
    DuckDuckGo redirect wrappers like:
      https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Fopenai%2F
    """
    # First try URL-decoded version.
    decoded = unquote(text)
    match = re.search(
        r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[^/?#\s]+",
        decoded,
    )
    if match:
        url = match.group(0).rstrip("/")
        return url + "/"

    # Try extracting the uddg= query param value (DuckDuckGo redirect).
    try:
        parsed = urlparse(text)
        params = parse_qs(parsed.query)
        for key in ("uddg", "u", "url"):
            vals = params.get(key, [])
            if vals:
                inner = unquote(vals[0])
                match = re.search(
                    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[^/?#\s]+",
                    inner,
                )
                if match:
                    url = match.group(0).rstrip("/")
                    return url + "/"
    except Exception:
        pass

    return ""


def _discover_linkedin_url_for_name(search_name: str) -> str:
    """Try DuckDuckGo then Google for one company name. Returns URL or \"\"."""
    q = f"site:linkedin.com/company {search_name}"
    ddg_url = f"https://html.duckduckgo.com/html/?q={requests.utils.requote_uri(q)}"
    try:
        resp = requests.get(ddg_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a.result__a[href], a[href]"):
                href = a.get("href", "")
                found = _extract_linkedin_company_url(href)
                if found:
                    return found
            found = _extract_linkedin_company_url(resp.text)
            if found:
                return found
    except Exception as exc:
        logger.debug("DuckDuckGo company search failed for '%s': %s", search_name, exc)

    g_q = f'site:linkedin.com/company "{search_name}"'
    google_url = f"https://www.google.com/search?q={requests.utils.requote_uri(g_q)}&num=5"
    try:
        resp = requests.get(google_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                found = _extract_linkedin_company_url(href)
                if found:
                    return found
    except Exception as exc:
        logger.debug("Google company search failed for '%s': %s", search_name, exc)

    return ""


def discover_company_linkedin_url(company_name: str) -> str:
    """
    Find a LinkedIn company page URL for a company name.

    Tries the name and variants (e.g. "Tactful AI" -> also "Tactful") so we
    match when X uses @Tactfulai but LinkedIn lists the company as "Tactful".
    Strategy: for each variant, DuckDuckGo then Google; return first found.
    """
    variants = get_company_name_variants(company_name)
    if not variants:
        return ""

    for search_name in variants:
        found = _discover_linkedin_url_for_name(search_name)
        if found:
            if search_name != (variants[0] or "").strip():
                logger.info(
                    "Discovered LinkedIn URL for '%s' via variant '%s': %s",
                    company_name, search_name, found,
                )
            else:
                logger.info(
                    "Discovered LinkedIn URL for '%s' via DuckDuckGo/Google: %s",
                    company_name, found,
                )
            return found

    logger.warning(
        "Could not discover LinkedIn company URL for '%s' (tried variants: %s). "
        "Browser fallback will be tried during run_probe.",
        company_name, variants,
    )
    return ""


# Role search terms used on the company People tab, in priority order.
# We search for these one at a time until we have enough profiles.
PEOPLE_SEARCH_TERMS = [
    "recruiter",
    "technical recruiter",
    "talent acquisition",
    "hiring manager",
    "engineering manager",
    "head of engineering",
    "head of talent",
    "find talent",
]

_RECRUITER_HEADLINE_MARKERS = [
    "recruiter", "recruiting", "talent acquisition", "talent partner",
    "hiring manager", "hr ", "hr manager", "human resources",
    "people operations", "people partner",
    "head of talent", "head of recruiting", "head of people",
    "staffing", "sourcer", "sourcing",
    "engineering manager", "head of engineering",
    "director of engineering",
    "find talent",
]


def _is_hiring_relevant_headline(headline: str) -> bool:
    lower = headline.lower()
    return any(m in lower for m in _RECRUITER_HEADLINE_MARKERS)


class LinkedInCompanyPeopleProbe(BaseScraper):
    PLATFORM = "linkedin"

    async def scrape(self) -> list[dict]:
        return []

    async def get_company_name(self, company_url: str) -> str:
        await self.page.goto(company_url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(2, 4)

        try:
            text = (await self.page.inner_text("body")).lower()
            if any(x in text for x in ["checkpoint", "verify", "security verification"]):
                raise RuntimeError(
                    "LinkedIn verification/checkpoint page detected. Run in headful mode."
                )
        except RuntimeError:
            raise
        except Exception:
            pass

        selectors = [
            "h1.org-top-card-summary__title",
            "h1.top-card-layout__title",
            "main h1",
            "h1",
        ]
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if not el:
                    continue
                name = (await el.inner_text()).strip()
                if name:
                    return re.sub(r"\s+", " ", name)
            except Exception:
                continue
        return ""

    async def get_people_links(self, company_url: str, limit: int) -> list[str]:
        """
        Search the company People tab for recruiters / hiring managers and
        return profile links found in the actual people result cards.

        Strategy:
        - For each role keyword in PEOPLE_SEARCH_TERMS, navigate to
          /company/<slug>/people/?keywords=<term>
        - Extract links ONLY from people result cards (not nav, sidebar, footer)
        - Stop once we have `limit` unique profiles
        """
        collected: list[str] = []
        seen: set[str] = set()
        base = company_url.rstrip("/")

        for term in PEOPLE_SEARCH_TERMS:
            if len(collected) >= limit:
                break

            search_url = f"{base}/people/?keywords={requests.utils.requote_uri(term)}"
            logger.info("People search: %s", search_url)
            try:
                await self.page.goto(
                    search_url, wait_until="domcontentloaded", timeout=60_000
                )
                await self.random_delay(2, 4)
            except Exception as exc:
                logger.debug("Navigation failed for term '%s': %s", term, exc)
                continue

            # Checkpoint guard
            try:
                body_text = (await self.page.inner_text("body")).lower()
                if any(
                    x in body_text
                    for x in ["checkpoint", "verify", "security verification"]
                ):
                    logger.warning(
                        "LinkedIn checkpoint on people search for '%s'; stopping.", term
                    )
                    break
            except Exception:
                pass

            # Scroll to reveal lazy-loaded cards
            await self.scroll_to_bottom()
            await self.random_delay(1, 3)

            links = await self._extract_people_card_links()
            new = [lnk for lnk in links if lnk not in seen]
            seen.update(new)
            collected.extend(new)
            logger.info(
                "People search '%s': +%d new profiles (total %d)",
                term, len(new), len(collected),
            )

        return collected[:limit]

    async def get_any_people_links(self, company_url: str, limit: int = 3) -> list[str]:
        """
        Get up to `limit` profile links from the company People tab without
        any keyword filter. Used when no recruiter/hiring/find-talent
        profiles were found, so we store 2-3 arbitrary contacts.
        """
        base = company_url.rstrip("/")
        search_url = f"{base}/people/"
        logger.info("People fallback (any): %s (limit=%d)", search_url, limit)
        try:
            await self.page.goto(
                search_url, wait_until="domcontentloaded", timeout=60_000
            )
            await self.random_delay(2, 4)
        except Exception as exc:
            logger.debug("Navigation failed for people fallback: %s", exc)
            return []

        try:
            body_text = (await self.page.inner_text("body")).lower()
            if any(
                x in body_text
                for x in ["checkpoint", "verify", "security verification"]
            ):
                logger.warning("LinkedIn checkpoint on people fallback; skipping.")
                return []
        except Exception:
            pass

        await self.scroll_to_bottom()
        await self.random_delay(1, 3)
        links = await self._extract_people_card_links()
        return links[:limit]

    async def _extract_people_card_links(self) -> list[str]:
        """
        Extract /in/ profile links from people result cards ONLY.

        LinkedIn company people page card containers (tried in order):
          - ul.org-people-profiles-module__profile-list > li  (classic)
          - ul[class*="org-people__profile-list"] > li
          - .org-people-profile-card  (individual card)
          - [data-test-org-people-profile-card]
        Fallback: all /in/ links inside <main>, excluding the global nav bar.
        """
        script = r"""
        (() => {
          const out = [];
          const seen = new Set();

          function addHref(href) {
            if (!href || !href.includes('/in/')) return;
            if (href.startsWith('/')) href = 'https://www.linkedin.com' + href;
            href = href.split('?')[0].split('#')[0];
            // Skip bare /in/ and nav-only links
            const slug = href.replace(/.*\/in\//, '').replace(/\/$/, '');
            if (!slug || slug.length < 2) return;
            if (!seen.has(href)) { seen.add(href); out.push(href); }
          }

          // --- Scoped card selectors (most specific first) ---
          const cardSelectors = [
            'ul.org-people-profiles-module__profile-list li a[href*="/in/"]',
            'ul[class*="org-people__profile-list"] li a[href*="/in/"]',
            '.org-people-profile-card a[href*="/in/"]',
            '[data-test-org-people-profile-card] a[href*="/in/"]',
            'section[class*="org-people"] a[href*="/in/"]',
            '.artdeco-card a[href*="/in/"]',
          ];

          let found = false;
          for (const sel of cardSelectors) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
              els.forEach(a => addHref(a.href || a.getAttribute('href') || ''));
              found = true;
            }
          }

          // --- Fallback: main content /in/ links (excludes global nav) ---
          if (!found || out.length === 0) {
            const main = (
              document.querySelector('main') ||
              document.querySelector('#main-content') ||
              document.body
            );
            // Exclude top global-nav element if present
            const nav = document.querySelector('header nav, #global-nav');
            main.querySelectorAll('a[href*="/in/"]').forEach(a => {
              if (nav && nav.contains(a)) return;
              addHref(a.href || a.getAttribute('href') || '');
            });
          }

          return out;
        })();
        """
        try:
            links = await self.page.evaluate(script)
        except Exception:
            return []
        return links or []

    async def read_profile(self, profile_url: str) -> dict:
        await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(2, 4)
        name = await self._first_text(["h1.text-heading-xlarge", "main h1", "h1"])
        headline = await self._first_text(["div.text-body-medium.break-words", "div.text-body-medium"])
        return {
            "name": self._clean_name(name),
            "headline": (headline or "").strip(),
            "linkedin_url": profile_url,
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

    @staticmethod
    def _clean_name(name: str) -> str:
        name = re.sub(r"\s+", " ", name or "").strip()
        return re.sub(r"[^\w\s\-'.À-ÿ]", "", name).strip()

    async def find_company_url_via_browser(self, company_name: str) -> str:
        """
        Search for a company LinkedIn page URL using the already-open,
        logged-in Playwright session.  Navigates to LinkedIn company search
        and returns the first result URL.
        """
        search_url = (
            "https://www.linkedin.com/search/results/companies/"
            f"?keywords={requests.utils.requote_uri(company_name)}"
        )
        try:
            await self.page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            await self.random_delay(2, 4)

            body = (await self.page.inner_text("body")).lower()
            if any(x in body for x in ["checkpoint", "verify", "security verification"]):
                logger.warning(
                    "LinkedIn checkpoint encountered during browser company search for '%s'",
                    company_name,
                )
                return ""

            # Extract the first company page link from the results.
            script = r"""
            (() => {
              const seen = new Set();
              for (const a of document.querySelectorAll('a[href*="/company/"]')) {
                const href = a.href || '';
                const m = href.match(/https?:\/\/(?:[a-z]{2,3}\.)?linkedin\.com\/company\/([^/?#]+)/);
                if (!m) continue;
                const url = 'https://www.linkedin.com/company/' + m[1] + '/';
                if (!seen.has(url)) { seen.add(url); return url; }
              }
              return '';
            })();
            """
            url = await self.page.evaluate(script)
            if url:
                logger.info(
                    "Discovered LinkedIn URL for '%s' via browser search: %s",
                    company_name, url,
                )
                return url
        except Exception as exc:
            logger.debug(
                "Browser LinkedIn company search failed for '%s': %s", company_name, exc
            )
        return ""


async def run_probe(
    company_url: str,
    limit: int = 5,
    domain_override: str = "",
    headful: bool = False,
    save_notion: bool = False,
    company_name_hint: str = "",
) -> list[dict]:
    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)
    li_cfg = cfg["scraping"]["linkedin"]
    headless = False if headful else cfg["scraping"].get("headless", True)

    probe = LinkedInCompanyPeopleProbe(
        browser_data_dir=li_cfg["browser_data_dir"],
        headless=headless,
        daily_quota=li_cfg["daily_action_quota"],
    )

    await probe.start()
    try:
        await probe.ensure_logged_in("https://www.linkedin.com/feed/", "feed")

        # If no company_url was supplied by the caller (HTTP search failed),
        # try browser-based LinkedIn company search using hint and its variants.
        if not company_url and company_name_hint:
            logger.info(
                "HTTP URL discovery failed for '%s'; trying browser search with name variants.",
                company_name_hint,
            )
            for search_name in get_company_name_variants(company_name_hint):
                company_url = await probe.find_company_url_via_browser(search_name)
                if company_url:
                    if search_name != (company_name_hint or "").strip():
                        logger.info(
                            "Resolved company via variant '%s': %s",
                            search_name, company_url,
                        )
                    break
            if not company_url:
                raise RuntimeError(
                    f"Could not resolve LinkedIn company URL for '{company_name_hint}' "
                    "via HTTP search or browser fallback (tried name variants)."
                )

        company_name = await probe.get_company_name(company_url)
        if not company_name:
            slug = company_url.rstrip("/").split("/company/")[-1].split("/")[0]
            slug = re.sub(r"[-_]+", " ", slug).strip()
            company_name = slug.title() if slug else "Unknown"

        domain = domain_override or (DomainFinder().find_domain(company_name) or "")
        if not domain:
            raise RuntimeError("Could not resolve company domain. Pass --domain explicitly.")

        profile_links = await probe.get_people_links(company_url, limit=limit * 3)
        require_recruiter_headline = True
        if not profile_links:
            # No recruiter/hiring/find-talent found: get any 2-3 people and store emails
            fallback_limit = min(3, max(1, limit))
            profile_links = await probe.get_any_people_links(company_url, limit=fallback_limit)
            if not profile_links:
                raise RuntimeError("No profile links found on company People tab.")
            require_recruiter_headline = False
            logger.info(
                "No recruiter/hiring/find-talent profiles; storing up to %d any-role contacts.",
                fallback_limit,
            )

        finder = AccurateEmailFinder()
        results: list[dict] = []
        seen = set()
        max_results = limit if require_recruiter_headline else min(3, max(1, limit))

        for url in profile_links:
            if len(results) >= max_results:
                break
            if url in seen:
                continue
            seen.add(url)
            try:
                profile = await probe.read_profile(url)
                name = profile.get("name", "")
                if not name:
                    continue
                headline = profile.get("headline", "")
                if require_recruiter_headline and headline and not _is_hiring_relevant_headline(headline):
                    logger.debug(
                        "Skipping non-recruiter/hiring profile: %s (%s)", name, headline,
                    )
                    continue
                email_result = finder.find_best_email(
                    full_name=name,
                    company_domain=domain,
                    company_name=company_name,
                    linkedin_url=url,
                )
                email = email_result.get("email", "")
                if not email:
                    continue
                results.append(
                    {
                        "name": name,
                        "headline": headline,
                        "linkedin_url": url,
                        "email": email,
                        "confidence": email_result.get("confidence", "low"),
                        "method": email_result.get("method", ""),
                        "company_name": company_name,
                        "domain": domain,
                    }
                )
            except Exception:
                continue

        if save_notion and results:
            notion = NotionStorage()
            notion.ensure_schemas()
            saved = 0
            first_error: Optional[str] = None
            for row in results:
                email = row.get("email", "")
                if not email:
                    logger.debug("Skipping contact with no email: %s", row.get("name"))
                    continue
                if notion.contact_exists(email):
                    logger.info("Contact already in Notion (skipping): %s", email)
                    continue
                try:
                    notion.add_contact(
                        {
                            "name": row.get("name", ""),
                            "email": email,
                            "role_title": row.get("headline", ""),
                            "company_name": row.get("company_name", ""),
                            "email_confidence": row.get("confidence", "low"),
                            "linkedin_url": row.get("linkedin_url", ""),
                        }
                    )
                    saved += 1
                except Exception as exc:
                    err_msg = str(exc)
                    if first_error is None:
                        first_error = err_msg
                    logger.warning(
                        "Could not save contact %s (%s) to Notion: %s",
                        row.get("name", ""),
                        email,
                        exc,
                    )
            if saved < len(results):
                logger.warning(
                    "Saved %d of %d contacts to Notion (check Contacts DB schema if some failed).",
                    saved,
                    len(results),
                )
                if first_error and saved == 0:
                    logger.warning("First Notion error was: %s", first_error)
            else:
                logger.info("Saved %d contact(s) to Notion.", saved)
        return results
    finally:
        try:
            await probe.stop()
        except Exception:
            pass
