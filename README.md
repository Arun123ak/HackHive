# Portfolio Sentinel — Hackathon Starter

A working Streamlit + LangGraph prototype for evidence-based monitoring of **fictional** portfolio holdings.

## What it demonstrates

- **Planning:** a planner node creates a six-step monitoring plan.
- **Tool use:** LangGraph nodes call SQLite-backed portfolio, news, and filing-retrieval tools.
- **Action:** an alert-write tool saves findings into SQLite.
- **Conditional workflow:** evidence verification can route to a second retrieval attempt.
- **Evidence:** each alert includes a mock source excerpt and source reference.
- **Dashboard:** Streamlit pages show overview, holdings, alerts/evidence, and agent execution trace.
- **Optional LLM:** if `OPENAI_API_KEY` is configured, the analysis step uses the OpenAI API. Without a key, the app runs with a deterministic local classifier.

## Important data-compliance note

The bundled CSV files contain **synthetic mock data** created for this demo. No real customer portfolios or actual financial events are included.

The uploaded research archives that may be used during development have different characteristics:
- SNES-style archive: historical stock prices and aggregated company/news-event counts.
- Financial PhraseBank archive: labelled financial-language sentences; its included license is CC BY-NC-SA 3.0.
- DJIA news archive: historical headlines and market labels.

Those are not included in this project and are not loaded by the app. The hackathon brief says real customer or financial data must not be used. Do not use those historical datasets in the submitted demo unless the organizers explicitly confirm that their use is allowed. Check each dataset's license and provenance before reuse. The `scripts/inspect_uploaded_archives.py` helper only inspects schemas; it does not ingest the data.

## Setup in VS Code (Windows)

1. Install Python 3.11 or 3.12 and VS Code.
2. Open this folder in VS Code.
3. Open Terminal → New Terminal.
4. Create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use:

   ```powershell
   .\.venv\Scripts\activate.bat
   ```

5. Install packages:

   ```powershell
   pip install -r requirements.txt
   ```

6. Optional: copy `.env.example` to `.env` and add your API key. The app works without it.

7. Start the app:

   ```powershell
   streamlit run app.py
   ```

The app opens in your browser. Choose `DEMO-01` or `DEMO-02` and click **Run portfolio health check**.

## Resetting the demo

Use the **Reset demo alerts** button in the sidebar. The database file `portfolio_sentinel.db` is created automatically on first run. Delete that file if you want to recreate the demo database from the bundled CSV files.

## Project structure

```text
Portfolio_Sentinel/
├── app.py
├── requirements.txt
├── .env.example
├── data/
│   ├── portfolio.csv
│   ├── news.csv
│   ├── filings.csv
│   └── event_labels.csv
├── backend/
│   ├── db.py
│   ├── tools.py
│   ├── analysis.py
│   └── agent.py
└── scripts/
    └── inspect_uploaded_archives.py
```

## Agent workflow

`Planner → Portfolio DB Tool → News Search Tool → Filing Retrieval Tool → Analysis → Evidence Verification → (conditional retry if needed) → Alert Write Tool → Final Report`

The database and file retrieval operations are real tool calls made by the agent workflow. The app stores a trace for each run so judges can inspect planning, tool use, and actions.

## How to make the submission stronger

1. Add a test suite for company matching, duplicate suppression, evidence verification, and event classification.
2. Add a PDF upload flow that extracts text and records page-level citations.
3. Add a source-quality field and distinguish primary disclosures from secondary reporting.
4. Evaluate event classification on a separate synthetic labelled test set; report precision, recall, and F1.
5. Keep the UI language cautious: "potentially relevant development", never buy/sell/hold advice.
6. Add screenshots and a short demo video to the submission.
7. Disclose actual AI coding assistants used by the team below.

## AI development tools disclosure

Update this section to accurately list the tools your team actually used (for example, ChatGPT, Cursor, GitHub Copilot, or Claude Code), and briefly state how they were used. Do not claim use of tools that were not used.

## Disclaimer

This is an educational software prototype using invented companies and invented events. It is not financial advice, does not provide trade recommendations, and does not predict investment returns.
