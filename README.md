# ExecFlow

ExecFlow is a lightweight personal execution assistant that consolidates notes from meetings,
email threads, calendar events, and voice notes into a structured operational summary.

## Project structure

- `app.py` - application entry point
- `agent.py` - main execution agent logic
- `database.py` - simple storage layer
- `rules.py` - transformation and normalization rules
- `prompts.py` - system prompt definitions
- `data/` - source files for input data
- `docs/architecture.md` - architecture overview

## Getting started

1. Create a virtual environment.
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the program:
   ```bash
   python app.py
   ```

## Notes

This project is intentionally simple and designed as a clean starting point for more advanced agent workflows.
