from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def sample_incident_payload() -> dict:
    return {
        "incident_details": {
            "incident_id": "INC0010245",
            "short_description": "Credit Limit field missing from Account Form",
            "description": "After deployment, the Credit Limit field disappeared from the Account Main Form.",
            "category": "Software",
            "subcategory": "UI/UX",
            "cmdb_ci": "Dynamics 365 Production Instance",
        },
        "technical_context": {
            "environment": "Production",
            "entity": "account",
            "form_name": "Account Main Form",
            "deployment_id": "REL_2023_OCT_S2",
        },
        "resolution": {
            "root_cause": "The field was accidentally removed from the form in Development.",
            "resolution_steps": [
                "Verify the field exists in Dataverse.",
                "Re-add the Credit Limit field to the Financials section.",
                "Publish the form and deploy a hotfix solution.",
            ],
            "resolved_date": "2023-10-28T10:00:00Z",
        },
    }


@pytest.fixture
def temp_data_dir(tmp_path: Path, sample_incident_payload: dict) -> Path:
    incidents = tmp_path / "incidents"
    incidents.mkdir()
    (incidents / "INC0010245.json").write_text(json.dumps(sample_incident_payload), encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(temp_data_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "your_openai_api_key_here")
    monkeypatch.setenv("USE_OPENAI_EMBEDDINGS", "false")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
