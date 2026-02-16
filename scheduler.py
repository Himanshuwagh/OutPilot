"""
APScheduler-based daily scheduler (Option B fallback).
Triggers the full pipeline at the configured hour each day.
"""

import logging
import signal
import sys

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.crew import run_pipeline

logger = logging.getLogger(__name__)


def _run_job():
    """Wrapper that catches exceptions so the scheduler keeps running."""
    try:
        logger.info("Scheduled run triggered.")
        result = run_pipeline()
        logger.info("Scheduled run complete: %s", result)
    except Exception as exc:
        logger.error("Scheduled run failed: %s", exc, exc_info=True)


def start_scheduler():
    """Start the blocking scheduler that runs forever."""
    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)["scheduling"]

    hour = cfg["daily_run_hour"]
    minute = cfg["daily_run_minute"]

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_job,
        CronTrigger(hour=hour, minute=minute),
        id="cold_outreach_daily",
        name="Daily Cold Outreach Pipeline",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info(
        "Scheduler started. Pipeline will run daily at %02d:%02d. Press Ctrl+C to stop.",
        hour,
        minute,
    )
    scheduler.start()
