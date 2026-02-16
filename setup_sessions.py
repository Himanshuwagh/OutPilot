#!/usr/bin/env python3
"""
One-time session seeding for headless mode.

Usage:
    python setup_sessions.py --platform x
    python setup_sessions.py --platform linkedin
    python setup_sessions.py --platform both

This script opens a visible browser ONCE, lets you log in, then stores
session cookies in browser_data/. Future runs stay fully headless.
"""

import argparse
import asyncio
import logging

from scrapers.x_scraper import XScraper
from scrapers.linkedin_scraper import LinkedInPostScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_sessions")


async def seed_x() -> None:
    scraper = XScraper(headless=False)
    await scraper.start()
    try:
        await scraper.ensure_logged_in("https://x.com/home", "home")
        logger.info("X session saved to browser_data/x.")
    finally:
        await scraper.stop()


async def seed_linkedin() -> None:
    scraper = LinkedInPostScraper(headless=False)
    await scraper.start()
    try:
        await scraper.ensure_logged_in("https://www.linkedin.com/feed/", "feed")
        logger.info("LinkedIn session saved to browser_data/linkedin.")
    finally:
        await scraper.stop()


async def main(platform: str) -> None:
    if platform in {"x", "both"}:
        await seed_x()
    if platform in {"linkedin", "both"}:
        await seed_linkedin()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed login sessions for headless scraping")
    parser.add_argument(
        "--platform",
        choices=["x", "linkedin", "both"],
        default="both",
        help="Which platform session to seed",
    )
    args = parser.parse_args()
    asyncio.run(main(args.platform))

