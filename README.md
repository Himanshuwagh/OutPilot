# AI Cold Outreach Pipeline

Automated pipeline that scrapes AI/ML hiring and funding posts from X.com, LinkedIn, and news sites, finds relevant contacts, drafts personalized cold emails, and sends them -- all on autopilot.

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure credentials**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

3. **Set up Notion**:
   - Create an integration at https://www.notion.so/my-integrations
   - Create a page and connect the integration to it
   - The pipeline will auto-create the databases on first run

4. **First run (manual)**:
   ```bash
   python main.py --run-now
   ```
   - Browser windows will open for LinkedIn and X.com login on first run
   - Log in manually; sessions are saved for future runs

### Headless / no browser popup mode

The pipeline now runs headless by default (`scraping.headless: true`), so no browser window opens during normal runs.

For authenticated X/LinkedIn scraping in headless mode, seed sessions once:

```bash
python setup_sessions.py --platform both
```

After that, all runs stay headless:

```bash
python demo.py
python main.py --run-now
```

### Find email from a LinkedIn profile URL

If LinkedIn People search is blocked/unstable for your account, use direct profile lookup:

```bash
python find_email_from_linkedin_profile.py --linkedin-url "https://www.linkedin.com/in/USERNAME/"
```

Recommended for best accuracy:

```bash
python find_email_from_linkedin_profile.py \
  --linkedin-url "https://www.linkedin.com/in/USERNAME/" \
  --company "OpenAI" \
  --domain "openai.com"
```

If LinkedIn shows security verification, run with visible browser:

```bash
python find_email_from_linkedin_profile.py --linkedin-url "..." --headful
```

5. **Install as daily service (runs at 6 AM)**:
   ```bash
   bash install_service.sh
   ```

## Architecture

- **Scrapers**: Playwright (X.com, LinkedIn), BeautifulSoup (TechCrunch, Google News)
- **Processing**: Rule-based classifier + regex extractor + two-layer dedup
- **Research**: LinkedIn people search + email pattern guessing + SMTP verification
- **Outreach**: Groq LLM drafting + Gmail SMTP sending
- **Storage**: Notion databases (Leads, Contacts, Outreach)
- **Orchestration**: CrewAI agents + macOS launchd scheduling

## Run frontend locally

The marketing site (ColdApply landing page) runs separately from the Python pipeline.

**Why you see `Can't resolve 'tailwindcss'`:** The bundler resolves modules from the current working directory. If you run `npm run dev` from the **project root** (`custom-cold-applying/`) instead of from `frontend/`, it looks for `tailwindcss` in the root and fails. Fix: run from `frontend/` or use the root scripts below.

### Option A — From project root (recommended if your IDE opens the whole repo)

From `custom-cold-applying/`:

1. **Install frontend dependencies** (first time only):
   ```bash
   npm run frontend:install
   ```

2. **Start the dev server**:
   ```bash
   npm run frontend
   ```

3. Open **http://localhost:3000** in your browser.

### Option B — From the frontend folder

```bash
cd frontend
npm install          # first time only
npm run dev
```

Then open **http://localhost:3000**.

**Other commands** (from inside `frontend/`): `npm run build`, `npm run start`

## Cost

$0. Everything uses free tiers or open-source tools.
