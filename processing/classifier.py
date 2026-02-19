"""
Rule-based post classifier: hiring / funding / both.
Also filters out noise (ads, courses, staffing agencies).
Uses Groq LLM (llama-3.3-70b-versatile) to drop news/commentary posts
that only discuss hiring in general rather than an actual job or funding.
"""

import logging
import os
import re

import yaml

logger = logging.getLogger(__name__)

_groq_client = None
_groq_model = None


def _get_groq():
    global _groq_client
    if _groq_client is None and os.getenv("GROQ_API_KEY"):
        try:
            from groq import Groq
            _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        except Exception as e:
            logger.debug("Groq client init failed: %s", e)
    return _groq_client


def _get_groq_model() -> str:
    global _groq_model
    if _groq_model is None:
        try:
            with open("config/settings.yaml") as f:
                cfg = yaml.safe_load(f)
            _groq_model = (cfg.get("outreach") or {}).get("groq_model", "llama-3.3-70b-versatile")
        except Exception:
            _groq_model = "llama-3.3-70b-versatile"
    return _groq_model


def _is_actual_job_or_funding_llm(text: str) -> bool:
    """
    Use Groq LLM to decide if the post is an actual job/funding announcement
    (from or about a specific company) vs general news/commentary/opinion.
    Returns True only for JOB_OR_FUNDING.
    """
    client = _get_groq()
    if not client:
        return True  # no API: keep post (rule-based only)
    model = _get_groq_model()
    system = (
        "You are a strict filter for job and funding posts. "
        "Your ONLY task is to decide if the given post is:\n"
        "- JOB_OR_FUNDING: A real announcement (a specific company hiring for a role, or a specific company that raised funding). "
        "The post should invite applications, link to a job, or announce a concrete funding round for a named company.\n"
        "- NEWS_OR_COMMENTARY: General news, opinion, or commentary about hiring/funding/AI in the industry. "
        "Examples: 'IBM plans to hire...' as news, 'LLMs are not AGI', 'companies are still hiring engineers', "
        "'AI has not replaced anyone', opinion pieces, hot takes, or posts that only discuss hiring in general.\n"
        "Reply with EXACTLY one of: JOB_OR_FUNDING or NEWS_OR_COMMENTARY. No other text."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": (text or "")[:600]},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        raw = (resp.choices[0].message.content or "").strip().upper()
        if "NEWS_OR_COMMENTARY" in raw or "NEWS" in raw:
            return False
        return True
    except Exception as exc:
        logger.debug("LLM relevance check failed: %s", exc)
        return True  # on error, keep post


class PostClassifier:
    def __init__(self):
        with open("config/keywords.yaml") as f:
            kw = yaml.safe_load(f)
        self.hiring_kw = [k.lower() for k in kw["hiring_keywords"]]
        self.funding_kw = [k.lower() for k in kw["funding_keywords"]]
        self.tech_kw = [k.lower() for k in kw["tech_keywords"]]
        self.exclude = [k.lower() for k in kw["exclude_patterns"]]

        with open("config/blocklist.yaml") as f:
            bl = yaml.safe_load(f)
        self.blocked_usernames = [u.lower() for u in bl.get("blocked_usernames", [])]
        self.blocked_companies = [c.lower() for c in bl.get("blocked_companies", [])]
        self.blocked_domains = [d.lower() for d in bl.get("blocked_domains", [])]

        # Strong relevance signals for actual AI/ML hiring posts
        self.ai_role_markers = [
            "ai engineer",
            "ml engineer",
            "machine learning engineer",
            "data scientist",
            "research scientist",
            "applied scientist",
            "llm engineer",
            "nlp engineer",
            "computer vision engineer",
            "mlops engineer",
            "generative ai engineer",
            "ai researcher",
            "ml researcher",
            "applied ml",
            "deep learning engineer",
        ]
        self.position_nouns = [
            "engineer",
            "scientist",
            "researcher",
            "developer",
            "role",
            "position",
            "opening",
        ]
        self.funding_strong_markers = [
            "series a",
            "series b",
            "series c",
            "series d",
            "seed round",
            "pre-seed",
            "raised $",
            "raised usd",
            "secured funding",
            "backed by",
            "valuation",
        ]
        self.noise_markers = [
            "killed",
            "murdered",
            "war",
            "earthquake",
            "flood",
            "sports",
            "election",
            "movie",
            "celebrity",
            "crypto giveaway",
            "airdrop",
        ]
        # Patterns that indicate commentary ABOUT hiring, not actual hiring
        self.opinion_patterns = [
            r"^stop\s+hiring",
            r"^why\s+(companies|startups|you)\s+(can't|don't|shouldn't|fail)",
            r"\bthe truth about\s+(hiring|recruiting)\b",
            r"\bi keep seeing\s+(job postings|companies|startups)\b",
            r"\bthat person (either )?doesn'?t exist\b",
            r"\bhere'?s what (actually|really) works\b",
            r"\bcompetitive advantage isn'?t a hire\b",
            r"\bwhat (no one|nobody) tells you about\b",
            r"^(unpopular|hot|controversial)\s+(opinion|take)",
            r"\bfree\b.{0,30}\bkit\b",
            r"\bgiving away\b.{0,50}\b(founders|startups|companies)\b",
        ]

    def classify(self, post: dict) -> str | None:
        """
        Classify a post as 'hiring', 'funding', 'both', or None (noise).

        Returns None if the post should be dropped.
        """
        text = self._normalize(post.get("text", ""))
        source_url = (post.get("source_url", "") or "").lower()
        author = (
            post.get("author_username", "") or post.get("author", "")
        ).lower()

        if len(text) < 30:
            return None

        for pattern in self.exclude:
            if pattern in text:
                return None

        if any(blocked in author for blocked in self.blocked_usernames):
            return None
        if any(company in text for company in self.blocked_companies):
            return None
        if any(domain in source_url for domain in self.blocked_domains):
            return None
        if any(noise in text for noise in self.noise_markers):
            return None
        if any(re.search(pat, text) for pat in self.opinion_patterns):
            return None

        has_tech = any(kw in text for kw in self.tech_kw)
        if not has_tech:
            return None

        # Weighted relevance checks
        hiring_score = self._hiring_score(text)
        funding_score = self._funding_score(text)

        has_hiring = hiring_score >= 4
        has_funding = funding_score >= 4

        # LLM relevance: drop news/commentary (e.g. "IBM plans to hire..." as general news)
        if has_hiring and has_funding:
            if not _is_actual_job_or_funding_llm(text):
                return None
            return "both"
        if has_hiring:
            if not _is_actual_job_or_funding_llm(text):
                return None
            return "hiring"
        if has_funding:
            if not _is_actual_job_or_funding_llm(text):
                return None
            return "funding"
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _hiring_score(self, text: str) -> int:
        score = 0

        # Explicit hiring language
        if any(kw in text for kw in self.hiring_kw):
            score += 2

        # Role noun + hiring intent together indicates real position
        has_position_noun = any(noun in text for noun in self.position_nouns)
        if has_position_noun:
            score += 1

        # Strong AI role match
        if any(marker in text for marker in self.ai_role_markers):
            score += 3

        # "we are hiring ... for/on/at" often indicates genuine company post
        if re.search(r"\bwe('re| are)? hiring\b", text):
            score += 1
        if re.search(r"\b(hiring|looking for|open role)\b.*\b(ai|ml|llm|nlp|vision)\b", text):
            score += 1

        return score

    def _funding_score(self, text: str) -> int:
        score = 0

        if any(kw in text for kw in self.funding_kw):
            score += 2

        if any(marker in text for marker in self.funding_strong_markers):
            score += 2

        if re.search(r"\$\s?\d+([.,]\d+)?\s?(m|b|million|billion)\b", text):
            score += 2

        # Ensure funding post is still AI/ML related
        if any(kw in text for kw in ["ai", "ml", "llm", "machine learning", "artificial intelligence"]):
            score += 1

        return score
