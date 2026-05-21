from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IncidentChunk:
    incident_id: str
    title: str
    section: str
    content: str
    snippet: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ParsedIncident:
    incident_id: str
    title: str
    payload: dict[str, Any]
    metadata: dict[str, Any]
    chunks: list[IncidentChunk]


def parse_incident_file(path: Path) -> ParsedIncident:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    details = payload.get("incident_details") or {}
    technical = payload.get("technical_context") or {}
    resolution = payload.get("resolution") or {}
    incident_id = str(details.get("incident_id") or payload.get("incident_id") or path.stem)
    title = str(details.get("short_description") or payload.get("title") or incident_id)
    metadata = {
        "priority": details.get("priority"),
        "impact": details.get("impact"),
        "urgency": details.get("urgency"),
        "category": details.get("category"),
        "subcategory": details.get("subcategory"),
        "cmdb_ci": details.get("cmdb_ci"),
        "environment": technical.get("environment"),
        "entity": technical.get("entity"),
        "form_name": technical.get("form_name"),
        "deployment_id": technical.get("deployment_id"),
        "resolved_date": resolution.get("resolved_date"),
    }

    chunks = [
        build_chunk(
            incident_id,
            title,
            "incident.description",
            " ".join(
                value
                for value in [
                    title,
                    str(details.get("description") or ""),
                    str(details.get("category") or ""),
                    str(details.get("subcategory") or ""),
                    str(technical.get("environment") or ""),
                    str(technical.get("entity") or ""),
                    str(technical.get("form_name") or ""),
                    str(technical.get("deployment_id") or ""),
                ]
                if value
            ),
            metadata,
        )
    ]

    root_cause = resolution.get("root_cause")
    if root_cause:
        chunks.append(build_chunk(incident_id, title, "resolution.root_cause", str(root_cause), metadata))

    steps = resolution.get("resolution_steps") or []
    if steps:
        step_text = "\n".join(str(step) for step in steps)
        chunks.append(build_chunk(incident_id, title, "resolution.steps", step_text, metadata))

    return ParsedIncident(
        incident_id=incident_id,
        title=title,
        payload=payload,
        metadata=metadata,
        chunks=chunks,
    )


def build_chunk(
    incident_id: str,
    title: str,
    section: str,
    content: str,
    metadata: dict[str, Any],
) -> IncidentChunk:
    cleaned = " ".join(content.split())
    snippet = cleaned[:280]
    return IncidentChunk(
        incident_id=incident_id,
        title=title,
        section=section,
        content=cleaned,
        snippet=snippet,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
