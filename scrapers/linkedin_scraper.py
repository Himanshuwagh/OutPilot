"""
LinkedIn post scraper for AI/ML hiring and funding posts.
Uses Playwright with persistent login session. Last 24 hours only.
Skips Promoted / Sponsored posts.
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

    SEARCH_QUERIES = [
        "hiring AI ML engineer",
        "raised funding artificial intelligence",
        "series A AI startup hiring",
        "looking for machine learning",
        "LLM engineer hiring",
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

    async def scrape(self) -> list[dict]:
        """Scrape LinkedIn feed posts from the last 24 hours."""
        await self.start()
        try:
            await self.ensure_logged_in("https://www.linkedin.com/feed/", "feed")
            all_posts: list[dict] = []
            seen_fingerprints: set[str] = set()

            for query in self.SEARCH_QUERIES:
                if not self.check_quota():
                    break
                if len(all_posts) >= self.max_posts:
                    break
                posts = await self._search_posts(query, seen_fingerprints)
                all_posts.extend(posts)

            logger.info("[linkedin] Total posts collected: %d", len(all_posts))
            return all_posts[: self.max_posts]
        finally:
            await self.stop()

    async def _search_posts(self, query: str, seen: set[str]) -> list[dict]:
        """Run one search query and collect post cards."""
        encoded = quote(query)
        url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords={encoded}&datePosted=%22past-24h%22&sortBy=%22date_posted%22"
        )
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

        link_el = await container.query_selector(
            'a[href*="/posts/"], a[href*="/feed/update/"]'
        )
        post_url = ""
        if link_el:
            href = await link_el.get_attribute("href") or ""
            if href.startswith("/"):
                href = f"https://www.linkedin.com{href}"
            post_url = href.split("?")[0]

        time_el = await container.query_selector("time, span.update-components-actor__sub-description")
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
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "platform": "linkedin",
            "fingerprint": fingerprint,
        }
