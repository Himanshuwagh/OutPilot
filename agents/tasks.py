"""
Task definitions for each CrewAI agent.
"""

from crewai import Task

from agents.tools import (
    scrape_all_sources,
    process_and_store_leads,
    research_contacts,
    draft_cold_emails,
    send_emails,
)


def create_scout_task(agent) -> Task:
    return Task(
        description=(
            "Scrape X.com, LinkedIn, and news sites for AI/ML hiring and funding "
            "posts from the last 24 hours. Return all raw posts as a list."
        ),
        expected_output="A list of raw post dictionaries from all sources.",
        agent=agent,
        tools=[scrape_all_sources],
    )


def create_analyst_task(agent, scout_task: Task) -> Task:
    return Task(
        description=(
            "Take the raw scraped posts, classify each as hiring/funding/both, "
            "extract company name, role, funding amount, location. "
            "Deduplicate against existing Notion entries. "
            "Store only new leads in Notion Leads database."
        ),
        expected_output="A list of newly stored lead dictionaries with page_ids.",
        agent=agent,
        tools=[process_and_store_leads],
        context=[scout_task],
    )


def create_researcher_task(agent, analyst_task: Task) -> Task:
    return Task(
        description=(
            "For each new lead: find the company's website domain, "
            "search LinkedIn for HR/recruiters/managers, "
            "guess email patterns and verify via SMTP. "
            "Store verified contacts in Notion Contacts database."
        ),
        expected_output="A list of contact dictionaries with verified emails and page_ids.",
        agent=agent,
        tools=[research_contacts],
        context=[analyst_task],
    )


def create_writer_task(agent, researcher_task: Task) -> Task:
    return Task(
        description=(
            "For each contact with a verified email, draft a personalized cold email "
            "using the appropriate template (funding/hiring/both). "
            "Use Groq LLM. Store drafts in Notion Outreach database."
        ),
        expected_output="A list of email draft dictionaries ready to send.",
        agent=agent,
        tools=[draft_cold_emails],
        context=[researcher_task],
    )


def create_sender_task(agent, writer_task: Task) -> Task:
    return Task(
        description=(
            "Send the drafted cold emails via Gmail SMTP with rate limiting. "
            "Max 25 per day with 30-60 second delays between sends. "
            "Update Notion status to 'sent' or 'bounced'."
        ),
        expected_output="A summary of how many emails were sent, failed, and remaining.",
        agent=agent,
        tools=[send_emails],
        context=[writer_task],
    )
