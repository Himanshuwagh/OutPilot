"""
Find a company's website domain from its name.

Strategies (in priority order):
1. Use domain_hint extracted from URLs in the original post (fastest, most accurate)
2. DuckDuckGo Instant Answer API (more reliable than scraping Google)
3. Google search scrape (may be blocked by CAPTCHA)
4. DNS resolution for common TLDs (with multiple slug variations)
"""

import re
import logging
from typing import Optional

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

SKIP_DOMAINS = {
    "google.com", "wikipedia.org", "linkedin.com", "facebook.com",
    "twitter.com", "x.com", "crunchbase.com", "glassdoor.com",
    "indeed.com", "youtube.com", "github.com", "bloomberg.com",
    "techcrunch.com", "forbes.com", "reuters.com", "bing.com",
    "duckduckgo.com", "reddit.com", "quora.com", "medium.com",
    "apple.com", "amazon.com",
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
        Tries multiple strategies in order of reliability.
        """
        key = company_name.strip().lower()
        if key in self._cache:
            return self._cache[key]

        domain = None

        # Strategy 1: Use domain_hint from the post
        if domain_hint:
            domain = self._validate_domain_hint(domain_hint, company_name)
            if domain:
                logger.info("Domain for '%s' via hint: %s", company_name, domain)

        # Strategy 2: DuckDuckGo (doesn't block like Google)
        if not domain:
            domain = self._duckduckgo_search(company_name)
            if domain:
                logger.info("Domain for '%s' via DuckDuckGo: %s", company_name, domain)

        # Strategy 3: Google search
        if not domain:
            domain = self._google_search(company_name)
            if domain:
                logger.info("Domain for '%s' via Google: %s", company_name, domain)

        # Strategy 4: DNS probe common TLDs (with multiple slug variations)
        if not domain:
            domain = self._dns_probe(company_name)
            if domain:
                logger.info("Domain for '%s' via DNS probe: %s", company_name, domain)

        if domain:
            self._cache[key] = domain
        else:
            logger.warning("Could not find domain for '%s'", company_name)

        return domain

    def _validate_domain_hint(self, hint: str, company_name: str) -> Optional[str]:
        """Verify the domain hint resolves and loosely relates to the company."""
        hint = hint.lower().strip()
        hint = re.sub(r"^www\.", "", hint)

        try:
            dns.resolver.resolve(hint, "A")
        except Exception:
            return None

        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        domain_slug = re.sub(r"[^a-z0-9]", "", hint.split(".")[0])

        if len(slug) >= 3 and (domain_slug in slug or slug in domain_slug):
            return hint

        logger.debug(
            "Domain hint %s doesn't match company '%s', but accepting anyway",
            hint, company_name,
        )
        return hint

    def _duckduckgo_search(self, company_name: str) -> Optional[str]:
        """Use DuckDuckGo HTML search to find the company's website."""
        query = f"{company_name} official website"
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.requote_uri(query)}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("DuckDuckGo search failed: %s", exc)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        for a_tag in soup.select("a.result__a[href]"):
            href = a_tag.get("href", "")
            domain = self._extract_domain_from_url(href)
            if domain and not self._is_skip_domain(domain):
                return domain

        # Also try result snippets for URLs
        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            domain = self._extract_domain_from_url(href)
            if domain and not self._is_skip_domain(domain):
                return domain

        return None

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

        for a_tag in soup.select("a[href]"):
            href = a_tag["href"]
            domain = self._extract_domain_from_url(href)
            if domain and not self._is_skip_domain(domain):
                return domain

        return None

    def _dns_probe(self, company_name: str) -> Optional[str]:
        """
        Try common TLDs with multiple slug variations to handle multi-word names.

        E.g. "Scale AI" -> tries: scaleai.com, scale.com, scale.ai, scale-ai.com, etc.
        """
        name = company_name.lower().strip()
        words = re.findall(r"[a-z0-9]+", name)
        if not words:
            return None

        # Build slug variations
        slugs = set()
        # All words joined: "scaleai"
        slugs.add("".join(words))
        # First word only: "scale"
        slugs.add(words[0])
        # Hyphenated: "scale-ai"
        if len(words) > 1:
            slugs.add("-".join(words))
        # First two words: "openai"
        if len(words) >= 2:
            slugs.add(words[0] + words[1])

        for slug in slugs:
            if not slug or len(slug) < 2:
                continue
            for tld in self.tlds:
                candidate = f"{slug}{tld}"
                try:
                    dns.resolver.resolve(candidate, "A")
                    return candidate
                except Exception:
                    continue

        return None

    @staticmethod
    def _extract_domain_from_url(url_or_href: str) -> Optional[str]:
        """Extract a clean domain from a URL string."""
        match = re.search(r"https?://([^/&?#]+)", url_or_href)
        if not match:
            return None
        domain = match.group(1).lower()
        domain = re.sub(r"^www\.", "", domain)
        if "." in domain:
            return domain
        return None

    @staticmethod
    def _is_skip_domain(domain: str) -> bool:
        """Check if domain is a known non-company site."""
        return any(skip in domain for skip in SKIP_DOMAINS)
