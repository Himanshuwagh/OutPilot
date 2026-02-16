#!/usr/bin/env python3
"""
Entry point for the AI Cold Outreach Pipeline.

Usage:
    python main.py --run-now       Run the full pipeline once immediately
    python main.py --schedule      Run as a long-lived process, executing daily at 6 AM
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment before anything else
load_dotenv(Path(__file__).parent / ".env")

from agents.crew import run_pipeline
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", mode="a"),
    ],
)
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(
        description="AI Cold Outreach Pipeline - Automated hiring/funding lead generation"
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the full pipeline once immediately",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Start the scheduler (runs daily at configured time)",
    )

    args = parser.parse_args()

    if not args.run_now and not args.schedule:
        parser.print_help()
        sys.exit(1)

    if args.run_now:
        logger.info("Running pipeline now...")
        try:
            result = run_pipeline()
            logger.info("Pipeline result: %s", result)
        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            sys.exit(1)

    if args.schedule:
        logger.info("Starting scheduler...")
        start_scheduler()


if __name__ == "__main__":
    main()
