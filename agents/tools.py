"""
CrewAI tool wrappers that bridge our modules into CrewAI's tool interface.
Each tool is a simple callable that agents can invoke.
"""

import asyncio
import logging
from typing import Any

from crewai.tools import tool

from scrapers.x_scraper import XScraper
from scrapers.linkedin_scraper import LinkedInPostScraper
from scrapers.news_scraper import NewsScraper
from processing.classifier import PostClassifier
from processing.extractor import InfoExtractor
from processing.deduplicator import Deduplicator, make_fingerprint
from storage.notion_client import NotionStorage
from research.domain_finder import DomainFinder
from research.contact_finder import ContactFinder
from research.email_finder import EmailFinder
from outreach.drafter import EmailDrafter
from outreach.sender import EmailSender

import yaml

logger = logging.getLogger(__name__)


# Load settings once
with open("config/settings.yaml") as _f:
    _settings = yaml.safe_load(_f)
_headless = _settings["scraping"].get("headless", True)


# ------------------------------------------------------------------
# Singletons (created lazily)
# ------------------------------------------------------------------
_notion: NotionStorage | None = None
_dedup: Deduplicator | None = None


def get_notion() -> NotionStorage:
    global _notion
    if _notion is None:
        _notion = NotionStorage()
    return _notion


def get_dedup() -> Deduplicator:
    global _dedup
    if _dedup is None:
        _dedup = Deduplicator(get_notion())
        _dedup.load_cache()
    return _dedup


# ------------------------------------------------------------------
# Tool: Scrape all sources
# ------------------------------------------------------------------

@tool("scrape_all_sources")
def scrape_all_sources(placeholder: str = "") -> list[dict]:
    """Scrape X.com, LinkedIn, and news sites for AI/ML hiring/funding posts from the last 24 hours."""
    all_posts: list[str | dict] = []

    xcfg = _settings["scraping"]["x"]
    licfg = _settings["scraping"]["linkedin"]

    # X.com
    try:
        x = XScraper(
            browser_data_dir=xcfg["browser_data_dir"],
            headless=_headless,
            max_tweets=xcfg["max_tweets_per_session"],
            max_scrolls=xcfg["max_scrolls"],
            scroll_delay_min=xcfg["scroll_delay_min"],
            scroll_delay_max=xcfg["scroll_delay_max"],
        )
        x_posts = asyncio.get_event_loop().run_until_complete(x.scrape())
        all_posts.extend(x_posts)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        x = XScraper(
            browser_data_dir=xcfg["browser_data_dir"],
            headless=_headless,
            max_tweets=xcfg["max_tweets_per_session"],
            max_scrolls=xcfg["max_scrolls"],
            scroll_delay_min=xcfg["scroll_delay_min"],
            scroll_delay_max=xcfg["scroll_delay_max"],
        )
        x_posts = loop.run_until_complete(x.scrape())
        all_posts.extend(x_posts)
    except Exception as exc:
        logger.error("X.com scraper failed: %s", exc)

    # LinkedIn
    try:
        li = LinkedInPostScraper(
            browser_data_dir=licfg["browser_data_dir"],
            headless=_headless,
            max_posts=licfg["max_posts_per_session"],
            max_scrolls=licfg["max_scrolls"],
            scroll_delay_min=licfg["scroll_delay_min"],
            scroll_delay_max=licfg["scroll_delay_max"],
            daily_quota=licfg["daily_action_quota"],
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        li_posts = loop.run_until_complete(li.scrape())
        all_posts.extend(li_posts)
    except Exception as exc:
        logger.error("LinkedIn scraper failed: %s", exc)

    # News
    try:
        news = NewsScraper()
        news_posts = news.scrape()
        all_posts.extend(news_posts)
    except Exception as exc:
        logger.error("News scraper failed: %s", exc)

    logger.info("Total raw posts scraped: %d", len(all_posts))
    return all_posts


# ------------------------------------------------------------------
# Tool: Classify, extract, dedup, and store leads
# ------------------------------------------------------------------

@tool("process_and_store_leads")
def process_and_store_leads(posts: list[dict]) -> list[dict]:
    """Classify posts (hiring/funding/both), extract info, dedup, and store in Notion Leads DB."""
    classifier = PostClassifier()
    extractor = InfoExtractor()
    dedup = get_dedup()
    notion = get_notion()
    prefs = _settings.get("processing", {}).get("candidate_preferences", {})

    stored_leads: list[dict] = []

    for post in posts:
        # Layer 1 dedup: fingerprint
        if dedup.is_duplicate_fingerprint(post):
            continue

        # Classify
        post_type = classifier.classify(post)
        if not post_type:
            continue
        post["post_type"] = post_type

        # Extract info
        post = extractor.extract(post)
        role = (post.get("role", "") or "").strip()
        required_years = post.get("required_years")
        is_senior_role = bool(post.get("is_senior_role"))
        is_us_only = bool(post.get("is_us_only"))
        location_scope = post.get("location_scope", "unknown")

        # Layer 2 dedup: company within window
        company = post.get("company_name", "Unknown")
        if not company or company.strip().lower() in {"unknown", "n/a", "none"}:
            # Drop items without identifiable company to keep results high quality.
            continue

        # Do NOT require explicit "junior" role text.
        # Keep posts even when role is missing, and only exclude when senior signals appear.
        # (Senior filtering is handled below via years/senior markers.)

        # Junior-focused filtering
        if prefs.get("junior_only", True):
            max_years = int(prefs.get("max_years_experience", 3))
            if required_years is not None and required_years > max_years:
                continue
            if prefs.get("exclude_senior_titles", True) and is_senior_role:
                continue

        # Location filtering preferences
        if prefs.get("exclude_us_only_jobs", True) and is_us_only:
            continue
        if not prefs.get("allow_non_us_roles", True) and location_scope == "non_us":
            continue
        if not prefs.get("allow_remote_roles", True) and location_scope == "remote":
            continue

        if dedup.is_duplicate_company(company, post_type):
            continue

        # Store in Notion
        fp = make_fingerprint(post)
        lead_data = {
            "company_name": company,
            "source_link": post.get("source_url", ""),
            "post_type": post_type,
            "role": role,
            "funding_amount": post.get("funding_amount", ""),
            "platform": post.get("platform", "unknown"),
            "fingerprint": fp,
            "domain_hint": post.get("domain_hint", ""),
        }

        try:
            page_id = notion.add_lead(lead_data)
            dedup.register_fingerprint(post)
            lead_data["page_id"] = page_id
            stored_leads.append(lead_data)
        except Exception as exc:
            logger.error("Failed to store lead for %s: %s", company, exc)

    logger.info("Stored %d new leads in Notion", len(stored_leads))
    return stored_leads


# ------------------------------------------------------------------
# Tool: Research contacts for leads
# ------------------------------------------------------------------

@tool("research_contacts")
def research_contacts(leads: list[dict]) -> list[dict]:
    """For each lead, find company domain, LinkedIn contacts, guess+verify emails, store in Notion."""
    domain_finder = DomainFinder()
    email_finder = EmailFinder()
    notion = get_notion()

    rcfg = _settings["research"]
    contacts_limit = rcfg["contacts_per_company"]
    max_leads_for_contact_search = rcfg.get("max_leads_for_contact_search", 20)

    all_contacts: list[dict] = []
    if not leads:
        return all_contacts

    # Process only the top leads to keep runtime predictable and quality high.
    def _lead_score(lead: dict) -> int:
        score = 0
        pt = lead.get("post_type", "")
        if pt == "both":
            score += 5
        elif pt == "funding":
            score += 4
        elif pt == "hiring":
            score += 3
        if lead.get("funding_amount"):
            score += 2
        if lead.get("role"):
            score += 1
        return score

    leads_to_process = sorted(leads, key=_lead_score, reverse=True)[:max_leads_for_contact_search]

    # Open LinkedIn ONCE, login once, reuse session for all companies.
    contact_finder = None
    loop = None
    try:
        contact_finder = ContactFinder(
            browser_data_dir=_settings["scraping"]["linkedin"]["browser_data_dir"],
            headless=_headless,
            contacts_per_company=contacts_limit,
            daily_quota=_settings["scraping"]["linkedin"]["daily_action_quota"],
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(contact_finder.start())
        loop.run_until_complete(
            contact_finder.ensure_logged_in(
                "https://www.linkedin.com/feed/", "feed"
            )
        )
    except Exception as exc:
        logger.error("Failed to initialize LinkedIn contact finder: %s", exc)
        if contact_finder and loop:
            try:
                loop.run_until_complete(contact_finder.stop())
                loop.close()
            except Exception:
                pass
        return all_contacts

    for lead in leads_to_process:
        company = lead.get("company_name", "")
        if not company:
            continue

        # Find domain — use domain_hint from post URLs first
        domain_hint = lead.get("domain_hint", "")
        domain = domain_finder.find_domain(company, domain_hint=domain_hint)
        if not domain:
            continue

        # Pre-scrape the company website for emails (cached per domain)
        email_finder.scrape_website_emails(domain)

        # Find people on LinkedIn
        try:
            people = loop.run_until_complete(contact_finder.find_contacts(company)) if loop else []
        except Exception as exc:
            logger.error("Contact search failed for %s: %s", company, exc)
            people = []

        for person in people:
            name = person.get("name", "")
            parts = name.split()
            if len(parts) < 2:
                continue
            first, last = parts[0], parts[-1]

            # Find email (website scrape -> pattern+SMTP -> GitHub)
            result = email_finder.find_email(first, last, domain)
            email = result.get("email", "")

            if not email:
                continue

            if notion.contact_exists(email):
                continue

            contact_data = {
                "name": name,
                "email": email,
                "role_title": person.get("role_title", ""),
                "lead_page_id": lead.get("page_id", ""),
                "email_confidence": result.get("confidence", "low"),
                "linkedin_url": person.get("linkedin_url", ""),
            }

            try:
                page_id = notion.add_contact(contact_data)
                contact_data["page_id"] = page_id
                contact_data["company_name"] = company
                contact_data["post_type"] = lead.get("post_type", "hiring")
                contact_data["role"] = lead.get("role", "")
                contact_data["funding_amount"] = lead.get("funding_amount", "")
                contact_data["platform"] = lead.get("platform", "unknown")
                all_contacts.append(contact_data)
            except Exception as exc:
                logger.error("Failed to store contact %s: %s", name, exc)

        # Update lead status
        try:
            notion.update_lead_status(lead.get("page_id", ""), "researching")
        except Exception:
            pass

    # Close LinkedIn browser once after all companies are processed.
    if contact_finder and loop:
        try:
            loop.run_until_complete(contact_finder.stop())
            loop.close()
        except Exception:
            pass

    logger.info("Found %d contacts total", len(all_contacts))
    return all_contacts


# ------------------------------------------------------------------
# Tool: Draft cold emails
# ------------------------------------------------------------------

@tool("draft_cold_emails")
def draft_cold_emails(contacts: list[dict]) -> list[dict]:
    """Draft personalized cold emails for each contact using Groq LLM."""
    drafter = EmailDrafter()
    notion = get_notion()

    drafts: list[dict] = []

    for contact in contacts:
        lead_info = {
            "company_name": contact.get("company_name", ""),
            "post_type": contact.get("post_type", "hiring"),
            "role": contact.get("role", ""),
            "funding_amount": contact.get("funding_amount", ""),
        }

        result = drafter.draft(lead_info, contact)
        if not result.get("body"):
            continue

        # Simple relevance scoring: prioritize funding/both, high-confidence emails, and platform
        score = 0
        post_type = lead_info["post_type"]
        if post_type == "funding":
            score += 4
        elif post_type == "both":
            score += 5
        elif post_type == "hiring":
            score += 3

        if lead_info.get("funding_amount"):
            score += 2

        confidence = contact.get("email_confidence", "low")
        if confidence == "high":
            score += 3
        elif confidence == "medium":
            score += 1

        platform = contact.get("platform", "unknown")
        if platform in {"linkedin", "x.com"}:
            score += 1

        outreach_data = {
            "subject": result["subject"],
            "contact_page_id": contact.get("page_id", ""),
            "email_draft": result["body"],
        }

        try:
            page_id = notion.add_outreach(outreach_data)
            drafts.append({
                "page_id": page_id,
                "to_email": contact.get("email", ""),
                "subject": result["subject"],
                "body": result["body"],
                "score": score,
            })
        except Exception as exc:
            logger.error("Failed to store draft: %s", exc)

    logger.info("Drafted %d emails", len(drafts))
    return drafts


# ------------------------------------------------------------------
# Tool: Send emails
# ------------------------------------------------------------------

@tool("send_emails")
def send_emails(drafts: list[dict]) -> str:
    """Send drafted cold emails via Gmail with rate limiting."""
    sender = EmailSender()
    notion = get_notion()

    sent = 0
    failed = 0

    # Prioritize top-scoring drafts and cap to 20 per day
    drafts_sorted = sorted(drafts, key=lambda d: d.get("score", 0), reverse=True)
    max_to_send = min(20, sender.remaining_today())

    for draft in drafts_sorted[:max_to_send]:
        if not sender.can_send():
            logger.warning("Daily send limit reached. Remaining drafts queued for tomorrow.")
            break

        to_email = draft.get("to_email", "")
        subject = draft.get("subject", "")
        body = draft.get("body", "")
        page_id = draft.get("page_id", "")

        success = sender.send_with_delay(to_email, subject, body)

        if success:
            sent += 1
            if page_id:
                try:
                    notion.update_outreach_status(page_id, "sent")
                except Exception:
                    pass
        else:
            failed += 1
            if page_id:
                try:
                    notion.update_outreach_status(page_id, "bounced")
                except Exception:
                    pass

    summary = f"Sent {sent} emails, {failed} failed, {sender.remaining_today()} remaining today."
    logger.info(summary)
    return summary
