# ExecFlow

ExecFlow is a lightweight, deterministic personal execution assistant designed to ingest free-form inputs
such as meeting notes, emails, calendar events, and voice notes and produce a constrained, auditable set of
structured commitments (Commitment text, Owner, Deadline, Evidence).

This repository contains a Streamlit application that demonstrates a safe, rule-driven extraction pipeline
that minimizes hallucination and produces repeatable results suitable for programmatic workflows or manual review.

## Key Features

- Deterministic extraction of commitments with explicit evidence tracking.
- Anti-hallucination rules: "Never invent an owner" and "Never invent a deadline".
- Reconciliation and deterministic deduplication to merge overlapping commitments.
- Audit trail persisted in SQLite and surfaced in the UI.
- Headless test harness with representative scenarios (6/6 passing in this workspace).

## Repository layout

- `app.py` — Streamlit UI and orchestrator (do not modify application logic unless intentionally changing behavior)
- `agent.py` — extraction logic and heuristics
- `database.py` — SQLite persistence and audit helpers
- `models.py` — Pydantic models for typed commitments and records
- `reconciliation.py` — deterministic deduplication & merge rules
- `rules.py` — business rules for deadlines, ownership, and status
- `prompts.py` — prompt templates and system prompt text (for optional LLM use)
- `data/` — example input files used by the test harness and local demo
- `tests/` — headless tests and debug helpers
- `docs/` — architecture and diagrams

## Detailed Architecture (high level)

ExecFlow is organized as an agentic pipeline with the following stages:

1. INGEST — Load text inputs from `data/` or user-supplied content.
2. UNDERSTAND — Lightweight NLU and heuristics normalize text for extraction.
3. EXTRACT — Deterministic extraction of candidate commitments (text + evidence spans).
4. RECONCILE — Merge duplicates and reconcile overlapping commitments deterministically.
5. VALIDATE — Enforce anti-hallucination rules (do not invent owners or deadlines).
6. STORE — Persist validated records to a local SQLite database with audit logs.
7. MONITOR / BRIEF / ANSWER — Streamlit UI surfaces daily briefs, an action center, and a Q&A interface.

Design principles: determinism, traceability (evidence preserved), minimal LLM reliance, and testability.

## Installation (Windows / Git Bash)

1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Or with Git Bash / bash:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` in the project root for optional secrets (do NOT commit it):

```
OPENAI_API_KEY=your_api_key_here
```

The application works without an OpenAI key — the LLM is optional and guarded.

## Running the application

To run the Streamlit UI locally on the default port (8506 in this workspace) use:

```bash
.venv\Scripts\Activate.ps1   # or `source .venv/bin/activate` on bash
streamlit run app.py --server.port 8506
```

Open http://localhost:8506 in your browser.

## Running tests (headless)

This repo includes a headless test runner that validates the deterministic behavior used by the app.

```bash
# If pytest is installed:
python -m pytest -q

# Or run the included harness (works without pytest):
python tests/run_tests.py
```

All tests should pass after repository housekeeping (this workspace: 6/6 passed).

## Development notes and safety

- Do not change business logic arbitrarily. The app enforces strict extraction rules.
- The agent is intentionally conservative about assigning owners and deadlines — changing those rules affects determinism.
- The SQLite file (`execflow.db`) is ignored by `.gitignore`; if you need to reset local data, stop the app and remove the DB.

## Commit message conventions

This project uses conventional-style commit prefixes for clarity. Examples:

- `feat:` new functionality
- `fix:` bug fixes
- `test:` tests and CI
- `docs:` documentation
- `refactor:` non-functional code changes
- `chore:` repository maintenance

The repository cleanup was committed as `chore: clean repository and ignore generated files`.

## How you can contribute

1. Create an issue describing the change or improvement.
2. Branch from `ci/add-tests` or `main` depending on guidelines.
3. Run tests locally and keep changes focused and minimal.

## Troubleshooting

- If Streamlit fails due to a reserved option, upgrade/downgrade Streamlit or remove unsupported `st.set_option` calls (these are guarded in the codebase).
- If port 8506 is in use, either kill the conflicting process or run the app on a different port: `streamlit run app.py --server.port 8507`.

## License

This repository does not include a license file by default. Add a `LICENSE` file if you want to set licensing terms.

## Contact / Maintainer

Repo owner: SpottedJaiveerSingh (GitHub: https://github.com/SpottedJaiveerSingh)

---

