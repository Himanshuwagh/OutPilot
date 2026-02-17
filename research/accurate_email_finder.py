"""
Accuracy-first email finder.

This module is designed as a stronger replacement for the basic email finder.
It uses multiple evidence sources, scores candidates, and enforces a daily
research quota to keep traffic low while maximizing precision.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

import requests
import yaml
from bs4 import BeautifulSoup

from research.email_finder import EmailFinder
from research.email_research_quota import EmailResearchQuota

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


class AccurateEmailFinder:
    """
    Deep email finder with evidence-based scoring.

    Output shape mirrors EmailFinder.find_email for compatibility.
    """

    def __init__(self):
        with open("config/email_patterns.yaml") as f:
            self.patterns = yaml.safe_load(f)["patterns"]
        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)

        rcfg = cfg.get("research", {})
        self.max_web_queries_per_contact = int(
            rcfg.get("accurate_web_queries_per_contact", 4)
        )
        self.quota = EmailResearchQuota(
            daily_limit=int(rcfg.get("accurate_email_daily_limit", 20))
        )
        self.basic = EmailFinder()

    def scrape_website_emails(self, domain: str) -> list[str]:
        """Compatibility helper used by existing pipelines."""
        return self.basic.scrape_website_emails(domain)

    def find_best_email(
        self,
        full_name: str,
        company_domain: str,
        company_name: str = "",
        linkedin_url: str = "",
    ) -> dict:
        """
        Return best email candidate with confidence and evidence.
        """
        first, last = self._normalize_name(full_name)
        if not first:
            return {"email": "", "confidence": "low", "all_candidates": [], "method": ""}

        if not last:
            last = first

        candidates = self._build_candidates(first, last, company_domain)
        if not candidates:
            return {"email": "", "confidence": "low", "all_candidates": [], "method": ""}

        # If daily deep-research budget is exhausted, fallback to basic finder.
        if not self.quota.can_process():
            logger.info(
                "[email-accurate] quota exhausted; using fallback for %s at %s",
                full_name,
                company_domain,
            )
            fallback = self.basic.find_email(first, last, company_domain)
            fallback["method"] = (
                f"{fallback.get('method', 'pattern_guess')}+quota_fallback"
            )
            return fallback

        self.quota.increment()

        scores: dict[str, int] = defaultdict(int)
        reasons: dict[str, list[str]] = defaultdict(list)

        # Base prior: favor first.last slightly.
        scores[candidates[0]] += 8
        reasons[candidates[0]].append("default_pattern_prior")

        # Evidence 1: Website match from known public emails.
        website_emails = self.basic.scrape_website_emails(company_domain)
        website_match = self._match_known_email(first, last, website_emails)
        if website_match:
            scores[website_match] += 90
            reasons[website_match].append("website_exact_or_pattern_match")

        # Evidence 2: Search web for direct candidate mentions (high precision).
        mention_hits = self._search_web_candidate_mentions(
            candidates[: self.max_web_queries_per_contact]
        )
        for email in mention_hits:
            if email in scores or email in candidates:
                scores[email] += 75
                reasons[email].append("direct_web_mention")

        # Evidence 3: Search web for name + domain and extract emails.
        contextual_hits = self._search_web_contextual(
            first, last, company_domain, company_name
        )
        for email in contextual_hits:
            if email in scores or email in candidates:
                scores[email] += 55
                reasons[email].append("name_domain_context_match")

        # Evidence 4: SMTP verification (bonus; often blocked by networks).
        smtp_verified = self._smtp_verified_candidate(candidates, company_domain)
        if smtp_verified:
            scores[smtp_verified] += 65
            reasons[smtp_verified].append("smtp_verified")

        # Small penalties for very unlikely patterns.
        for email in candidates:
            local = email.split("@")[0]
            if len(local) <= 2:
                scores[email] -= 8
                reasons[email].append("short_local_penalty")
            if local in {"admin", "contact", "careers", "jobs", "hr"}:
                scores[email] -= 30
                reasons[email].append("generic_alias_penalty")

        # Ensure every candidate at least exists in scores map.
        for c in candidates:
            _ = scores[c]

        best = max(candidates, key=lambda c: scores[c])
        best_score = scores[best]
        confidence = self._score_to_confidence(best_score)

        method = self._pick_method(reasons[best])
        logger.info(
            "[email-accurate] %s -> %s (%s score=%d reasons=%s)",
            full_name,
            best,
            confidence,
            best_score,
            ",".join(reasons[best]) if reasons[best] else "pattern_guess",
        )

        return {
            "email": best,
            "confidence": confidence,
            "all_candidates": candidates,
            "method": method,
        }

    # Backward-compatible alias.
    def find_email(self, first_name: str, last_name: str, domain: str) -> dict:
        full_name = f"{first_name} {last_name}".strip()
        return self.find_best_email(full_name=full_name, company_domain=domain)

    def _normalize_name(self, full_name: str) -> tuple[str, str]:
        cleaned = re.sub(r"\s+", " ", full_name or "").strip()
        if not cleaned:
            return "", ""
        parts = cleaned.split(" ")
        first = re.sub(r"[^a-z]", "", parts[0].lower())
        last = re.sub(r"[^a-z]", "", parts[-1].lower()) if len(parts) > 1 else ""
        return first, last

    def _build_candidates(self, first: str, last: str, domain: str) -> list[str]:
        f = first[0] if first else ""
        l = last[0] if last else ""
        candidates: list[str] = []
        for pattern in self.patterns:
            email = (
                pattern.replace("{first}", first)
                .replace("{last}", last)
                .replace("{f}", f)
                .replace("{l}", l)
                .replace("{domain}", domain)
            )
            if email and email not in candidates:
                candidates.append(email)
        if not candidates and first and domain:
            candidates.append(f"{first}@{domain}")
        return candidates

    def _match_known_email(self, first: str, last: str, emails: list[str]) -> str:
        if not first:
            return ""
        for email in emails:
            local = email.split("@")[0].lower()
            if first and last:
                if f"{first}.{last}" in local:
                    return email
                if f"{first}{last}" in local:
                    return email
                if f"{first[0]}{last}" in local:
                    return email
            if local == first:
                return email
        return ""

    def _search_web_candidate_mentions(self, candidates: list[str]) -> set[str]:
        hits: set[str] = set()
        for candidate in candidates:
            query = f"\"{candidate}\""
            html = self._duckduckgo_html_search(query)
            if not html:
                continue
            if candidate.lower() in html.lower():
                hits.add(candidate)
        return hits

    def _search_web_contextual(
        self, first: str, last: str, domain: str, company_name: str
    ) -> set[str]:
        query = f"\"{first} {last}\" \"@{domain}\" {company_name}".strip()
        html = self._duckduckgo_html_search(query)
        if not html:
            return set()
        emails = set(
            re.findall(
                r"[a-zA-Z0-9._%+-]+@" + re.escape(domain) + r"\b",
                html,
            )
        )
        return {e.lower() for e in emails}

    def _duckduckgo_html_search(self, query: str) -> str:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.requote_uri(query)}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            return soup.get_text(" ", strip=True)
        except Exception:
            return ""

    def _smtp_verified_candidate(self, candidates: list[str], domain: str) -> str:
        # Uses the existing SMTP logic from EmailFinder as optional evidence.
        try:
            return self.basic._try_smtp_verification(candidates, domain)  # noqa: SLF001
        except Exception:
            return ""

    @staticmethod
    def _score_to_confidence(score: int) -> str:
        if score >= 85:
            return "high"
        if score >= 55:
            return "medium"
        return "low"

    @staticmethod
    def _pick_method(reasons: list[str]) -> str:
        if "website_exact_or_pattern_match" in reasons:
            return "website_scrape"
        if "smtp_verified" in reasons:
            return "smtp_verified"
        if "direct_web_mention" in reasons:
            return "web_mention"
        if "name_domain_context_match" in reasons:
            return "context_match"
        return "pattern_guess"
