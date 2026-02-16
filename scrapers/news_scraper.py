"""
News scraper for AI funding and hiring announcements.
Sources: TechCrunch AI category + Google News RSS.
Uses requests + BeautifulSoup (no browser needed). Last 24 hours only.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

import yaml

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


class NewsScraper:
    """Scrapes TechCrunch and Google News RSS for AI funding/hiring posts."""

    def __init__(self):
        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)["scraping"]["news"]
        self.tc_url = cfg["techcrunch_url"]
        self.gn_rss = cfg["google_news_rss"]

        with open("config/keywords.yaml") as f:
            kw = yaml.safe_load(f)
        self.hiring_kw = [k.lower() for k in kw["hiring_keywords"]]
        self.funding_kw = [k.lower() for k in kw["funding_keywords"]]
        self.tech_kw = [k.lower() for k in kw["tech_keywords"]]

        self.cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    def scrape(self) -> list[dict]:
        """Collect articles from all news sources."""
        articles: list[dict] = []
        articles.extend(self._scrape_techcrunch())
        articles.extend(self._scrape_google_news())
        logger.info("[news] Total news articles collected: %d", len(articles))
        return articles

    # ------------------------------------------------------------------
    # TechCrunch
    # ------------------------------------------------------------------

    def _scrape_techcrunch(self) -> list[dict]:
        results: list[dict] = []
        try:
            resp = requests.get(self.tc_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("[news] TechCrunch fetch failed: %s", exc)
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article, div.post-block")

        for art in articles:
            try:
                link_el = art.select_one("a[href]")
                if not link_el:
                    continue
                url = link_el.get("href", "")
                title = link_el.get_text(strip=True)

                time_el = art.select_one("time[datetime]")
                if time_el:
                    dt_str = time_el["datetime"]
                    pub_date = self._parse_iso(dt_str)
                else:
                    pub_date = None

                if pub_date and pub_date < self.cutoff:
                    continue

                snippet_el = art.select_one("p, div.post-block__content")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                combined = f"{title} {snippet}".lower()
                if not self._is_relevant(combined):
                    continue

                results.append({
                    "text": f"{title}. {snippet}",
                    "source_url": url,
                    "author": "TechCrunch",
                    "timestamp": pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
                    "platform": "techcrunch",
                })

            except Exception as exc:
                logger.debug("[news] TC article parse error: %s", exc)

        logger.info("[news] TechCrunch: %d relevant articles", len(results))
        return results

    # ------------------------------------------------------------------
    # Google News RSS
    # ------------------------------------------------------------------

    def _scrape_google_news(self) -> list[dict]:
        results: list[dict] = []
        try:
            resp = requests.get(self.gn_rss, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("[news] Google News RSS failed: %s", exc)
            return results

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.warning("[news] RSS parse error: %s", exc)
            return results

        for item in root.iter("item"):
            try:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_str = item.findtext("pubDate") or ""

                pub_date = self._parse_rfc2822(pub_str)
                if pub_date and pub_date < self.cutoff:
                    continue

                desc_raw = item.findtext("description") or ""
                desc = BeautifulSoup(desc_raw, "html.parser").get_text(strip=True)

                combined = f"{title} {desc}".lower()
                if not self._is_relevant(combined):
                    continue

                results.append({
                    "text": f"{title}. {desc}",
                    "source_url": link,
                    "author": "Google News",
                    "timestamp": pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
                    "platform": "google_news",
                })

            except Exception as exc:
                logger.debug("[news] RSS item parse error: %s", exc)

        logger.info("[news] Google News: %d relevant articles", len(results))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_relevant(self, text: str) -> bool:
        """Check if article is about AI hiring/funding."""
        has_tech = any(kw in text for kw in self.tech_kw)
        has_hiring = any(kw in text for kw in self.hiring_kw)
        has_funding = any(kw in text for kw in self.funding_kw)
        return has_tech and (has_hiring or has_funding)

    @staticmethod
    def _parse_iso(dt_str: str) -> Optional[datetime]:
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_rfc2822(dt_str: str) -> Optional[datetime]:
        try:
            return parsedate_to_datetime(dt_str)
        except (ValueError, TypeError):
            return None
