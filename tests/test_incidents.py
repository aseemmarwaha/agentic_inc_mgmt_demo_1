from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.incidents import build_chunk, parse_incident_file


def test_parse_incident_file_creates_source_linked_chunks(tmp_path: Path, sample_incident_payload: dict) -> None:
    path = tmp_path / "incident.json"
    path.write_text(json.dumps(sample_incident_payload), encoding="utf-8")

    parsed = parse_incident_file(path)

    assert parsed.incident_id == "INC0010245"
    assert parsed.title == "Credit Limit field missing from Account Form"
    assert {chunk.section for chunk in parsed.chunks} == {
        "incident.description",
        "resolution.root_cause",
        "resolution.steps",
    }
    assert all(chunk.incident_id == "INC0010245" for chunk in parsed.chunks)


def test_parse_incident_file_uses_filename_when_incident_id_missing(tmp_path: Path) -> None:
    path = tmp_path / "fallback.json"
    path.write_text(json.dumps({"incident_details": {"short_description": "Missing id"}}), encoding="utf-8")

    parsed = parse_incident_file(path)

    assert parsed.incident_id == "fallback"
    assert parsed.title == "Missing id"


def test_parse_incident_file_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError):
        parse_incident_file(path)


def test_build_chunk_preserves_metadata_and_snippet() -> None:
    chunk = build_chunk(
        "INC1",
        "Title",
        "resolution.steps",
        "  Step one.   Step two.  ",
        {"entity": "account", "empty": None},
    )

    assert chunk.content == "Step one. Step two."
    assert chunk.snippet == "Step one. Step two."
    assert chunk.metadata == {"entity": "account"}
