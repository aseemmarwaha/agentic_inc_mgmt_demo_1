from typing import Any, Literal
from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]


class ChatContext(BaseModel):
    application: str | None = None
    environment: str | None = None
    entity: str | None = None
    entities: list[str] = Field(default_factory=list)
    ticket_id: str | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1)
    context: ChatContext = Field(default_factory=ChatContext)
    allow_external_search: bool = True


class Source(BaseModel):
    type: str
    id: str
    title: str
    section: str | None = None
    snippet: str
    score: float | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposedAction(BaseModel):
    action_id: str
    type: str = "mock_ticket_update"
    summary: str
    draft_note: str
    status: Literal["pending", "approved", "rejected"] = "pending"


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    confidence: Confidence
    sources: list[Source]
    follow_up_questions: list[str] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    diagnostic_note: str | None = None


class ConfirmDraftRequest(BaseModel):
    approved: bool
    target_ticket_id: str
    user_note: str | None = None


class ConfirmDraftResponse(BaseModel):
    action_id: str
    status: Literal["approved", "rejected"]
    stored_update_id: int | None = None


class IngestResponse(BaseModel):
    incidents_indexed: int
    chunks_indexed: int
    vector_extension_available: bool


class IndexStatusResponse(BaseModel):
    indexed: bool
    incidents_indexed: int
    chunks_indexed: int
    vector_extension_available: bool
    message: str


class SessionResponse(BaseModel):
    session_id: str
    messages: list[dict[str, Any]]


class RealtimeClientSecretResponse(BaseModel):
    client_secret: str
    expires_at: int | None = None
    model: str
    voice: str


class EntityReference(BaseModel):
    label: str
    logical_name: str
    area: str
    description: str
