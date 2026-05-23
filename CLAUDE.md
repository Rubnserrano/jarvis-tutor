# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # required by notebooklm-py for browser automation

# One-time Google auth (opens browser)
notebooklm auth

# Create .env with Gemini API key (required for study/tutor commands)
cp .env.example .env
```

## Running the CLI

```bash
python cli.py --help
python cli.py add "texto de nota"
python cli.py add --file notes.md --tag dbt
python cli.py search "cadenas de Markov"
python cli.py ask "¿Qué es una distribución estacionaria?"
python cli.py list
python cli.py notebook create "mi_notebook"
python cli.py use "mi_notebook"
python cli.py status
python cli.py study --text                          # text mode (no mic)
python cli.py study --context PE_tutor.md           # with voice
```

## Architecture

The project has two distinct subsystems:

**1. NotebookLM subsystem** (`notebook.py`, `ingest.py`, `query.py`)
All note storage, search, and Q&A is delegated entirely to Google NotebookLM via the `notebooklm-py` library, which uses Playwright to automate a real browser session. `get_notebook()` is an async context manager that resolves the active notebook and yields `(client, notebook)`. Every operation in `ingest.py` and `query.py` wraps `get_notebook()`. There is no local vector store or embedding — RAG is handled 100% by NotebookLM.

**2. Tutor subsystem** (`tutor.py`, `voice.py`, `screen.py`, `memory.py`)
`TutorSession` powers the `study` command: it uses Gemini (`gemini-2.0-flash`) directly via `google-genai` to run a Socratic tutoring loop. On each turn it fetches relevant context from NotebookLM (`search_notes`), optionally captures a screenshot (`screen.py` via `mss`), and sends a multi-part message to Gemini. Voice I/O uses Google Speech Recognition (STT) and `pyttsx3` (TTS). Session history is maintained in `self.history` as `types.Content` objects and passed on every call.

**Persistent state** is stored outside the repo:
- `~/.jarvis/config.json` — active notebook name (managed by `settings.py`)
- `~/.jarvis/memory/<notebook_slug>.json` — session count, topics covered, weak areas (managed by `memory.py`)
- `~/.notebooklm/storage_state.json` — Playwright browser session (managed by `notebooklm auth`)

**Tutor context files** live in `context/` and are Markdown templates with a `{memory_summary}` placeholder that gets injected at session start. Add new tutors there and pass the filename with `--context`.

## Key constraints

- All NotebookLM operations are `async`; `cli.py` wraps them with `asyncio.run()`. Do not mix `asyncio.run()` calls inside async functions.
- `ingest.py` only accepts `.txt` and `.md` files.
- `GEMINI_API_KEY` must be set in `.env` for the `study` command; the other commands (add/search/ask/list) do not require it.
- Screenshot capture requires a working `DISPLAY` (WSLg on WSL2).
- Voice requires a microphone and an internet connection (Google STT). Use `--text` flag to bypass both.
