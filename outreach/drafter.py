"""
Cold email drafter using Groq (free tier) with llama-3.3-70b-versatile.
Generates personalized emails based on post type.
"""

import os
import logging
import time

from groq import Groq

import yaml

from outreach.templates import SYSTEM_PROMPT, get_template

logger = logging.getLogger(__name__)


class EmailDrafter:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        self.client = Groq(api_key=api_key)

        with open("config/settings.yaml") as f:
            cfg = yaml.safe_load(f)
        self.model = cfg["outreach"]["groq_model"]

        self.your_name = os.getenv("YOUR_NAME", "")
        self.your_role = os.getenv("YOUR_ROLE", "")
        self.your_skills = os.getenv("YOUR_SKILLS", "")
        self.resume_link = os.getenv("YOUR_RESUME_LINK", "")
        self.linkedin_url = os.getenv("YOUR_LINKEDIN", "")
        self.github_url = os.getenv("YOUR_GITHUB", "")
        self.portfolio_url = os.getenv("YOUR_PORTFOLIO", "")

    def draft(self, lead: dict, contact: dict) -> dict:
        """
        Generate a cold email for a given lead + contact.

        Args:
            lead: dict with company_name, post_type, role, funding_amount
            contact: dict with name, role_title

        Returns:
            {"subject": "...", "body": "..."}
        """
        post_type = lead.get("post_type", "hiring")
        template = get_template(post_type)

        prompt = template.format(
            contact_name=contact.get("name", "Hiring Manager"),
            contact_title=contact.get("role_title", ""),
            company=lead.get("company_name", "your company"),
            role=lead.get("role", "an AI/ML role"),
            funding_details=lead.get("funding_amount", "secured new funding"),
            your_name=self.your_name,
            your_role=self.your_role,
            your_skills=self.your_skills,
            resume_link=self.resume_link,
            linkedin_url=self.linkedin_url,
            github_url=self.github_url,
            portfolio_url=self.portfolio_url,
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("Groq API error: %s", exc)
            time.sleep(5)
            return {"subject": "", "body": ""}

        subject, body = self._parse_response(raw)
        logger.info(
            "Drafted email for %s at %s (type=%s)",
            contact.get("name"),
            lead.get("company_name"),
            post_type,
        )
        return {"subject": subject, "body": body}

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, str]:
        """Split LLM response into subject and body."""
        lines = raw.strip().split("\n")
        subject = ""
        body_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower().startswith("subject:"):
                subject = stripped[len("subject:"):].strip().strip('"')
            else:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        if not subject:
            subject = "Quick note about your AI team"

        return subject, body
