"""
Extract structured information from post text:
company name, role, funding amount, location, remote status, apply URL.

Uses multi-strategy company extraction (regex -> URL hints -> Groq LLM fallback).
"""

import os
import re
import logging
from typing import Optional
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

_groq_client = None


def _get_groq():
    """Lazy init Groq client for company extraction fallback."""
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if api_key:
            from groq import Groq
            _groq_client = Groq(api_key=api_key)
    return _groq_client


class InfoExtractor:
    def __init__(self):
        with open("config/roles.yaml") as f:
            self.roles = yaml.safe_load(f)["roles"]
        with open("config/keywords.yaml") as f:
            kw = yaml.safe_load(f)
            self.tech_keywords = kw["tech_keywords"]
            self.location_kw = kw["location_keywords"]

    def extract(self, post: dict) -> dict:
        """Enrich a post dict with extracted fields."""
        text = post.get("text", "")
        author = post.get("author_display_name", "") or post.get("author", "")
        source_url = post.get("source_url", "") or ""
        author_company = post.get("author_company", "")

        post["company_name"] = self._company(text, author, source_url, author_company)
        post["role"] = self._role(text)
        post["funding_amount"] = self._funding_amount(text)
        post["tech_keywords"] = self._tech_keywords(text)

        country, remote = self._location(text)
        post["country"] = country
        post["remote"] = remote

        apply_url, app_type = self._apply_details(text)
        post["apply_url"] = apply_url
        post["application_type"] = app_type

        # Extract domain hint from URLs in the post for later email finding
        post["domain_hint"] = self._domain_from_urls(text, apply_url)

        # Eligibility signals
        post["required_years"] = self._required_years(text)
        post["is_senior_role"] = self._is_senior_role(text, post["role"])
        post["is_us_only"] = self._is_us_only(text)
        post["location_scope"] = self._location_scope(country=post["country"], remote=post["remote"])

        return post

    # ------------------------------------------------------------------
    # Company name: multi-strategy
    # ------------------------------------------------------------------

    def _company(self, text: str, author: str, source_url: str, author_company: str = "") -> str:
        # Strategy 0: Company resolved from poster's LinkedIn profile (strongest for job posts)
        if author_company and len(author_company) > 1:
            return author_company

        # Strategy 1: Regex patterns from post text
        name = self._company_from_regex(text)
        if name:
            return name

        # Strategy 2: Extract from URLs in the post (career pages, company websites)
        name = self._company_from_post_urls(text)
        if name:
            return name

        # Strategy 3: Use Groq LLM to extract company name from the full post
        name = self._company_from_llm(text)
        if name:
            return name

        # Strategy 4: Author name cleanup (often a company page on LinkedIn)
        name = self._company_from_author(author)
        if name:
            return name

        return "Unknown"

    def _company_from_regex(self, text: str) -> str:
        """Extract company via common text patterns."""
        patterns = [
            r"(?:join|work at|join us at|come join)\s+(@?\w[\w\s&.'-]*?)(?:\s+as\b|\s+to\b|\s*[,!.])",
            r"we\s+at\s+(@?\w[\w\s&.'-]*?)(?:\s+are\b|\s*[,.])",
            r"@(\w+)\s+is\s+hiring",
            r"at\s+(@?\w[\w\s&.'-]*?),?\s+we(?:'re|\s+are)",
            r"(?:hiring at|openings? at|positions? at)\s+(@?\w[\w\s&.'-]*?)(?:\s*[,!.]|\s+for\b)",
            r"^(@?\w[\w\s&.'-]*?)\s+is\s+(?:hiring|looking|seeking)",
        ]
        stop_words = {"us", "our", "the", "team", "a", "an", "my", "this", "we", "i"}

        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                name = m.group(1).strip("@ ").strip()
                if name.lower() not in stop_words and len(name) > 1:
                    return name
        return ""

    def _company_from_post_urls(self, text: str) -> str:
        """Infer company from career/job URLs in the post."""
        urls = re.findall(r"https?://[^\s]+", text)
        skip = {"linkedin.com", "twitter.com", "x.com", "google.com", "github.com",
                "forms.gle", "docs.google.com", "bit.ly", "t.co", "youtu.be"}

        for url in urls:
            url = url.rstrip(".,;:)")
            domain = urlparse(url).netloc.lower()
            domain = re.sub(r"^www\.", "", domain)

            if any(s in domain for s in skip):
                continue
            if not domain or "." not in domain:
                continue

            # Career/job pages often reveal the company
            if any(x in url.lower() for x in ["career", "jobs", "/job", "greenhouse", "lever.co", "apply"]):
                name = domain.split(".")[0]
                if name and len(name) > 2:
                    return name.replace("-", " ").title()

            # Any company-owned domain
            name = domain.split(".")[0]
            if name and len(name) > 2 and name not in {"www", "app", "api", "mail"}:
                return name.replace("-", " ").title()

        return ""

    def _company_from_llm(self, text: str) -> str:
        """Use Groq to extract company name from post text."""
        client = _get_groq()
        if not client:
            return ""

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": (
                        "Extract the company name from this job/funding post. "
                        "Return ONLY the company name, nothing else. "
                        "If you cannot determine it, return exactly: UNKNOWN"
                    )},
                    {"role": "user", "content": text[:500]},
                ],
                temperature=0.0,
                max_tokens=30,
            )
            name = resp.choices[0].message.content.strip().strip('"').strip("'")
            if name and name.upper() != "UNKNOWN" and len(name) > 1 and len(name) < 80:
                return name
        except Exception as exc:
            logger.debug("LLM company extraction failed: %s", exc)

        return ""

    @staticmethod
    def _company_from_author(author: str) -> str:
        """Clean up author name as company fallback."""
        if not author:
            return ""
        name = author.split("|")[0].split("@")[0].split("-")[0].strip()
        skip = {"unknown", "n/a", "none", "linkedin member", "user"}
        if name.lower() in skip or len(name) < 2:
            return ""
        return name

    # ------------------------------------------------------------------
    # Domain hint from URLs in the post
    # ------------------------------------------------------------------

    @staticmethod
    def _domain_from_urls(text: str, apply_url: Optional[str] = None) -> str:
        """Extract a company domain from URLs found in the post."""
        skip = {"linkedin.com", "twitter.com", "x.com", "google.com", "github.com",
                "forms.gle", "docs.google.com", "bit.ly", "t.co", "youtu.be",
                "medium.com", "substack.com"}

        urls = re.findall(r"https?://[^\s]+", text)
        if apply_url:
            urls.insert(0, apply_url)

        for url in urls:
            url = url.rstrip(".,;:)")
            domain = urlparse(url).netloc.lower()
            domain = re.sub(r"^www\.", "", domain)
            if domain and "." in domain and not any(s in domain for s in skip):
                return domain
        return ""

    # ------------------------------------------------------------------
    # Role extraction
    # ------------------------------------------------------------------

    def _role(self, text: str) -> str:
        text_lower = text.lower()
        for role in self.roles:
            if role.lower() in text_lower:
                return role
        junior_patterns = [
            "junior ai engineer",
            "junior ml engineer",
            "junior machine learning engineer",
            "junior data scientist",
            "entry level ai engineer",
            "entry level machine learning engineer",
            "new grad ai engineer",
            "new grad ml engineer",
            "graduate ai engineer",
            "ml intern",
            "ai intern",
            "research intern",
        ]
        for marker in junior_patterns:
            if marker in text_lower:
                return marker.title()
        return ""

    # ------------------------------------------------------------------
    # Funding, tech, location, apply details
    # ------------------------------------------------------------------

    def _funding_amount(self, text: str) -> str:
        patterns = [
            r"\$[\d,.]+\s*[BMbm](?:illion|n)?",
            r"\$[\d,.]+\s*(?:million|billion)",
            r"(?:raised|secured|closed)\s+\$[\d,.]+\s*[BMbm]?",
            r"(?:series\s+[a-eA-E])\s*(?:round)?",
            r"seed\s+round",
            r"pre-seed",
        ]
        findings = []
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                findings.append(m.group(0).strip())
        return "; ".join(findings) if findings else ""

    def _tech_keywords(self, text: str) -> str:
        text_lower = text.lower()
        found = sorted({kw for kw in self.tech_keywords if kw.lower() in text_lower})
        return ", ".join(found)

    def _location(self, text: str) -> tuple[Optional[str], bool]:
        text_lower = text.lower()
        is_remote = any(kw.lower() in text_lower for kw in self.location_kw["remote"])

        for kw in self.location_kw["united_states"]:
            if kw.lower() in text_lower:
                return "United States", is_remote
        for kw in self.location_kw["india"]:
            if kw.lower() in text_lower:
                return "India", is_remote
        if is_remote:
            return None, True
        return None, False

    def _apply_details(self, text: str) -> tuple[Optional[str], str]:
        urls = re.findall(r"https?://[^\s]+", text)
        for url in urls:
            url = url.rstrip(".,;:)")
            domain = urlparse(url).netloc.lower()

            if any(x in url.lower() for x in ["career", "jobs", "/job", "apply"]):
                return url, "careers_page"
            if "greenhouse" in domain:
                return url, "careers_page"
            if "lever.co" in domain:
                return url, "careers_page"
            if "linkedin.com" in domain:
                return url, "linkedin"
            if "forms.gle" in domain or "docs.google.com/forms" in url:
                return url, "google_form"

        if re.search(r"\bdm\b|\bdirect message\b", text, re.IGNORECASE):
            return None, "dm"
        return None, "unknown"

    # ------------------------------------------------------------------
    # Eligibility signals
    # ------------------------------------------------------------------

    def _required_years(self, text: str) -> Optional[int]:
        patterns = [
            r"\b(\d+)\+?\s*(?:years|yrs)\s+(?:of\s+)?(?:experience|exp)\b",
            r"\bminimum\s+(\d+)\s*(?:years|yrs)\b",
            r"\bat\s+least\s+(\d+)\s*(?:years|yrs)\b",
            r"\brequires?\s+(\d+)\+?\s*(?:years|yrs)\b",
            r"\b(\d+)\s*-\s*(\d+)\s*(?:years|yrs)\s+(?:of\s+)?(?:experience|exp)\b",
            r"\b(\d+)\s+to\s+(\d+)\s*(?:years|yrs)\s+(?:of\s+)?(?:experience|exp)\b",
        ]
        text_lower = text.lower()
        best: Optional[int] = None
        for pat in patterns:
            for m in re.finditer(pat, text_lower, re.IGNORECASE):
                if m.lastindex is None:
                    continue
                val = int(m.group(1))
                if best is None or val > best:
                    best = val
        return best

    def _is_senior_role(self, text: str, extracted_role: str = "") -> bool:
        title_markers = [
            "senior", "sr ", "sr.", "staff ", "principal",
            "lead ", "manager", "director", "vp ", "vice president",
            "head of", "architect", "cto", "chief ",
        ]

        if extracted_role:
            role_lower = extracted_role.lower()
            return any(m in role_lower for m in title_markers)

        text_lower = text.lower()
        senior_role_patterns = [
            r"\b(?:senior|sr\.?|staff|principal)\s+(?:\w+\s+){0,2}(?:engineer|scientist|researcher|developer)\b",
            r"\b(?:director|vp|head)\s+of\s+\w+",
            r"\bcto\b",
            r"\bchief\s+(?:technology|ai|data|science)\b",
        ]
        return any(re.search(pat, text_lower) for pat in senior_role_patterns)

    def _is_us_only(self, text: str) -> bool:
        text_lower = text.lower()
        us_only_patterns = [
            r"\bus only\b", r"\busa only\b", r"\bunited states only\b",
            r"\bu\.s\. only\b", r"\bus candidates only\b",
            r"\bmust be based in the us\b", r"\bremote \(us\)\b",
            r"\bus timezone only\b", r"\bonly in usa\b",
        ]
        return any(re.search(pat, text_lower) for pat in us_only_patterns)

    @staticmethod
    def _location_scope(country: Optional[str], remote: bool) -> str:
        if remote:
            return "remote"
        if country == "United States":
            return "us"
        if country:
            return "non_us"
        return "unknown"
