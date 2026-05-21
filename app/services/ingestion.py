from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models import IngestResponse
from app.services.db import init_db, replace_incident
from app.services.embeddings import EmbeddingProvider
from app.services.incidents import parse_incident_file


def ingest_incidents(
    connection: sqlite3.Connection,
    incidents_dir: Path,
    embedding_provider: EmbeddingProvider,
) -> IngestResponse:
    vector_available = init_db(connection)
    incidents_indexed = 0
    chunks_indexed = 0
    for path in sorted(incidents_dir.glob("*.json")):
        parsed = parse_incident_file(path)
        chunk_payloads = []
        for chunk in parsed.chunks:
            chunk_payloads.append(
                {
                    "title": chunk.title,
                    "section": chunk.section,
                    "content": chunk.content,
                    "snippet": chunk.snippet,
                    "metadata": chunk.metadata,
                    "embedding": embedding_provider.embed(
                        f"{chunk.title}\n{chunk.section}\n{chunk.content}\n{chunk.metadata}"
                    ),
                }
            )
        chunks_indexed += replace_incident(
            connection,
            parsed.incident_id,
            parsed.title,
            parsed.payload,
            parsed.metadata,
            chunk_payloads,
        )
        incidents_indexed += 1
    return IngestResponse(
        incidents_indexed=incidents_indexed,
        chunks_indexed=chunks_indexed,
        vector_extension_available=vector_available,
    )
