# Gen AI Incident Management Assistant Prototype Plan

## Summary
Build a lightweight, Docker Compose-run prototype for a Dynamics 365 CRM incident assistant. Users describe an issue in a simple chat UI; the FastAPI backend searches persistent local knowledge, proposes likely resolutions, shows cited sources, supports multi-turn troubleshooting, and creates user-confirmed mock ticket updates.

## Project Goals
- Help users resolve Dynamics 365 CRM incidents faster by matching natural-language problem descriptions to historical incidents, resolutions, and knowledge articles.
- Use internal local/offline knowledge first, especially exported ServiceNow-style JSON incidents and known CRM fixes.
- Provide trustworthy answers with cited evidence: incident IDs, resolution snippets, knowledge article references, and external links when used.
- Support multi-turn troubleshooting so the assistant can ask follow-up questions when environment, entity, deployment, or symptom details are missing.
- Return actionable resolution steps, likely root cause, validation checks, and confidence level.
- Persist indexed knowledge, chat sessions, retrieved evidence, and confirmed mock ticket updates in SQLite.
- Enable a safe ticket update workflow where the assistant drafts a ServiceNow-style update, but stores it only after explicit user confirmation.
- Stay lightweight: Python, FastAPI, simple `chat.html`, SQLite with search/vector indexing, and Docker Compose.
- Allow external research when local knowledge is insufficient, prioritizing Microsoft/Dynamics documentation before broader public web results.
- Keep the architecture ready for future ServiceNow API, Dynamics/Dataverse API, Microsoft Entra ID, and production deployment.
- Ensure adequate automated and manual testing so the prototype is demo-ready, reliable, and safe to extend.

## Architecture
Use one Dockerized FastAPI application that serves both backend APIs and the lightweight frontend.

```text
Browser
  -> FastAPI container
      -> static chat.html
      -> chat/session APIs
      -> RAG orchestration
      -> OpenAI API
      -> SQLite datastore
          -> incidents
          -> chunks
          -> vector index
          -> FTS index
          -> sessions
          -> citations
          -> mock ticket updates
      -> local JSON knowledge folder
```

SQLite is persistent through a Docker Compose volume:

```text
./data -> /app/data
```

The Docker image contains code and dependencies only. Runtime data, incident JSON files, and `assistant.db` stay outside the image.

## Key Implementation Choices
- Use FastAPI as the middleware/backend and serve `chat.html` from the same app.
- Use OpenAI API for generation and embeddings when configured.
- Use deterministic local embeddings and local answer generation for offline tests and demos without an API key.
- Use SQLite as the single persistent datastore.
- Use SQLite FTS5 for keyword search.
- Store embeddings in SQLite and score semantic matches locally; load `sqlite-vec` when available so the vector layer can move to native SQLite vector search without changing the API.
- Store local incident JSON files under `data/incidents/`.
- Store generated SQLite database at `data/assistant.db`.
- Use Docker Compose for repeatable local startup.
- Use mock writeback for ticket create/update in v1, with user confirmation required.
- Do not implement real ServiceNow or Dynamics writes in the first prototype.

## Core User Flow
1. User opens `http://localhost:8000/`.
2. User describes a Dynamics 365 CRM issue in chat.
3. Backend stores the message in the session.
4. Retrieval searches local SQLite vector and FTS indexes.
5. If local evidence is weak or the user asks for current guidance, backend allows external search through the OpenAI-backed flow.
6. Assistant responds with likely resolution, reasoning summary, confidence level, cited sources, follow-up questions if needed, and an optional draft ticket update.
7. User confirms or rejects the proposed mock ticket update.
8. Confirmed update is persisted locally in SQLite.

## Public Interfaces
- `GET /`: serves the lightweight chat UI.
- `GET /api/health`: returns runtime, persistence, OpenAI, and vector-extension status.
- `POST /api/chat`: accepts a user message and returns assistant answer, confidence, sources, follow-up questions, and proposed actions.
- `GET /api/sessions/{session_id}`: restores prior chat state.
- `POST /api/ticket-drafts/{action_id}/confirm`: confirms or rejects a proposed mock ticket update.
- `POST /api/ingest`: rebuilds or updates the local SQLite search indexes from `data/incidents/`.

## Response Requirements
Every assistant answer should include:
- Proposed resolution steps.
- Likely root cause when available.
- Confidence: `high`, `medium`, or `low`.
- Internal sources with incident ID, title, section, snippet, and similarity score.
- External sources with title, URL, provider, and snippet when external search is used.
- A clear note when no strong local match is found.
- A draft ticket update only when enough context exists.

## Testing Strategy
Testing is a first-class deliverable. Add tests at unit, integration, API, retrieval-quality, and UI smoke levels.

- Unit tests cover incident parsing, chunk creation, confidence mapping, and prompt/context behavior.
- Datastore tests cover schema initialization, ingestion idempotency, FTS exact matching, vector-extension health, and persistent database behavior.
- Retrieval tests cover known issue matching, hybrid ranking, low-confidence handling, and source metadata preservation.
- API tests cover session creation/reuse, multi-turn persistence, response shape, draft confirmation, and error handling.
- LLM behavior tests use mocked/local generation by default and avoid live OpenAI calls in automated tests.
- UI smoke tests verify `chat.html` loads, sends messages, displays sources, and confirms draft updates.
- Manual acceptance verifies Docker Compose startup, ingestion, cited answer for `INC0010245`, follow-up questions for incomplete issues, and persisted mock ticket updates.

## Assumptions
- The first prototype runs locally with no login.
- The first prototype uses OpenAI API when configured, not Azure OpenAI.
- The first prototype uses local JSON files as the knowledge source.
- External search is allowed, but local/internal knowledge is prioritized.
- The first prototype uses mock writeback only.
- Automated tests should run without making live OpenAI calls by default.
- Live OpenAI and external-search tests should be optional/manual or marked separately.
- The final production version may later add ServiceNow API, Dynamics/Dataverse API, enterprise authentication, audit logging, and role-based permissions.
