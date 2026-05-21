from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from openai import OpenAI

from app.models import ChatContext, ChatResponse, ProposedAction, Source
from app.services.retrieval import RetrievalResult, calculate_confidence


REQUIRED_CONTEXT_HINTS = {
    "environment": "Which Dynamics environment is affected, for example Production, UAT, or Development?",
    "entity": "Which Dynamics table/entity or form is affected?",
}

ACCESS_VISIBILITY_TERMS = {
    "access",
    "permission",
    "permissions",
    "privilege",
    "privileges",
    "role",
    "roles",
    "security",
    "unable to view",
    "cannot view",
    "can't view",
    "not able to view",
    "unable to see",
    "cannot see",
    "can't see",
    "not visible",
    "missing project",
    "client project",
}

ACCESS_CONTEXT_QUESTIONS = [
    "What Dynamics security role(s) does the affected user have?",
    "Is this affecting one user, a team/business unit, or all users?",
    "Can the same user view other client/project records, or is only one record/client project missing?",
]

LOGIN_AUTH_TERMS = {
    "login",
    "log in",
    "sign in",
    "signin",
    "authentication",
    "mfa",
    "cannot access crm",
    "can't access crm",
    "unable to access crm",
}

LOGIN_AUTH_QUESTIONS = [
    "What exact error message do you see when login fails?",
    "Is this affecting only you, multiple users, or everyone?",
    "Can you access other Microsoft 365 apps with the same account?",
    "Does it fail before MFA, after MFA, or after the CRM page starts loading?",
]


class AssistantService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        openai_api_key: str | None,
        openai_model: str,
        enable_external_search: bool,
    ) -> None:
        self.connection = connection
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.enable_external_search = enable_external_search

    def answer(
        self,
        session_id: str,
        message: str,
        context: ChatContext,
        results: list[RetrievalResult],
        allow_external_search: bool,
        conversation_text: str = "",
    ) -> ChatResponse:
        confidence = calculate_confidence(results)
        follow_ups = self._follow_up_questions(message, context, confidence, conversation_text)
        needs_clarification = bool(follow_ups)
        trusted_results = [] if needs_clarification else select_trusted_results(results, confidence)
        sources = [result.source for result in trusted_results]
        diagnostic_note = None

        if needs_clarification:
            answer_text = self._clarification_answer(message, context, follow_ups)
            diagnostic_note = self._diagnostic_note(message, results, confidence)
        elif self.openai_api_key:
            answer_text = self._openai_answer(
                message,
                context,
                trusted_results,
                confidence,
                allow_external_search,
                follow_ups,
            )
        else:
            answer_text = self._local_answer(
                message,
                context,
                trusted_results,
                confidence,
                allow_external_search,
                follow_ups,
            )

        actions: list[ProposedAction] = []
        if sources and confidence != "low" and not follow_ups:
            action = ProposedAction(
                action_id=str(uuid.uuid4()),
                summary="Draft ServiceNow-style resolution/work note",
                draft_note=self._draft_ticket_note(message, answer_text, confidence, sources),
            )
            self._store_draft_action(session_id, action, sources)
            actions.append(action)

        return ChatResponse(
            session_id=session_id,
            answer=answer_text,
            confidence=confidence,
            sources=sources,
            follow_up_questions=follow_ups,
            proposed_actions=actions,
            diagnostic_note=diagnostic_note,
        )

    def _clarification_answer(
        self,
        message: str,
        context: ChatContext,
        follow_ups: list[str],
    ) -> str:
        if self._is_login_auth_issue(message):
            environment = context.environment or "Production"
            return (
                f"I understand you are unable to log in to the CRM application in {environment}. "
                "Let's narrow down whether this is account, MFA, URL, license, or service availability related.\n\n"
                f"First question: {follow_ups[0]}"
            )

        if self._is_access_visibility_issue(message):
            affected = "Client Project records" if "client project" in message.lower() else "the requested records"
            environment = context.environment or "Production"
            return (
                f"I understand you are unable to view {affected} in {environment}. "
                "Let's narrow this down one step at a time.\n\n"
                f"First question: {follow_ups[0]}"
            )

        return (
            "I understand the issue. I need one more detail before proposing a reliable resolution.\n\n"
            f"First question: {follow_ups[0]}"
        )

    def _diagnostic_note(
        self,
        message: str,
        results: list[RetrievalResult],
        confidence: str,
    ) -> str | None:
        if self._is_access_visibility_issue(message):
            note = (
                "Access issues can come from security role privileges, team membership, business-unit scope, "
                "record ownership, sharing, or view filters. Asking one question at a time avoids recommending "
                "a permission change before the affected user's context is known."
            )
        elif self._is_login_auth_issue(message):
            note = (
                "Login issues happen before a CRM table or form is reached, so the first useful detail is the "
                "exact authentication error and affected scope."
            )
        else:
            note = "The assistant needs enough context to avoid proposing a weak or unrelated resolution."
        if results and confidence != "low":
            top = results[0].source
            note += f" A possible related incident was found ({top.id}), but it is not treated as confirmed evidence yet."
        return note

    def _local_answer(
        self,
        message: str,
        context: ChatContext,
        results: list[RetrievalResult],
        confidence: str,
        allow_external_search: bool,
        follow_ups: list[str],
    ) -> str:
        if not results or confidence == "low":
            external_note = ""
            if allow_external_search and self.enable_external_search:
                external_note = (
                    "\n\nExternal search is enabled for the full OpenAI-backed flow, but no live "
                    "OpenAI API key is configured in this local run."
                )
            return (
                "I do not have a strong enough local match yet. Please share the affected Dynamics "
                "environment, entity/form, deployment or release id, and the exact user-visible symptom."
                f"{external_note}"
            )

        top = results[0]
        if follow_ups and self._is_access_visibility_issue(message):
            return (
                "I found potentially relevant historical knowledge, but this looks like an access or visibility "
                "issue. Before proposing a fix, I need the user's security context so we do not recommend the "
                "wrong role, sharing, ownership, or business-unit change.\n\n"
                f"Closest source so far: {top.source.id} - {top.source.title}.\n\n"
                "Please answer the follow-up questions below, then I can narrow the likely cause and resolution."
            )

        root_cause_chunk = next(
            (result for result in results if result.source.section == "resolution.root_cause"),
            None,
        )
        steps_chunk = next(
            (result for result in results if result.source.section == "resolution.steps"),
            None,
        )
        evidence = steps_chunk or root_cause_chunk or top
        metadata = evidence.source.metadata
        likely_root = (
            root_cause_chunk.content
            if root_cause_chunk
            else "The issue appears similar to a previously resolved Dynamics 365 CRM incident."
        )

        answer_parts = [
            "Likely resolution:",
            evidence.content,
            "",
            "Why this is relevant:",
            (
                f"The closest local source is {top.source.id} - {top.source.title}. "
                f"It matches the reported issue with a {confidence} confidence score."
            ),
        ]
        if metadata.get("entity") or metadata.get("environment") or metadata.get("deployment_id"):
            answer_parts.extend(
                [
                    "",
                    "Matching context:",
                    ", ".join(
                        value
                        for value in [
                            f"environment={metadata.get('environment')}" if metadata.get("environment") else "",
                            f"entity={metadata.get('entity')}" if metadata.get("entity") else "",
                            f"deployment={metadata.get('deployment_id')}" if metadata.get("deployment_id") else "",
                        ]
                        if value
                    ),
                ]
            )
        answer_parts.extend(["", "Likely root cause:", likely_root])
        return "\n".join(answer_parts)

    def _openai_answer(
        self,
        message: str,
        context: ChatContext,
        results: list[RetrievalResult],
        confidence: str,
        allow_external_search: bool,
        follow_ups: list[str],
    ) -> str:
        client = OpenAI(api_key=self.openai_api_key)
        source_block = "\n\n".join(
            f"Source {index + 1}: {result.source.id} | {result.source.title} | "
            f"{result.source.section} | score={result.source.score}\n{result.content}"
            for index, result in enumerate(results)
        )
        tools: list[dict[str, Any]] = []
        if allow_external_search and self.enable_external_search and confidence == "low":
            tools.append({"type": "web_search"})

        prompt = f"""
You are an incident management assistant for Dynamics 365 CRM.
Use internal sources first. Cite incident IDs in the prose. If evidence is weak, ask follow-up questions.
Return concise, actionable resolution steps and do not invent unsupported certainty.
For access, permission, security role, or record visibility issues, collect security role, team/business-unit,
record ownership/sharing, and affected-user scope before recommending a configuration change.

User issue:
{message}

Known context:
{context.model_dump()}

Retrieval confidence:
{confidence}

Required follow-up questions:
{follow_ups or "None"}

Internal sources:
{source_block or "No strong internal source found."}
"""
        response = client.responses.create(
            model=self.openai_model,
            input=prompt,
            tools=tools or None,
        )
        return response.output_text

    def _follow_up_questions(
        self,
        message: str,
        context: ChatContext,
        confidence: str,
        conversation_text: str = "",
    ) -> list[str]:
        questions: list[str] = []
        lowered = message.lower()
        conversation_lowered = conversation_text.lower()
        if self._is_login_auth_issue(conversation_text or message):
            next_question = next_login_auth_question(conversation_lowered or lowered)
            if next_question:
                questions.append(next_question)
        if self._is_access_visibility_issue(conversation_text or message):
            next_question = next_access_question(conversation_lowered)
            if next_question:
                questions.append(next_question)
        if confidence == "low":
            for field, question in REQUIRED_CONTEXT_HINTS.items():
                if field == "entity" and (context.entity or context.entities):
                    continue
                if getattr(context, field) is None and field not in lowered:
                    questions.append(question)
        return dedupe(questions)[:1]

    def _is_access_visibility_issue(self, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ACCESS_VISIBILITY_TERMS)

    def _is_login_auth_issue(self, message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in LOGIN_AUTH_TERMS)

    def _draft_ticket_note(
        self,
        message: str,
        answer_text: str,
        confidence: str,
        sources: list[Source],
    ) -> str:
        source_lines = "\n".join(f"- {source.id}: {source.title} ({source.section})" for source in sources[:4])
        return (
            f"User reported:\n{message}\n\n"
            f"Assistant confidence: {confidence}\n\n"
            f"Suggested resolution/work note:\n{answer_text}\n\n"
            f"Supporting sources:\n{source_lines}"
        )

    def _store_draft_action(self, session_id: str, action: ProposedAction, sources: list[Source]) -> None:
        self.connection.execute(
            """
            INSERT INTO draft_actions(action_id, session_id, summary, draft_note, status, sources_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                action.action_id,
                session_id,
                action.summary,
                action.draft_note,
                action.status,
                json.dumps([source.model_dump() for source in sources]),
            ),
        )
        self.connection.commit()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def select_trusted_results(results: list[RetrievalResult], confidence: str) -> list[RetrievalResult]:
    if confidence == "low" or not results:
        return []
    top_source_id = results[0].source.id
    return [result for result in results if result.source.id == top_source_id]


def next_access_question(conversation_text: str) -> str | None:
    role_known = any(term in conversation_text for term in ["role", "pmo standard user", "system administrator"])
    scope_known = any(
        term in conversation_text
        for term in ["one user", "single user", "all users", "team", "business unit", "everyone", "multiple users"]
    )
    record_scope_known = any(
        term in conversation_text
        for term in ["other client", "other project", "other records", "only one", "specific record", "all records"]
    )
    if not role_known:
        return ACCESS_CONTEXT_QUESTIONS[0]
    if not scope_known:
        return ACCESS_CONTEXT_QUESTIONS[1]
    if not record_scope_known:
        return ACCESS_CONTEXT_QUESTIONS[2]
    return None


def next_login_auth_question(conversation_text: str) -> str | None:
    error_known = any(
        term in conversation_text
        for term in ["error", "message", "code", "aadsts", "unauthorized", "denied", "disabled", "license", "password"]
    )
    scope_known = any(
        term in conversation_text
        for term in ["only me", "one user", "single user", "multiple users", "everyone", "all users"]
    )
    m365_known = any(
        term in conversation_text
        for term in ["office", "outlook", "teams", "sharepoint", "microsoft 365", "m365", "other apps"]
    )
    mfa_stage_known = any(term in conversation_text for term in ["before mfa", "after mfa", "mfa", "page starts loading"])
    if not error_known:
        return LOGIN_AUTH_QUESTIONS[0]
    if not scope_known:
        return LOGIN_AUTH_QUESTIONS[1]
    if not m365_known:
        return LOGIN_AUTH_QUESTIONS[2]
    if not mfa_stage_known:
        return LOGIN_AUTH_QUESTIONS[3]
    return None
