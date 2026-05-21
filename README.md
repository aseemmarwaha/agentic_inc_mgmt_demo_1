# Gen AI Incident Management Assistant

Prototype incident assistant for Dynamics 365 CRM support teams. It uses FastAPI, a lightweight `chat.html`, persistent SQLite storage, local JSON incident ingestion, hybrid retrieval, cited answers, and user-confirmed mock ticket updates.

## What It Does

- Lets a user describe a Dynamics 365 CRM incident in chat.
- Searches local JSON incident/resolution records first.
- Uses SQLite for persistent storage, keyword search, and stored embeddings.
- Returns likely resolution steps with confidence and cited source snippets.
- Supports multi-turn chat sessions.
- Shows index readiness and disables chat until local knowledge has been indexed.
- Provides high-priority issue bubbles for common triage starts such as login failure, access issues, sync failures, missing fields, slow views, unexpected save errors, timeline failures, and duplicates.
- Provides a multi-select Dynamics 365/Dataverse table picker for standard tables such as Account, Contact, Opportunity, Case, Order, and Invoice.
- Creates mock ServiceNow-style ticket update drafts after user confirmation.
- Runs locally through Docker Compose or directly with Python.

## Prerequisites

- Docker Desktop
- Git
- Optional for local Python development: Python 3.12 and `uv`
- Optional for OpenAI-backed generation: an `OPENAI_API_KEY`

The prototype also works without an OpenAI key by using deterministic local embeddings and local answer generation. That mode is useful for demos and tests.

## Quick Start With Docker

From the project root:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8000
```

Click **Rebuild index**, then ask:

```text
Credit Limit field disappeared from the Account Main Form after the last deployment
```

You can also click one of the **Common high-priority issues** bubbles at the top of the chat to start a guided triage flow.

To stop the app:

```bash
docker compose down
```

## Enable OpenAI

The app runs offline by default. To enable OpenAI-backed answer generation and Realtime voice mode, create a `.env` file in the project root. You can start from the included template:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_REALTIME_MODEL=gpt-realtime
OPENAI_REALTIME_VOICE=marin
USE_OPENAI_EMBEDDINGS=false
ENABLE_EXTERNAL_SEARCH=true
```

Then restart:

```bash
docker compose up --build
```

`USE_OPENAI_EMBEDDINGS=false` keeps ingestion cheap and deterministic for the prototype. Set it to `true` later if you want OpenAI embeddings during ingestion.

The browser never receives your real `OPENAI_API_KEY`. For voice mode, FastAPI creates a short-lived OpenAI Realtime client secret and the browser uses that token to establish a WebRTC connection.

## Realtime Voice Mode

After adding a real `OPENAI_API_KEY` to `.env` and restarting the app:

1. Open `http://localhost:8000`.
2. Click **Start voice**.
3. Approve microphone access in the browser.
4. Speak naturally with the Realtime assistant.
5. Click **Stop voice** when done.

The normal text chat remains the trusted RAG flow for cited incident resolutions. Voice mode is intended for a more natural triage conversation.

## Add Incident Knowledge

Put local incident JSON files here:

```text
data/incidents/
```

Then click **Rebuild index** in the UI, or call:

```bash
curl -X POST http://localhost:8000/api/ingest
```

The app stores runtime data in:

```text
data/assistant.db
```

That database is intentionally ignored by Git. Docker Compose mounts `./data` into the container as `/app/data`, so the SQLite datastore persists across container rebuilds.

If you add or edit files under `data/incidents/`, you do not need to restart the app. Click **Rebuild index** in the UI to refresh the local search index.

## Local Development

```bash
uv sync --group dev
uv run uvicorn main:app --reload
```

Run tests:

```bash
uv run pytest
```

The automated suite covers parsing, ingestion, retrieval, API behavior, triage follow-up behavior, and UI smoke checks.

## Main Project Structure

```text
app/
  main.py                 FastAPI routes
  static/chat.html        Lightweight chat UI
  services/               Ingestion, retrieval, database, assistant logic
data/
  incidents/              Local JSON incident knowledge
docs/
  project_plan.md         Architecture and project goals
tests/                    Automated test suite
Dockerfile
docker-compose.yml
```

## Main Endpoints

- `GET /`
- `GET /api/health`
- `GET /api/index/status`
- `GET /api/reference/entities`
- `POST /api/ingest`
- `POST /api/realtime/client-secret`
- `POST /api/chat`
- `GET /api/sessions/{session_id}`
- `POST /api/ticket-drafts/{action_id}/confirm`

## Git Safety Notes

The repository is configured to commit source code, tests, docs, Docker files, `.env.example`, and sample incident JSON files.

The following local/runtime files are intentionally ignored:

- `.env` and `.env.*`
- `data/assistant.db` and SQLite sidecar files
- Python caches and test caches
- local virtual environments
- editor and OS noise

## Troubleshooting

If `docker` is not found on macOS after installing Docker Desktop, add Docker Desktop's CLI to your shell path:

```zsh
echo 'export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"' >> ~/.zshrc
mkdir -p ~/.docker/cli-plugins
ln -sf /Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose ~/.docker/cli-plugins/docker-compose
source ~/.zshrc
```

Verify:

```bash
docker --version
docker compose version
```

If port `8000` is already in use, stop the other process or change the port mapping in `docker-compose.yml`.

See [docs/project_plan.md](docs/project_plan.md) for the implementation plan and goals.
