from __future__ import annotations


def test_chat_creates_session_and_returns_cited_answer(client) -> None:
    ingest = client.post("/api/ingest")
    assert ingest.status_code == 200

    response = client.post(
        "/api/chat",
        json={
            "message": "Credit Limit field disappeared from the Account Main Form after deployment",
            "context": {"application": "Dynamics 365 CRM", "environment": "Production", "entity": "account"},
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["confidence"] in {"high", "medium"}
    assert payload["sources"]
    assert payload["sources"][0]["id"] == "INC0010245"
    assert "Credit Limit" in payload["answer"] or "field" in payload["answer"]
    assert "proposed_actions" in payload


def test_chat_accepts_multi_selected_entities_context(client) -> None:
    ingest = client.post("/api/ingest")
    assert ingest.status_code == 200

    response = client.post(
        "/api/chat",
        json={
            "message": "Credit Limit field disappeared from the main form after deployment",
            "context": {
                "application": "Dynamics 365 CRM",
                "environment": "Production",
                "entities": ["account", "contact"],
            },
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]
    assert payload["sources"][0]["id"] == "INC0010245"


def test_access_visibility_issue_asks_for_role_context_before_action(client) -> None:
    client.post("/api/ingest")

    response = client.post(
        "/api/chat",
        json={
            "message": "I am unable to view client project",
            "context": {"application": "Dynamics 365 CRM", "environment": "Production"},
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    questions = " ".join(payload["follow_up_questions"]).lower()
    assert "security role" in questions
    assert len(payload["follow_up_questions"]) == 1
    assert "i understand" in payload["answer"].lower()
    assert "first question" in payload["answer"].lower()
    assert "PMO Standard User" not in payload["answer"]
    assert payload["sources"] == []
    assert payload["proposed_actions"] == []
    assert payload["diagnostic_note"]


def test_login_issue_asks_for_auth_error_not_entity(client) -> None:
    client.post("/api/ingest")

    response = client.post(
        "/api/chat",
        json={
            "message": "I am unable to log in to the CRM application",
            "context": {"application": "Dynamics 365 CRM", "environment": "Production"},
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    questions = " ".join(payload["follow_up_questions"]).lower()
    assert "exact error message" in questions
    assert "table/entity" not in questions
    assert "unable to log in" in payload["answer"].lower()
    assert payload["sources"] == []
    assert payload["proposed_actions"] == []


def test_access_visibility_questions_are_asked_one_by_one(client) -> None:
    client.post("/api/ingest")
    first = client.post(
        "/api/chat",
        json={
            "message": "I am unable to view client project",
            "context": {"application": "Dynamics 365 CRM", "environment": "Production"},
            "allow_external_search": True,
        },
    ).json()

    second = client.post(
        "/api/chat",
        json={
            "session_id": first["session_id"],
            "message": "The user's role is PMO Standard User",
            "context": {"application": "Dynamics 365 CRM", "environment": "Production"},
            "allow_external_search": True,
        },
    ).json()

    assert len(second["follow_up_questions"]) == 1
    assert "one user" in second["follow_up_questions"][0].lower()


def test_rebuild_index_chat_command_runs_ingestion_without_ticket_draft(client) -> None:
    response = client.post(
        "/api/chat",
        json={
            "message": "can you rebuild the index?",
            "context": {"application": "Dynamics 365 CRM"},
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "rebuilt the local incident index" in payload["answer"]
    assert "Indexed 1 incidents and 3 chunks" in payload["answer"]
    assert payload["sources"] == []
    assert payload["proposed_actions"] == []


def test_index_status_reports_not_ready_before_ingestion(client) -> None:
    response = client.get("/api/index/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed"] is False
    assert payload["incidents_indexed"] == 0
    assert payload["chunks_indexed"] == 0
    assert "not built" in payload["message"]


def test_index_status_reports_ready_after_ingestion(client) -> None:
    client.post("/api/ingest")
    response = client.get("/api/index/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed"] is True
    assert payload["incidents_indexed"] == 1
    assert payload["chunks_indexed"] == 3
    assert "Index ready" in payload["message"]


def test_low_confidence_answer_does_not_show_weak_sources(client) -> None:
    client.post("/api/ingest")

    response = client.post(
        "/api/chat",
        json={
            "message": "printer toner jam",
            "context": {"application": "Dynamics 365 CRM"},
            "allow_external_search": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] == "low"
    assert payload["sources"] == []
    assert payload["proposed_actions"] == []


def test_session_restore_preserves_multi_turn_messages(client) -> None:
    client.post("/api/ingest")
    first = client.post(
        "/api/chat",
        json={"message": "Credit Limit missing", "context": {"environment": "Production", "entity": "account"}},
    ).json()
    second = client.post(
        "/api/chat",
        json={
            "session_id": first["session_id"],
            "message": "It started after REL_2023_OCT_S2",
            "context": {"environment": "Production", "entity": "account"},
        },
    )
    assert second.status_code == 200

    restored = client.get(f"/api/sessions/{first['session_id']}")
    assert restored.status_code == 200
    messages = restored.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]


def test_confirm_draft_persists_only_approved_update(client) -> None:
    client.post("/api/ingest")
    chat = client.post(
        "/api/chat",
        json={
            "message": "Credit Limit disappeared from Account form",
            "context": {"environment": "Production", "entity": "account"},
        },
    ).json()
    action_id = chat["proposed_actions"][0]["action_id"]

    confirm = client.post(
        f"/api/ticket-drafts/{action_id}/confirm",
        json={"approved": True, "target_ticket_id": "INC-DEMO"},
    )

    assert confirm.status_code == 200
    payload = confirm.json()
    assert payload["status"] == "approved"
    assert payload["stored_update_id"] is not None


def test_invalid_session_and_missing_draft_return_404(client) -> None:
    assert client.get("/api/sessions/missing").status_code == 404
    response = client.post(
        "/api/ticket-drafts/missing/confirm",
        json={"approved": True, "target_ticket_id": "INC-DEMO"},
    )
    assert response.status_code == 404


def test_chat_html_loads(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Incident Management Assistant" in response.text
    assert "Rebuild index" in response.text
    assert "Start voice" in response.text
    assert "index-status" in response.text
    assert "The local incident index is ready" in response.text
    assert "Common high-priority issues" in response.text
    assert 'data-priority-prompt="I am unable to log in to the CRM application"' in response.text
    assert "Unable to log in" in response.text
    assert "Cannot view records" in response.text
    assert 'id="environment" placeholder="Production" value="Production" disabled' in response.text
    assert "Select one or more tables" in response.text
    assert "/api/reference/entities" in response.text
    assert "Used only when you confirm a mock ticket update" in response.text


def test_reference_entities_returns_standard_dynamics_tables(client) -> None:
    response = client.get("/api/reference/entities")

    assert response.status_code == 200
    payload = response.json()
    logical_names = {entity["logical_name"] for entity in payload}
    assert {"account", "contact", "opportunity", "incident", "salesorder"}.issubset(logical_names)
    assert all({"label", "logical_name", "area", "description"} <= set(entity) for entity in payload)


def test_realtime_client_secret_requires_openai_key(client) -> None:
    response = client.post("/api/realtime/client-secret")

    assert response.status_code == 400
    assert "OPENAI_API_KEY is not configured" in response.json()["detail"]
