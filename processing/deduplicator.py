"""
Two-layer deduplicator.

Layer 1 (Early): fingerprint-based, checks Notion before classification.
Layer 2 (Post-extraction): company-name within 7-day window.
"""

import hashlib
import logging
from typing import Optional

from storage.notion_client import NotionStorage

logger = logging.getLogger(__name__)


def make_fingerprint(post: dict) -> str:
    """Create a unique fingerprint for a post."""
    url = post.get("source_url", "")
    if url:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    text = post.get("text", "")[:200]
    platform = post.get("platform", "")
    raw = f"{platform}:{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Deduplicator:
    def __init__(self, notion: NotionStorage):
        self.notion = notion
        self._fingerprint_cache: Optional[set[str]] = None

    def load_cache(self, days: int = 7) -> None:
        """Pre-load fingerprints from Notion for fast O(1) checks."""
        self._fingerprint_cache = self.notion.load_recent_fingerprints(days)

    @property
    def cache(self) -> set[str]:
        if self._fingerprint_cache is None:
            self.load_cache()
        assert self._fingerprint_cache is not None
        return self._fingerprint_cache

    # Layer 1 -------------------------------------------------------

    def is_duplicate_fingerprint(self, post: dict) -> bool:
        """Return True if this post's fingerprint is already known."""
        fp = make_fingerprint(post)
        if fp in self.cache:
            logger.debug("Duplicate fingerprint: %s", fp)
            return True
        return False

    def register_fingerprint(self, post: dict) -> str:
        """Add fingerprint to cache (call after inserting into Notion)."""
        fp = make_fingerprint(post)
        self.cache.add(fp)
        return fp

    # Layer 2 -------------------------------------------------------

    def is_duplicate_company(
        self, company_name: str, post_type: str, days: int = 7
    ) -> bool:
        """Return True if a lead for this company+type exists within the window."""
        return self.notion.lead_exists_by_company(company_name, days, post_type)
