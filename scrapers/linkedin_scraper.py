"""
LinkedIn post scraper — two distinct flows:

  1. **Funding posts**: Recent funding/investment announcements for AI/ML
     companies.  No contentType filter (these are regular posts, not job
     listings).  Company name is extracted from the post text.

  2. **Job posts**: Hiring announcements (LinkedIn contentType=job).  After
     collection, the scraper visits each poster's profile to resolve the
     company they work at — this is the most reliable signal because many
     job posts are shared by individual recruiters / managers, not by the
     company page itself.

Both flows feed into the same downstream pipeline:
  company → find recruiter / hiring-manager contacts → email scrape.
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInPostScraper(BaseScraper):
    PLATFORM = "linkedin"

    FUNDING_QUERIES = [
        "raised funding artificial intelligence",
        "series A AI startup",
        "AI company funding round",
        "machine learning startup raised",
    ]

    JOB_QUERIES = [
        "hiring AI ML engineer",
        "looking for machine learning engineer",
        "LLM engineer hiring",
        "AI engineer open role",
        "ML engineer position",
    ]

    def __init__(
        self,
        browser_data_dir: str = "./browser_data/linkedin",
        headless: bool = True,
        max_posts: int = 40,
        max_scrolls: int = 10,
        scroll_delay_min: float = 3.0,
        scroll_delay_max: float = 8.0,
        daily_quota: int = 80,
    ):
        super().__init__(browser_data_dir, headless=headless, daily_quota=daily_quota)
        self.max_posts = max_posts
        self.max_scrolls = max_scrolls
        self.scroll_delay_min = scroll_delay_min
        self.scroll_delay_max = scroll_delay_max

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict]:
        """Scrape LinkedIn for funding posts and job posts (last 24 h)."""
        await self.start()
        try:
            await self.ensure_logged_in("https://www.linkedin.com/feed/", "feed")
            all_posts: list[dict] = []
            seen_fingerprints: set[str] = set()

            # ---- Flow 1: Funding posts (no contentType filter) ----
            for query in self.FUNDING_QUERIES:
                if not self.check_quota() or len(all_posts) >= self.max_posts:
                    break
                posts = await self._search_posts(query, seen_fingerprints, content_type="")
                for p in posts:
                    p["scrape_type"] = "funding"
                all_posts.extend(posts)

            # ---- Flow 2: Job posts (contentType=job) ----
            for query in self.JOB_QUERIES:
                if not self.check_quota() or len(all_posts) >= self.max_posts:
                    break
                posts = await self._search_posts(query, seen_fingerprints, content_type="job")
                for p in posts:
                    p["scrape_type"] = "job"
                all_posts.extend(posts)

            trimmed = all_posts[: self.max_posts]

            # ---- Enrich job posts: visit poster profiles to find company ----
            await self._enrich_job_posts(trimmed)

            n_fund = sum(1 for p in trimmed if p.get("scrape_type") == "funding")
            n_job = sum(1 for p in trimmed if p.get("scrape_type") == "job")
            logger.info(
                "[linkedin] Total posts collected: %d (funding=%d, job=%d)",
                len(trimmed), n_fund, n_job,
            )
            return trimmed
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Search + extraction
    # ------------------------------------------------------------------

    async def _search_posts(
        self, query: str, seen: set[str], content_type: str = ""
    ) -> list[dict]:
        """Run one search query and collect post cards."""
        encoded = quote(query)
        url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords={encoded}"
            f"&datePosted=%22past-24h%22"
            f"&sortBy=%22date_posted%22"
        )
        if content_type:
            url += f"&contentType=%22{content_type}%22"

        logger.info("[linkedin] Searching: %s", query)

        await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(3, 6)
        self.increment_quota()

        posts: list[dict] = []
        last_height = 0
        stale = 0

        for _ in range(self.max_scrolls):
            if not self.check_quota() or len(posts) >= self.max_posts:
                break

            new_posts = await self._extract_posts(seen)
            posts.extend(new_posts)

            new_height = await self.scroll_to_bottom()
            self.increment_quota()
            await self.random_delay(self.scroll_delay_min, self.scroll_delay_max)

            if new_height == last_height:
                stale += 1
                if stale >= 3:
                    break
            else:
                stale = 0
            last_height = new_height

        return posts

    async def _extract_posts(self, seen: set[str]) -> list[dict]:
        """Parse visible post cards on the search results page."""
        posts: list[dict] = []

        containers = await self.page.query_selector_all(
            "div.feed-shared-update-v2"
        )
        if not containers:
            containers = await self.page.query_selector_all(
                "li.reusable-search__result-container"
            )

        for container in containers:
            try:
                if await self._is_promoted(container):
                    continue

                parsed = await self._parse_post(container)
                if not parsed:
                    continue

                fp = parsed.get("fingerprint", "")
                if fp in seen:
                    continue
                seen.add(fp)
                posts.append(parsed)

            except Exception as exc:
                logger.debug("[linkedin] Error parsing post: %s", exc)

        return posts

    async def _is_promoted(self, container) -> bool:
        """Check if the post has a Promoted / Sponsored badge."""
        try:
            badge = await container.query_selector(
                'span:text-is("Promoted"), span:text-is("Sponsored")'
            )
            if badge:
                return True
            text = await container.inner_text()
            lower = text.lower()
            if "promoted" in lower[:100] or "sponsored" in lower[:100]:
                return True
        except Exception:
            pass
        return False

    async def _parse_post(self, container) -> Optional[dict]:
        """Extract data from a single LinkedIn post card."""
        text_el = await container.query_selector(
            "span.break-words, div.feed-shared-text"
        )
        text = ""
        if text_el:
            text = (await text_el.inner_text()).strip()
        if not text or len(text) < 30:
            return None

        author_el = await container.query_selector(
            "span.update-components-actor__name span, "
            "span.feed-shared-actor__name span"
        )
        author = (await author_el.inner_text()).strip() if author_el else "Unknown"

        subtitle_el = await container.query_selector(
            "span.update-components-actor__description, "
            "span.feed-shared-actor__description"
        )
        subtitle = (await subtitle_el.inner_text()).strip() if subtitle_el else ""

        # Post permalink
        link_el = await container.query_selector(
            'a[href*="/posts/"], a[href*="/feed/update/"]'
        )
        post_url = ""
        if link_el:
            href = await link_el.get_attribute("href") or ""
            if href.startswith("/"):
                href = f"https://www.linkedin.com{href}"
            post_url = href.split("?")[0]

        # Author's LinkedIn profile or company URL
        author_linkedin_url = ""
        author_company_url = ""
        for sel in [
            "a.update-components-actor__container-link",
            "a.update-components-actor__meta-link",
            "a.feed-shared-actor__container-link",
        ]:
            el = await container.query_selector(sel)
            if el:
                href = await el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = f"https://www.linkedin.com{href}"
                href = href.split("?")[0]
                if "/in/" in href:
                    author_linkedin_url = href
                elif "/company/" in href:
                    author_company_url = href
                break

        time_el = await container.query_selector(
            "time, span.update-components-actor__sub-description"
        )
        timestamp = ""
        if time_el:
            timestamp = (await time_el.get_attribute("datetime")) or ""
            if not timestamp:
                timestamp = (await time_el.inner_text()).strip()

        fingerprint = f"{author}:{text[:200]}"

        return {
            "text": text,
            "source_url": post_url,
            "author": author,
            "author_subtitle": subtitle,
            "author_linkedin_url": author_linkedin_url,
            "author_company_url": author_company_url,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "platform": "linkedin",
            "fingerprint": fingerprint,
        }

    # ------------------------------------------------------------------
    # Job-post enrichment: visit poster profiles to resolve company
    # ------------------------------------------------------------------

    async def _enrich_job_posts(
        self, posts: list[dict], max_visits: int = 15
    ) -> None:
        """For job posts, visit the poster's profile to find their company."""
        visited = 0
        for post in posts:
            if visited >= max_visits:
                break
            if post.get("scrape_type") != "job":
                continue

            # If the author IS a company page, use the author name directly
            if post.get("author_company_url"):
                post["author_company"] = post.get("author", "")
                continue

            url = post.get("author_linkedin_url", "")
            if not url or not self.check_quota():
                continue

            company, headline = await self._resolve_author_company(url)
            visited += 1
            if company:
                post["author_company"] = company
                slug = url.split("/in/")[-1].rstrip("/")
                logger.info("[linkedin] Author profile %s -> company: %s", slug, company)
            if headline:
                post["author_headline"] = headline

    async def _resolve_author_company(self, profile_url: str) -> tuple[str, str]:
        """Visit a LinkedIn profile and extract the company from the headline."""
        try:
            await self.page.goto(
                profile_url, wait_until="domcontentloaded", timeout=30_000
            )
            await self.random_delay(1, 3)
            self.increment_quota()

            headline = ""
            for sel in [
                "div.text-body-medium.break-words",
                "div.text-body-medium",
            ]:
                el = await self.page.query_selector(sel)
                if el:
                    headline = (await el.inner_text()).strip()
                    if headline:
                        break

            company = ""
            if headline:
                # Headline format: "Role at Company" or "Role @ Company"
                lower = headline.lower()
                for sep in [" at ", " @ "]:
                    idx = lower.rfind(sep)
                    if idx != -1:
                        company = headline[idx + len(sep):].strip()
                        for delim in ["|", "·", "•", ",", "-"]:
                            if delim in company:
                                company = company.split(delim)[0].strip()
                        break

            return company, headline
        except Exception as exc:
            logger.debug(
                "[linkedin] Profile visit failed for %s: %s", profile_url, exc,
            )
            return "", ""
