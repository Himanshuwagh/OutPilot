"""
CrewAI tool wrappers that bridge our modules into CrewAI's tool interface.
Each tool is a simple callable that agents can invoke.

Also contains the company-targeted outreach pipeline (run_company_outreach)
which can be invoked directly from main.py / demo.py.
"""

import asyncio
import logging
import re
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
from research.accurate_email_finder import AccurateEmailFinder
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

    # X.com (funding + hiring flows)
    try:
        x = XScraper(
            browser_data_dir=xcfg["browser_data_dir"],
            headless=_headless,
            max_tweets=xcfg["max_tweets_per_session"],
            max_scrolls=xcfg["max_scrolls"],
            scroll_delay_min=xcfg["scroll_delay_min"],
            scroll_delay_max=xcfg["scroll_delay_max"],
            daily_quota=xcfg["daily_action_quota"],
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        x_posts = loop.run_until_complete(x.scrape())
        all_posts.extend(x_posts)
    except Exception as exc:
        logger.error("X.com scraper failed: %s", exc)

    # LinkedIn (funding + job flows)
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

    skipped = {"dedup_fp": 0, "classify": 0, "company": 0, "years": 0,
               "senior": 0, "us_only": 0, "location": 0, "dedup_co": 0}

    for post in posts:
        text_preview = (post.get("text", "") or "")[:80]

        # Layer 1 dedup: fingerprint
        if dedup.is_duplicate_fingerprint(post):
            skipped["dedup_fp"] += 1
            continue

        # Classify
        post_type = classifier.classify(post)
        if not post_type:
            skipped["classify"] += 1
            logger.debug("Filtered (classify): %s", text_preview)
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
            skipped["company"] += 1
            logger.debug("Filtered (no company): %s", text_preview)
            continue

        # Junior / location filters only apply to hiring posts, not funding
        is_hiring_post = post_type in {"hiring", "both"}
        if is_hiring_post and prefs.get("junior_only", True):
            max_years = int(prefs.get("max_years_experience", 3))
            if required_years is not None and required_years > max_years:
                skipped["years"] += 1
                logger.debug("Filtered (years=%d > %d): %s", required_years, max_years, text_preview)
                continue
            if prefs.get("exclude_senior_titles", True) and is_senior_role:
                skipped["senior"] += 1
                logger.debug("Filtered (senior role=%s): %s", role, text_preview)
                continue

        if is_hiring_post and prefs.get("exclude_us_only_jobs", True) and is_us_only:
            skipped["us_only"] += 1
            continue
        if is_hiring_post and not prefs.get("allow_non_us_roles", True) and location_scope == "non_us":
            skipped["location"] += 1
            continue
        if is_hiring_post and not prefs.get("allow_remote_roles", True) and location_scope == "remote":
            skipped["location"] += 1
            continue

        if dedup.is_duplicate_company(company, post_type):
            skipped["dedup_co"] += 1
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

    if any(skipped.values()):
        logger.info(
            "Filter summary: %s (of %d posts)",
            ", ".join(f"{k}={v}" for k, v in skipped.items() if v),
            len(posts),
        )
    logger.info("Stored %d new leads in Notion", len(stored_leads))
    return stored_leads


# ------------------------------------------------------------------
# Tool: Research contacts for leads
# ------------------------------------------------------------------

@tool("research_contacts")
def research_contacts(leads: list[dict]) -> list[dict]:
    """For each lead, find company domain, LinkedIn contacts, guess+verify emails, store in Notion."""
    domain_finder = DomainFinder()
    email_finder = AccurateEmailFinder()
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
            name = person.get("name", "").strip()
            if not name:
                continue
            parts = name.split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
            elif len(parts) == 1:
                first = last = parts[0]
            else:
                continue
            first = re.sub(r"[^a-zA-Z]", "", first)
            last = re.sub(r"[^a-zA-Z]", "", last)
            if not first:
                continue

            # Find email via deep, evidence-based finder.
            result = email_finder.find_best_email(
                full_name=name,
                company_domain=domain,
                company_name=company,
                linkedin_url=person.get("linkedin_url", ""),
            )
            email = result.get("email", "")

            # Fallback: always build a best-guess email
            if not email and first and last:
                email = f"{first.lower()}.{last.lower()}@{domain}"

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


# ------------------------------------------------------------------
# Company-targeted outreach pipeline
# ------------------------------------------------------------------

async def run_company_outreach(
    company_name: str,
    role: str = "",
    domain_override: str = "",
    dry_run: bool = False,
    num_contacts: int = 5,
) -> dict:
    """
    Full company-targeted pipeline:
      1. Find company domain
      2. Search LinkedIn People for hiring managers / managers
      3. Find email addresses (website scrape -> pattern + SMTP -> GitHub)
      4. Store contacts in Notion
      5. Draft personalized cold emails via Groq LLM
      6. Send emails via Gmail (unless dry_run=True)

    Args:
        company_name: Target company (e.g. "OpenAI").
        role: Specific role to mention in emails (e.g. "ML Engineer").
        domain_override: Skip domain auto-detection (e.g. "openai.com").
        dry_run: If True, draft emails but don't send them.
        num_contacts: How many contacts to find (default 5).

    Returns a summary dict with counts and contact details.
    """
    li_cfg = _settings["scraping"]["linkedin"]

    summary = {
        "company": company_name,
        "contacts_found": 0,
        "emails_found": 0,
        "emails_stored_notion": 0,
        "drafts_created": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "contacts": [],
    }

    # ---- Step 1: Find company domain ----
    logger.info("=" * 60)
    logger.info("STEP 1: Finding domain for %s", company_name)
    logger.info("=" * 60)

    domain_finder = DomainFinder()
    domain = domain_override or domain_finder.find_domain(company_name)

    if not domain:
        logger.error(
            "Could not find domain for '%s'. Provide it with --domain.",
            company_name,
        )
        return summary

    logger.info("Domain: %s", domain)

    # ---- Step 2: Search LinkedIn People for managers ----
    logger.info("=" * 60)
    logger.info("STEP 2: Searching LinkedIn People for managers at %s", company_name)
    logger.info("=" * 60)

    contact_finder = ContactFinder(
        browser_data_dir=li_cfg["browser_data_dir"],
        headless=_headless,
        contacts_per_company=num_contacts,
        daily_quota=li_cfg["daily_action_quota"],
    )

    people: list[dict] = []
    try:
        await contact_finder.start()
        await contact_finder.ensure_logged_in(
            "https://www.linkedin.com/feed/", "feed"
        )
        people = await contact_finder.find_contacts(
            company_name, search_mode="managers"
        )
    except Exception as exc:
        logger.error("LinkedIn contact search failed: %s", exc)
    finally:
        try:
            await contact_finder.stop()
        except Exception:
            pass

    if not people:
        logger.warning(
            "No contacts found on LinkedIn for %s. "
            "Possible causes:\n"
            "  1. LinkedIn session expired — re-run: python setup_sessions.py --platform linkedin\n"
            "  2. LinkedIn changed their page layout (CSS selectors outdated)\n"
            "  3. Company name not matching any LinkedIn results\n"
            "  4. Daily LinkedIn quota exhausted",
            company_name,
        )
        return summary

    summary["contacts_found"] = len(people)
    logger.info("Found %d relevant people at %s", len(people), company_name)
    for p in people:
        logger.info("  - %s | %s | %s", p["name"], p["role_title"], p["linkedin_url"])

    # ---- Step 3: Find email addresses ----
    logger.info("=" * 60)
    logger.info("STEP 3: Finding email addresses for %d contacts", len(people))
    logger.info("=" * 60)

    email_finder = AccurateEmailFinder()

    contacts_with_emails: list[dict] = []
    for person in people:
        name = person.get("name", "").strip()
        if not name:
            continue

        # Parse name: handle "First Last", "First Middle Last",
        # "First", "Dr. First Last", etc.
        parts = name.split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
        elif len(parts) == 1:
            # Single name — use it as both first and last
            first = parts[0]
            last = parts[0]
        else:
            continue

        # Clean non-alpha chars (titles like "Dr.", "Jr.", "III")
        first = re.sub(r"[^a-zA-Z]", "", first)
        last = re.sub(r"[^a-zA-Z]", "", last)
        if not first:
            continue

        result = email_finder.find_best_email(
            full_name=name,
            company_domain=domain,
            company_name=company_name,
            linkedin_url=person.get("linkedin_url", ""),
        )
        email = result.get("email", "")

        # If EmailFinder returned empty (shouldn't happen), build a fallback
        if not email and first and last:
            email = f"{first.lower()}.{last.lower()}@{domain}"
            result = {
                "email": email,
                "confidence": "low",
                "all_candidates": [email],
                "method": "pattern_guess",
            }
            logger.info("  Built fallback email: %s", email)

        if email:
            person["email"] = email
            person["email_confidence"] = result.get("confidence", "low")
            person["email_method"] = result.get("method", "")
            contacts_with_emails.append(person)
            logger.info(
                "  [%s] %s -> %s (%s)",
                result.get("confidence", "?"),
                name,
                email,
                result.get("method", ""),
            )
        else:
            logger.warning("  No email found for %s", name)

    summary["emails_found"] = len(contacts_with_emails)

    if not contacts_with_emails:
        logger.warning("No emails found for any contacts at %s", company_name)
        return summary

    # ---- Step 4: Store contacts in Notion ----
    logger.info("=" * 60)
    logger.info("STEP 4: Storing %d contacts in Notion", len(contacts_with_emails))
    logger.info("=" * 60)

    notion = get_notion()
    notion.ensure_schemas()

    stored_contacts: list[dict] = []
    for contact in contacts_with_emails:
        email = contact.get("email", "")

        if notion.contact_exists(email):
            logger.info("  Contact %s already in Notion, skipping.", email)
            continue

        contact_data = {
            "name": contact["name"],
            "email": email,
            "role_title": contact.get("role_title", ""),
            "company_name": company_name,
            "email_confidence": contact.get("email_confidence", "low"),
            "linkedin_url": contact.get("linkedin_url", ""),
        }

        try:
            page_id = notion.add_contact(contact_data)
            contact["page_id"] = page_id
            stored_contacts.append(contact)
            logger.info("  Stored: %s (%s) -> %s", contact["name"], email, page_id)
        except Exception as exc:
            logger.error("  Failed to store %s: %s", contact["name"], exc)

    summary["emails_stored_notion"] = len(stored_contacts)

    if not stored_contacts:
        logger.info("All contacts already in Notion or failed to store.")
        stored_contacts = contacts_with_emails

    # ---- Step 5: Draft personalized cold emails ----
    logger.info("=" * 60)
    logger.info("STEP 5: Drafting cold emails for %d contacts", len(stored_contacts))
    logger.info("=" * 60)

    drafter = EmailDrafter()
    drafts: list[dict] = []

    for contact in stored_contacts:
        lead_info = {
            "company_name": company_name,
            "post_type": "hiring",
            "role": role or "an AI/ML role",
            "funding_amount": "",
        }

        result = drafter.draft(lead_info, contact)
        if not result.get("body"):
            logger.warning("  Empty draft for %s, skipping", contact["name"])
            continue

        outreach_data = {
            "subject": result["subject"],
            "contact_page_id": contact.get("page_id", ""),
            "email_draft": result["body"],
        }

        try:
            outreach_page_id = notion.add_outreach(outreach_data)
            drafts.append({
                "outreach_page_id": outreach_page_id,
                "to_email": contact.get("email", ""),
                "to_name": contact.get("name", ""),
                "subject": result["subject"],
                "body": result["body"],
            })
            logger.info(
                "  Draft created for %s: %s", contact["name"], result["subject"]
            )
        except Exception as exc:
            logger.error("  Failed to store draft for %s: %s", contact["name"], exc)

    summary["drafts_created"] = len(drafts)

    if not drafts:
        logger.warning("No email drafts created.")
        return summary

    # ---- Step 6: Send emails (skip if dry_run) ----
    if dry_run:
        logger.info("=" * 60)
        logger.info(
            "DRY RUN - Emails NOT sent. %d drafts stored in Notion.", len(drafts)
        )
        logger.info("=" * 60)
        for d in drafts:
            logger.info("  Would send to: %s <%s>", d["to_name"], d["to_email"])
            logger.info("  Subject: %s", d["subject"])
    else:
        logger.info("=" * 60)
        logger.info("STEP 6: Sending %d emails", len(drafts))
        logger.info("=" * 60)

        sender = EmailSender()
        sent = 0
        failed = 0

        for draft in drafts:
            if not sender.can_send():
                logger.warning(
                    "Daily email limit reached. Remaining drafts queued in Notion."
                )
                break

            success = sender.send_with_delay(
                draft["to_email"], draft["subject"], draft["body"]
            )

            if success:
                sent += 1
                if draft.get("outreach_page_id"):
                    try:
                        notion.update_outreach_status(
                            draft["outreach_page_id"], "sent"
                        )
                    except Exception:
                        pass
                logger.info("  Sent to %s <%s>", draft["to_name"], draft["to_email"])
            else:
                failed += 1
                if draft.get("outreach_page_id"):
                    try:
                        notion.update_outreach_status(
                            draft["outreach_page_id"], "bounced"
                        )
                    except Exception:
                        pass
                logger.warning(
                    "  Failed to send to %s <%s>", draft["to_name"], draft["to_email"]
                )

        summary["emails_sent"] = sent
        summary["emails_failed"] = failed

    # ---- Build summary ----
    summary["contacts"] = [
        {
            "name": c.get("name"),
            "email": c.get("email"),
            "role_title": c.get("role_title"),
            "linkedin_url": c.get("linkedin_url"),
            "confidence": c.get("email_confidence"),
        }
        for c in stored_contacts
    ]

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE for %s", company_name)
    logger.info("  Contacts found on LinkedIn: %d", summary["contacts_found"])
    logger.info("  Emails discovered: %d", summary["emails_found"])
    logger.info("  Stored in Notion: %d", summary["emails_stored_notion"])
    logger.info("  Email drafts created: %d", summary["drafts_created"])
    if not dry_run:
        logger.info("  Emails sent: %d", summary["emails_sent"])
        logger.info("  Emails failed: %d", summary["emails_failed"])
    logger.info("=" * 60)

    return summary
