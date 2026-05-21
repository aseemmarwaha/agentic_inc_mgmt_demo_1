from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
import httpx
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.models import (
    ChatRequest,
    ChatResponse,
    ConfirmDraftRequest,
    ConfirmDraftResponse,
    EntityReference,
    IndexStatusResponse,
    IngestResponse,
    RealtimeClientSecretResponse,
    SessionResponse,
)
from app.reference_data import STANDARD_DYNAMICS_ENTITIES
from app.services.assistant import AssistantService
from app.services.db import connect, init_db
from app.services.embeddings import HashEmbeddingProvider, OpenAIEmbeddingProvider
from app.services.ingestion import ingest_incidents
from app.services.retrieval import Retriever


app = FastAPI(title="Gen AI Incident Management Assistant")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def get_connection(settings: Settings = Depends(get_settings)) -> sqlite3.Connection:
    connection = connect(settings.resolved_database_path)
    init_db(connection)
    try:
        yield connection
    finally:
        connection.close()


def get_embedding_provider(settings: Settings = Depends(get_settings)):
    if settings.openai_api_key and settings.use_openai_embeddings:
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return HashEmbeddingProvider(dimensions=settings.embedding_dimensions)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "chat.html")


@app.get("/api/health")
def health(
    settings: Settings = Depends(get_settings),
    connection: sqlite3.Connection = Depends(get_connection),
) -> dict[str, object]:
    vector_available = init_db(connection)
    return {
        "status": "ok",
        "database_path": str(settings.resolved_database_path),
        "incidents_dir": str(settings.resolved_incidents_dir),
        "vector_extension_available": vector_available,
        "openai_configured": bool(settings.openai_api_key),
    }


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(
    settings: Settings = Depends(get_settings),
    connection: sqlite3.Connection = Depends(get_connection),
    embedding_provider=Depends(get_embedding_provider),
) -> IngestResponse:
    return ingest_incidents(connection, settings.resolved_incidents_dir, embedding_provider)


@app.get("/api/index/status", response_model=IndexStatusResponse)
def index_status(connection: sqlite3.Connection = Depends(get_connection)) -> IndexStatusResponse:
    vector_available = init_db(connection)
    incident_count = connection.execute("SELECT COUNT(*) AS count FROM incidents").fetchone()["count"]
    chunk_count = connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()["count"]
    indexed = chunk_count > 0
    if indexed:
        message = f"Index ready: {incident_count} incidents, {chunk_count} chunks."
    else:
        message = "Index not built yet. Rebuild the index before starting chat."
    return IndexStatusResponse(
        indexed=indexed,
        incidents_indexed=incident_count,
        chunks_indexed=chunk_count,
        vector_extension_available=vector_available,
        message=message,
    )


@app.get("/api/reference/entities", response_model=list[EntityReference])
def reference_entities() -> list[EntityReference]:
    return STANDARD_DYNAMICS_ENTITIES


@app.post("/api/realtime/client-secret", response_model=RealtimeClientSecretResponse)
def create_realtime_client_secret(settings: Settings = Depends(get_settings)) -> RealtimeClientSecretResponse:
    if not settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY is not configured. Add your key to .env and restart the app.",
        )

    payload = {
        "expires_after": {"anchor": "created_at", "seconds": 600},
        "session": {
            "type": "realtime",
            "model": settings.realtime_model,
            "audio": {
                "output": {
                    "voice": settings.realtime_voice,
                }
            },
            "instructions": (
                "You are a Dynamics 365 CRM incident management assistant. Help the user triage "
                "incidents conversationally. Ask clarifying questions before recommending access, "
                "security role, ownership, sharing, or deployment changes. For concrete resolutions, "
                "prefer the regular incident assistant chat API because it has local RAG sources."
            ),
        },
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime client secret request failed: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI Realtime request failed: {exc}") from exc

    data = response.json()
    secret = data.get("value") or data.get("client_secret", {}).get("value")
    expires_at = data.get("expires_at") or data.get("client_secret", {}).get("expires_at")
    if not secret:
        raise HTTPException(status_code=502, detail="OpenAI Realtime response did not include a client secret.")

    return RealtimeClientSecretResponse(
        client_secret=secret,
        expires_at=expires_at,
        model=settings.realtime_model,
        voice=settings.realtime_voice,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
    connection: sqlite3.Connection = Depends(get_connection),
    embedding_provider=Depends(get_embedding_provider),
) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    ensure_session(connection, session_id)
    store_message(connection, session_id, "user", request.message, request.context.model_dump())

    if is_rebuild_index_request(request.message):
        ingest_result = ingest_incidents(connection, settings.resolved_incidents_dir, embedding_provider)
        answer = (
            "I rebuilt the local incident index. "
            f"Indexed {ingest_result.incidents_indexed} incidents and {ingest_result.chunks_indexed} chunks."
        )
        response = ChatResponse(
            session_id=session_id,
            answer=answer,
            confidence="high",
            sources=[],
            follow_up_questions=[],
            proposed_actions=[],
        )
        store_message(
            connection,
            session_id,
            "assistant",
            response.answer,
            {
                "operation": "rebuild_index",
                "ingest": ingest_result.model_dump(),
            },
        )
        return response

    retriever = Retriever(connection, embedding_provider)
    results = retriever.search(build_retrieval_query(request))
    conversation_text = get_session_transcript(connection, session_id)
    assistant = AssistantService(
        connection=connection,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        enable_external_search=settings.enable_external_search,
    )
    response = assistant.answer(
        session_id=session_id,
        message=request.message,
        context=request.context,
        results=results,
        allow_external_search=request.allow_external_search,
        conversation_text=conversation_text,
    )
    store_message(
        connection,
        session_id,
        "assistant",
        response.answer,
        {
            "confidence": response.confidence,
            "sources": [source.model_dump() for source in response.sources],
            "proposed_actions": [action.model_dump() for action in response.proposed_actions],
            "diagnostic_note": response.diagnostic_note,
        },
    )
    return response


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, connection: sqlite3.Connection = Depends(get_connection)) -> SessionResponse:
    session = connection.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = connection.execute(
        """
        SELECT role, content, metadata_json, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY id
        """,
        (session_id,),
    ).fetchall()
    messages = [
        {
            "role": row["role"],
            "content": row["content"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return SessionResponse(session_id=session_id, messages=messages)


@app.post("/api/ticket-drafts/{action_id}/confirm", response_model=ConfirmDraftResponse)
def confirm_draft(
    action_id: str,
    request: ConfirmDraftRequest,
    connection: sqlite3.Connection = Depends(get_connection),
) -> ConfirmDraftResponse:
    row = connection.execute("SELECT * FROM draft_actions WHERE action_id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Draft action not found")
    status = "approved" if request.approved else "rejected"
    connection.execute(
        "UPDATE draft_actions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE action_id = ?",
        (status, action_id),
    )
    stored_update_id = None
    if request.approved:
        note = row["draft_note"]
        if request.user_note:
            note = f"{note}\n\nUser note:\n{request.user_note}"
        cursor = connection.execute(
            """
            INSERT INTO ticket_updates(action_id, target_ticket_id, update_note, sources_json)
            VALUES (?, ?, ?, ?)
            """,
            (action_id, request.target_ticket_id, note, row["sources_json"]),
        )
        stored_update_id = cursor.lastrowid
    connection.commit()
    return ConfirmDraftResponse(action_id=action_id, status=status, stored_update_id=stored_update_id)


def ensure_session(connection: sqlite3.Connection, session_id: str) -> None:
    connection.execute(
        """
        INSERT INTO sessions(session_id, created_at, updated_at)
        VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
        (session_id,),
    )
    connection.commit()


def store_message(
    connection: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    metadata: dict,
) -> None:
    connection.execute(
        """
        INSERT INTO messages(session_id, role, content, metadata_json)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, role, content, json.dumps(metadata)),
    )
    connection.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?", (session_id,))
    connection.commit()


def get_session_transcript(connection: sqlite3.Connection, session_id: str) -> str:
    rows = connection.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = ?
        ORDER BY id
        """,
        (session_id,),
    ).fetchall()
    return "\n".join(f"{row['role']}: {row['content']}" for row in rows)


def is_rebuild_index_request(message: str) -> bool:
    normalized = " ".join(message.lower().replace("?", " ").split())
    index_terms = ("index", "indexes", "indices", "knowledge base", "kb")
    rebuild_terms = ("rebuild", "reindex", "refresh", "update", "ingest", "reload")
    return any(term in normalized for term in index_terms) and any(term in normalized for term in rebuild_terms)


def build_retrieval_query(request: ChatRequest) -> str:
    context_terms = [request.context.entity or "", *request.context.entities]
    unique_terms = []
    for term in context_terms:
        normalized = term.strip()
        if normalized and normalized not in unique_terms:
            unique_terms.append(normalized)
    if not unique_terms:
        return request.message
    return f"{request.message} {' '.join(unique_terms)}"
