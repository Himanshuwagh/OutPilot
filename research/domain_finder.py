"""
Find a company's website domain from its name.

Strategies (in priority order):
1. Use domain_hint extracted from URLs in the original post (fastest, most accurate)
2. Google search scrape
3. DNS resolution for common TLDs
"""

import re
import logging
from typing import Optional
from urllib.parse import urlparse

import dns.resolver
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


class DomainFinder:
    def __init__(self):
        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)
        self.tlds = cfg["research"]["common_tlds"]
        self._cache: dict[str, str] = {}

    def find_domain(self, company_name: str, domain_hint: str = "") -> Optional[str]:
        """
        Return the primary domain for a company, or None.

        Args:
            company_name: Company name to search for.
            domain_hint: An optional domain extracted from the post's URLs
                         (e.g., "acme.ai"). If provided and valid, used first.
        """
        key = company_name.strip().lower()
        if key in self._cache:
            return self._cache[key]

        domain = None

        # Strategy 1: Use domain_hint from the post
        if domain_hint:
            domain = self._validate_domain_hint(domain_hint, company_name)

        # Strategy 2: Google search
        if not domain:
            domain = self._google_search(company_name)

        # Strategy 3: DNS probe common TLDs
        if not domain:
            domain = self._dns_probe(company_name)

        if domain:
            self._cache[key] = domain
            logger.info("Domain for '%s': %s", company_name, domain)
        else:
            logger.warning("Could not find domain for '%s'", company_name)

        return domain

    def _validate_domain_hint(self, hint: str, company_name: str) -> Optional[str]:
        """Verify the domain hint resolves and loosely relates to the company."""
        hint = hint.lower().strip()
        hint = re.sub(r"^www\.", "", hint)

        # Must resolve (has DNS records)
        try:
            dns.resolver.resolve(hint, "A")
        except Exception:
            return None

        # Optional: check it loosely relates to the company name
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        domain_slug = re.sub(r"[^a-z0-9]", "", hint.split(".")[0])

        # If the domain name contains part of the company name, great
        if len(slug) >= 3 and (domain_slug in slug or slug in domain_slug):
            return hint

        # Even if names don't match, if it's from the post it's likely right
        # (e.g., the post has a careers link to a domain different from the company name)
        logger.debug("Domain hint %s doesn't match company '%s', but accepting anyway", hint, company_name)
        return hint

    def _google_search(self, company_name: str) -> Optional[str]:
        """Scrape Google search for the company's official website."""
        query = f"{company_name} official website"
        url = f"https://www.google.com/search?q={requests.utils.requote_uri(query)}&num=5"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("Google search failed: %s", exc)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        skip_domains = {
            "google.com", "wikipedia.org", "linkedin.com", "facebook.com",
            "twitter.com", "x.com", "crunchbase.com", "glassdoor.com",
            "indeed.com", "youtube.com", "github.com",
        }

        for a_tag in soup.select("a[href]"):
            href = a_tag["href"]
            match = re.search(r"https?://([^/&]+)", href)
            if not match:
                continue
            domain = match.group(1).lower()
            domain = re.sub(r"^www\.", "", domain)

            if any(skip in domain for skip in skip_domains):
                continue
            if "." in domain:
                return domain

        return None

    def _dns_probe(self, company_name: str) -> Optional[str]:
        """Try common TLDs to see if the domain resolves."""
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        for tld in self.tlds:
            candidate = f"{slug}{tld}"
            try:
                dns.resolver.resolve(candidate, "A")
                return candidate
            except Exception:
                continue
        return None
