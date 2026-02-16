"""
Prompt templates for cold email drafting, one per post type.
"""

SYSTEM_PROMPT = (
    "You are a cold email expert. Write concise, human-sounding cold emails. "
    "No fluff, no filler, no generic phrases like 'I hope this finds you well'. "
    "Each email should be 4-5 sentences, under 100 words. "
    "Sound like a real person, not a template."
)

FUNDING_TEMPLATE = """Write a cold email to {contact_name} ({contact_title}) at {company}.

Context: {company} just {funding_details}. The sender is {your_name}, an {your_role} with skills in {your_skills}.

Requirements:
- Open with the funding news as the hook (show you're paying attention)
- Express genuine interest in what they're building in AI
- Briefly mention 1-2 relevant skills from the sender's background
- End with a soft ask (chat, not "give me a job")
- Under 100 words, 4-5 sentences
- Subject line included on the first line as "Subject: ..."

Sender links:
- Resume: {resume_link}
- LinkedIn: {linkedin_url}
- GitHub: {github_url}
- Portfolio: {portfolio_url}"""

HIRING_TEMPLATE = """Write a cold email to {contact_name} ({contact_title}) at {company}.

Context: {company} posted about hiring for {role}. The sender is {your_name}, an {your_role} with skills in {your_skills}.

Requirements:
- Reference the specific role they posted about
- Show you understand what they're building (mention their tech/domain)
- Mention 1-2 directly relevant experiences or skills
- End by asking for a brief conversation
- Under 100 words, 4-5 sentences
- Subject line included on the first line as "Subject: ..."

Sender links:
- Resume: {resume_link}
- LinkedIn: {linkedin_url}
- GitHub: {github_url}
- Portfolio: {portfolio_url}"""

BOTH_TEMPLATE = """Write a cold email to {contact_name} ({contact_title}) at {company}.

Context: {company} just {funding_details} AND is hiring for {role}. The sender is {your_name}, an {your_role} with skills in {your_skills}.

Requirements:
- Congratulate on the funding (brief, not sycophantic)
- Express interest in the open role
- Mention 1-2 relevant skills that map to the role
- End with a call to action
- Under 100 words, 4-5 sentences
- Subject line included on the first line as "Subject: ..."

Sender links:
- Resume: {resume_link}
- LinkedIn: {linkedin_url}
- GitHub: {github_url}
- Portfolio: {portfolio_url}"""


def get_template(post_type: str) -> str:
    """Return the appropriate template for the post type."""
    mapping = {
        "funding": FUNDING_TEMPLATE,
        "hiring": HIRING_TEMPLATE,
        "both": BOTH_TEMPLATE,
    }
    return mapping.get(post_type, HIRING_TEMPLATE)
