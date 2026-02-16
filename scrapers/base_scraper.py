"""
Base scraper with Playwright persistent browser context, anti-detection,
human-like delays, and daily quota tracking.
"""

import asyncio
import json
import os
import random
import logging
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

QUOTA_DIR = Path("./browser_data/quotas")


class BaseScraper(ABC):
    """Abstract base for browser-based scrapers (X, LinkedIn)."""

    PLATFORM: str = "unknown"

    def __init__(
        self,
        browser_data_dir: str,
        headless: bool = False,
        daily_quota: int = 200,
    ):
        self.browser_data_dir = browser_data_dir
        self.headless = headless
        self.daily_quota = daily_quota

        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._actions_today = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch Playwright with a persistent (cookie-saving) context."""
        os.makedirs(self.browser_data_dir, exist_ok=True)
        self._playwright = await async_playwright().start()

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.browser_data_dir,
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self._page = await self._context.new_page()
        self._load_quota()
        logger.info(
            "[%s] Browser started. Actions used today: %d/%d",
            self.PLATFORM,
            self._actions_today,
            self.daily_quota,
        )

    async def stop(self) -> None:
        """Close browser and save quota."""
        self._save_quota()
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[%s] Browser closed.", self.PLATFORM)

    @property
    def page(self) -> Page:
        assert self._page is not None, "Call start() first"
        return self._page

    # ------------------------------------------------------------------
    # Anti-detection helpers
    # ------------------------------------------------------------------

    async def random_delay(self, lo: float = 2.0, hi: float = 5.0) -> None:
        """Sleep for a random duration to look human."""
        delay = random.uniform(lo, hi)
        await asyncio.sleep(delay)

    async def human_scroll(self, times: int = 1) -> None:
        """Scroll down in a human-like manner."""
        for _ in range(times):
            distance = random.randint(300, 700)
            await self.page.evaluate(f"window.scrollBy(0, {distance})")
            await self.random_delay(1.0, 2.5)

    async def scroll_to_bottom(self) -> int:
        """Scroll to bottom and return new page height."""
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self.random_delay(1.5, 3.0)
        return await self.page.evaluate("document.body.scrollHeight")

    # ------------------------------------------------------------------
    # Quota management
    # ------------------------------------------------------------------

    def _quota_path(self) -> Path:
        QUOTA_DIR.mkdir(parents=True, exist_ok=True)
        return QUOTA_DIR / f"{self.PLATFORM}.json"

    def _load_quota(self) -> None:
        path = self._quota_path()
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("date") == date.today().isoformat():
                self._actions_today = data.get("count", 0)
            else:
                self._actions_today = 0
        else:
            self._actions_today = 0

    def _save_quota(self) -> None:
        path = self._quota_path()
        path.write_text(
            json.dumps({"date": date.today().isoformat(), "count": self._actions_today})
        )

    def increment_quota(self, n: int = 1) -> None:
        self._actions_today += n
        self._save_quota()

    def quota_remaining(self) -> int:
        return max(0, self.daily_quota - self._actions_today)

    def check_quota(self) -> bool:
        """Return True if we still have quota left."""
        if self._actions_today >= self.daily_quota:
            logger.warning("[%s] Daily quota exhausted (%d).", self.PLATFORM, self.daily_quota)
            return False
        return True

    # ------------------------------------------------------------------
    # Login helper
    # ------------------------------------------------------------------

    async def ensure_logged_in(self, home_url: str, login_indicator: str) -> None:
        """
        Navigate to home_url. If not logged in (URL contains 'login'),
        wait for manual login.
        """
        await self.page.goto(home_url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(3)

        current = self.page.url
        if "login" in current or "/login" in current:
            if self.headless:
                raise RuntimeError(
                    f"[{self.PLATFORM}] Login required but running in headless mode. "
                    "Seed auth session once using setup_sessions.py, then rerun."
                )
            logger.info(
                "[%s] Not logged in. Please log in manually in the browser window...",
                self.PLATFORM,
            )
            try:
                # Wait until we are no longer on a login URL or we've reached the expected home section
                await self.page.wait_for_url(
                    f"**/{login_indicator}*",
                    timeout=300_000,  # 5 minutes max
                )
                logger.info("[%s] Login successful (URL matched %s).", self.PLATFORM, login_indicator)
            except Exception:
                # If LinkedIn/X changes their URL pattern, don't hang forever — just continue.
                logger.warning(
                    "[%s] Login wait timed out; proceeding anyway. If scraping fails, re-run and ensure you're logged in.",
                    self.PLATFORM,
                )
            await asyncio.sleep(2)
        else:
            logger.info("[%s] Already logged in (no login redirect detected).", self.PLATFORM)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """Run the scraping logic and return a list of raw post dicts."""
        ...
