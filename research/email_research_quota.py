"""
Daily quota tracker for deep email research.

This keeps expensive enrichment bounded (web lookups + SMTP probes) so we can
optimize for accuracy without running heavy traffic all day.
"""

import json
from datetime import date
from pathlib import Path


QUOTA_FILE = Path("./browser_data/quotas/email_research.json")


class EmailResearchQuota:
    """Tracks how many deep email lookups were executed today."""

    def __init__(self, daily_limit: int = 20):
        self.daily_limit = max(1, int(daily_limit))
        self._count = self._load()

    def _load(self) -> int:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not QUOTA_FILE.exists():
            return 0
        try:
            data = json.loads(QUOTA_FILE.read_text())
        except Exception:
            return 0
        if data.get("date") != date.today().isoformat():
            return 0
        return int(data.get("count", 0))

    def _save(self) -> None:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"date": date.today().isoformat(), "count": self._count}
        QUOTA_FILE.write_text(json.dumps(payload))

    def can_process(self) -> bool:
        return self._count < self.daily_limit

    def remaining(self) -> int:
        return max(0, self.daily_limit - self._count)

    def increment(self, n: int = 1) -> None:
        self._count += max(1, int(n))
        self._save()
