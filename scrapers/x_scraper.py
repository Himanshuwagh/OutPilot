"""
X.com (Twitter) scraper for AI/ML hiring and funding posts.
Uses Playwright with persistent login session. Last 24 hours only.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import yaml

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class XScraper(BaseScraper):
    PLATFORM = "x.com"

    def __init__(
        self,
        browser_data_dir: str = "./browser_data/x",
        headless: bool = True,
        max_tweets: int = 50,
        max_scrolls: int = 15,
        scroll_delay_min: float = 2.0,
        scroll_delay_max: float = 5.0,
    ):
        super().__init__(browser_data_dir, headless=headless, daily_quota=200)
        self.max_tweets = max_tweets
        self.max_scrolls = max_scrolls
        self.scroll_delay_min = scroll_delay_min
        self.scroll_delay_max = scroll_delay_max

        with open("config/keywords.yaml") as f:
            kw = yaml.safe_load(f)
        self.tech_keywords = kw.get("tech_keywords", [])

    def _build_queries(self) -> list[str]:
        """Build search queries with since: operator for last 24h."""
        since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d")
        return [
            f'"hiring" (AI OR ML OR LLM OR "machine learning") since:{since}',
            f'"raised" (AI OR "series" OR "funding" OR "seed") since:{since}',
            f'"looking for" (ML OR "machine learning" OR "data scientist" OR "AI engineer") since:{since}',
        ]

    async def scrape(self) -> list[dict]:
        """Scrape X.com for hiring/funding posts in the last 24 hours."""
        await self.start()
        try:
            await self.ensure_logged_in("https://x.com/home", "home")
            all_tweets: list[dict] = []
            seen_ids: set[str] = set()

            for query in self._build_queries():
                if not self.check_quota():
                    break
                tweets = await self._search(query, seen_ids)
                all_tweets.extend(tweets)
                if len(all_tweets) >= self.max_tweets:
                    break

            logger.info("[x.com] Total tweets collected: %d", len(all_tweets))
            return all_tweets[: self.max_tweets]
        finally:
            await self.stop()

    async def _search(self, query: str, seen_ids: set[str]) -> list[dict]:
        """Execute one search query and return parsed tweets."""
        encoded = quote(query)
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        logger.info("[x.com] Searching: %s", query[:80])

        await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await self.random_delay(3, 5)
        self.increment_quota()

        tweets: list[dict] = []
        last_height = 0
        stale_scrolls = 0

        for _ in range(self.max_scrolls):
            if not self.check_quota():
                break

            new_tweets = await self._extract_tweets(seen_ids)
            tweets.extend(new_tweets)

            if len(tweets) >= self.max_tweets:
                break

            new_height = await self.scroll_to_bottom()
            self.increment_quota()
            await self.random_delay(self.scroll_delay_min, self.scroll_delay_max)

            if new_height == last_height:
                stale_scrolls += 1
                if stale_scrolls >= 3:
                    break
            else:
                stale_scrolls = 0
            last_height = new_height

        return tweets

    async def _extract_tweets(self, seen_ids: set[str]) -> list[dict]:
        """Parse tweet elements currently visible on the page."""
        tweets: list[dict] = []
        articles = await self.page.query_selector_all('article[data-testid="tweet"]')

        for article in articles:
            try:
                parsed = await self._parse_tweet(article)
                if parsed and parsed["tweet_id"] not in seen_ids:
                    seen_ids.add(parsed["tweet_id"])
                    tweets.append(parsed)
            except Exception as exc:
                logger.debug("[x.com] Error parsing tweet: %s", exc)
        return tweets

    async def _parse_tweet(self, article) -> Optional[dict]:
        """Extract data from a single tweet DOM element."""
        link_el = await article.query_selector('a[href*="/status/"]')
        if not link_el:
            return None
        href = await link_el.get_attribute("href") or ""
        match = re.search(r"/([^/]+)/status/(\d+)", href)
        if not match:
            return None

        username = match.group(1)
        tweet_id = match.group(2)

        text_el = await article.query_selector('[data-testid="tweetText"]')
        tweet_text = (await text_el.inner_text()) if text_el else ""

        name_el = await article.query_selector('[data-testid="User-Name"] span')
        display_name = (await name_el.inner_text()) if name_el else username

        time_el = await article.query_selector("time")
        timestamp = (
            (await time_el.get_attribute("datetime"))
            if time_el
            else datetime.utcnow().isoformat()
        )

        return {
            "tweet_id": tweet_id,
            "text": tweet_text,
            "source_url": f"https://x.com/{username}/status/{tweet_id}",
            "author_username": username,
            "author_display_name": display_name,
            "timestamp": timestamp,
            "platform": "x.com",
        }
