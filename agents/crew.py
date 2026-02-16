"""
CrewAI agent and crew definitions.
Five agents in sequential pipeline: Scout -> Analyst -> Researcher -> Writer -> Sender.
"""

import os
import logging

from crewai import Agent, Crew, Process

from agents.tasks import (
    create_scout_task,
    create_analyst_task,
    create_researcher_task,
    create_writer_task,
    create_sender_task,
)

logger = logging.getLogger(__name__)


def build_crew() -> Crew:
    """Construct and return the cold outreach crew."""

    groq_model = f"groq/{os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')}"

    # --- Agents ---

    scout = Agent(
        role="Scout",
        goal="Scrape AI/ML hiring and funding posts from X.com, LinkedIn, and news sites (last 24h only).",
        backstory=(
            "You are a data collection specialist. You know how to navigate social media "
            "and news sites to find the freshest AI/ML hiring announcements and funding news."
        ),
        verbose=True,
        llm=groq_model,
    )

    analyst = Agent(
        role="Analyst",
        goal="Classify scraped posts, extract structured data, and deduplicate before storing in Notion.",
        backstory=(
            "You are an analytical expert who can quickly determine if a post is about hiring, "
            "funding, or both. You extract company names, roles, and funding details with precision."
        ),
        verbose=True,
        llm=groq_model,
    )

    researcher = Agent(
        role="Researcher",
        goal="Find the right contacts (HR, recruiters, managers) at each company and verify their emails.",
        backstory=(
            "You are a resourceful researcher who can find anyone's professional contact info. "
            "You use LinkedIn to identify the right people and email pattern guessing to find their addresses."
        ),
        verbose=True,
        llm=groq_model,
    )

    writer = Agent(
        role="Writer",
        goal="Draft compelling, personalized cold emails for each contact based on the post context.",
        backstory=(
            "You are a cold email copywriter. You craft short, human-sounding emails that "
            "reference specific company news (hiring/funding) to maximize response rates."
        ),
        verbose=True,
        llm=groq_model,
    )

    sender = Agent(
        role="Sender",
        goal="Send drafted emails via Gmail with proper rate limiting and tracking.",
        backstory=(
            "You are a delivery specialist who ensures emails reach their destination safely. "
            "You respect rate limits, track bounces, and update the database accordingly."
        ),
        verbose=True,
        llm=groq_model,
    )

    # --- Tasks (sequential chain) ---

    scout_task = create_scout_task(scout)
    analyst_task = create_analyst_task(analyst, scout_task)
    researcher_task = create_researcher_task(researcher, analyst_task)
    writer_task = create_writer_task(writer, researcher_task)
    sender_task = create_sender_task(sender, writer_task)

    # --- Crew ---

    crew = Crew(
        agents=[scout, analyst, researcher, writer, sender],
        tasks=[scout_task, analyst_task, researcher_task, writer_task, sender_task],
        process=Process.sequential,
        verbose=True,
    )

    return crew


def run_pipeline() -> str:
    """Build and execute the full pipeline. Returns final output."""
    logger.info("=" * 70)
    logger.info("COLD OUTREACH PIPELINE - STARTING")
    logger.info("=" * 70)

    crew = build_crew()
    result = crew.kickoff()

    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)

    return str(result)
