"""
Free email finder: multi-strategy approach.

Strategies (in order):
1. Scrape company website (/about, /team, /contact) for public emails
2. Pattern guessing + SMTP verification (first.last@domain.com, etc.)
3. GitHub public email scraping (for tech roles)

Replaces paid services like Hunter.io / Skrapp.io.
"""

import logging
import re
import smtplib
import socket
import time
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

# Generic role aliases to filter out (not actual people)
GENERIC_EMAILS = {
    "info", "contact", "hello", "support", "admin", "sales",
    "team", "career", "careers", "jobs", "hr", "office",
    "press", "marketing", "help", "noreply", "no-reply",
}


class EmailFinder:
    """Multi-strategy email finder."""

    def __init__(self):
        with open("config/email_patterns.yaml") as f:
            self.patterns = yaml.safe_load(f)["patterns"]
        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)
        self.smtp_delay = cfg["research"]["email_smtp_delay"]

        self._mx_cache: dict[str, list[str]] = {}
        self._website_emails_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> dict:
        """
        Try all strategies and return the best email.

        Returns:
            {
                "email": "verified@example.com" or "",
                "confidence": "high" | "medium" | "low",
                "all_candidates": [...],
                "method": "website_scrape" | "smtp_verified" | "pattern_guess" | "github" | "",
            }
        """
        first = re.sub(r"[^a-z]", "", first_name.lower())
        last = re.sub(r"[^a-z]", "", last_name.lower())
        full_name_lower = f"{first} {last}"

        # ---- Strategy 1: Website scraping ----
        website_email = self._match_website_email(first, last, domain)
        if website_email:
            logger.info("Found email via website scrape: %s", website_email)
            return {
                "email": website_email,
                "confidence": "high",
                "all_candidates": [website_email],
                "method": "website_scrape",
            }

        # ---- Strategy 2: Pattern guessing + SMTP verification ----
        f_initial = first[0] if first else ""
        l_initial = last[0] if last else ""

        candidates = []
        for pattern in self.patterns:
            email = (
                pattern.replace("{first}", first)
                .replace("{last}", last)
                .replace("{f}", f_initial)
                .replace("{l}", l_initial)
                .replace("{domain}", domain)
            )
            if email not in candidates:
                candidates.append(email)

        mx_hosts = self._get_mx(domain)
        if mx_hosts:
            is_catchall = self._detect_catchall(mx_hosts[0], domain)

            for candidate in candidates:
                time.sleep(self.smtp_delay)
                valid = self._smtp_verify(candidate, mx_hosts[0])

                if valid:
                    if is_catchall:
                        logger.info("Catch-all domain, accepting first pattern: %s", candidate)
                        return {
                            "email": candidate,
                            "confidence": "medium",
                            "all_candidates": candidates,
                            "method": "pattern_guess",
                        }
                    logger.info("SMTP-verified email: %s", candidate)
                    return {
                        "email": candidate,
                        "confidence": "high",
                        "all_candidates": candidates,
                        "method": "smtp_verified",
                    }
        else:
            logger.warning("No MX records for %s", domain)

        # ---- Strategy 3: GitHub public email ----
        github_email = self._github_email(first_name, last_name, domain)
        if github_email:
            logger.info("Found email via GitHub: %s", github_email)
            return {
                "email": github_email,
                "confidence": "medium",
                "all_candidates": candidates + [github_email],
                "method": "github",
            }

        # ---- Fallback: return best-guess pattern (no verification) ----
        if candidates:
            best_guess = candidates[0]
            logger.info("Returning best-guess (unverified): %s", best_guess)
            return {
                "email": best_guess,
                "confidence": "low",
                "all_candidates": candidates,
                "method": "pattern_guess",
            }

        logger.info("No email found for %s %s @ %s", first_name, last_name, domain)
        return {"email": "", "confidence": "low", "all_candidates": candidates, "method": ""}

    # ------------------------------------------------------------------
    # Strategy 1: Website email scraping
    # ------------------------------------------------------------------

    def scrape_website_emails(self, domain: str) -> list[str]:
        """
        Scrape a company's website for public email addresses.
        Crawls common pages: /, /about, /team, /contact, /careers.
        Returns a list of unique emails found.
        """
        if domain in self._website_emails_cache:
            return self._website_emails_cache[domain]

        pages = ["", "/about", "/about-us", "/team", "/our-team",
                 "/contact", "/contact-us", "/careers", "/jobs"]
        found_emails: set[str] = set()

        for page in pages:
            url = f"https://{domain}{page}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
                if resp.status_code != 200:
                    continue
                emails = self._extract_emails_from_html(resp.text, domain)
                found_emails.update(emails)
            except Exception:
                continue

            if len(found_emails) >= 10:
                break

        result = sorted(found_emails)
        self._website_emails_cache[domain] = result
        if result:
            logger.info("Found %d emails on %s website", len(result), domain)
        return result

    def _extract_emails_from_html(self, html: str, domain: str) -> list[str]:
        """Pull email addresses from HTML, filtering out generic ones."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")

        # Find all emails in text
        raw_emails = re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text
        )

        # Also check mailto: links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "mailto:" in href:
                email = href.replace("mailto:", "").split("?")[0].strip()
                if "@" in email:
                    raw_emails.append(email)

        # Filter: keep only emails at the company domain (or close variants)
        domain_root = domain.split(".")[-2] if "." in domain else domain
        good: list[str] = []
        for email in raw_emails:
            email = email.lower().strip()
            local = email.split("@")[0]
            email_domain = email.split("@")[1] if "@" in email else ""

            # Must be at a domain related to the company
            if domain_root not in email_domain:
                continue
            # Skip generic addresses
            if local in GENERIC_EMAILS:
                continue
            if email not in good:
                good.append(email)

        return good

    def _match_website_email(self, first: str, last: str, domain: str) -> str:
        """Check if any scraped website email matches the person's name."""
        website_emails = self.scrape_website_emails(domain)
        if not website_emails:
            return ""

        for email in website_emails:
            local = email.split("@")[0].lower()
            # Direct match: first.last, firstlast, f.last, first, etc.
            if first and last:
                if f"{first}.{last}" in local:
                    return email
                if f"{first}{last}" in local:
                    return email
                if f"{first[0]}{last}" in local:
                    return email
                if f"{first[0]}.{last}" in local:
                    return email
            if first and local == first:
                return email

        return ""

    # ------------------------------------------------------------------
    # Strategy 3: GitHub public email
    # ------------------------------------------------------------------

    def _github_email(self, first_name: str, last_name: str, domain: str) -> str:
        """Search GitHub for the person and check their public email."""
        query = f"{first_name} {last_name}"
        url = f"https://api.github.com/search/users?q={requests.utils.requote_uri(query)}&per_page=5"

        try:
            resp = requests.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=10)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            items = data.get("items", [])
        except Exception:
            return ""

        domain_root = domain.split(".")[-2] if "." in domain else domain

        for user in items:
            login = user.get("login", "")
            if not login:
                continue

            # Fetch user profile for public email
            try:
                profile_resp = requests.get(
                    f"https://api.github.com/users/{login}",
                    headers={"Accept": "application/vnd.github.v3+json"},
                    timeout=10,
                )
                if profile_resp.status_code != 200:
                    continue
                profile = profile_resp.json()
                email = profile.get("email", "") or ""
                if email and domain_root in email.lower():
                    return email.lower()

                # Also check recent public events for email in commits
                events_email = self._github_commit_email(login, domain_root)
                if events_email:
                    return events_email

            except Exception:
                continue

        return ""

    @staticmethod
    def _github_commit_email(login: str, domain_root: str) -> str:
        """Check a GitHub user's recent public events for commit emails."""
        try:
            resp = requests.get(
                f"https://api.github.com/users/{login}/events/public?per_page=10",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return ""
            events = resp.json()
            for event in events:
                if event.get("type") != "PushEvent":
                    continue
                commits = event.get("payload", {}).get("commits", [])
                for commit in commits:
                    email = commit.get("author", {}).get("email", "")
                    if email and domain_root in email.lower() and "noreply" not in email.lower():
                        return email.lower()
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # MX lookup
    # ------------------------------------------------------------------

    def _get_mx(self, domain: str) -> list[str]:
        if domain in self._mx_cache:
            return self._mx_cache[domain]
        try:
            answers = dns.resolver.resolve(domain, "MX")
            hosts = sorted(answers, key=lambda r: r.preference)
            result = [str(r.exchange).rstrip(".") for r in hosts]
            self._mx_cache[domain] = result
            return result
        except Exception as exc:
            logger.debug("MX lookup failed for %s: %s", domain, exc)
            self._mx_cache[domain] = []
            return []

    # ------------------------------------------------------------------
    # Catch-all detection
    # ------------------------------------------------------------------

    def _detect_catchall(self, mx_host: str, domain: str) -> bool:
        """A catch-all domain accepts any address, making SMTP verify unreliable."""
        fake = f"definitely_not_a_real_user_1234567@{domain}"
        return self._smtp_verify(fake, mx_host)

    # ------------------------------------------------------------------
    # SMTP verification
    # ------------------------------------------------------------------

    def _smtp_verify(self, email: str, mx_host: str) -> bool:
        """
        Connect to the MX server and check if the email is accepted.
        Returns True if the server responds 250 to RCPT TO.
        """
        try:
            with smtplib.SMTP(timeout=10) as smtp:
                smtp.connect(mx_host, 25)
                smtp.helo("verify.local")
                smtp.mail("check@verify.local")
                code, _ = smtp.rcpt(email)
                return code == 250
        except smtplib.SMTPServerDisconnected:
            return False
        except smtplib.SMTPConnectError:
            return False
        except socket.timeout:
            return False
        except Exception as exc:
            logger.debug("SMTP verify error for %s: %s", email, exc)
            return False
