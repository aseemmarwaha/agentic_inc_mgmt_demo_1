from __future__ import annotations

import sqlite3

from app.services.db import connect, init_db
from app.services.embeddings import HashEmbeddingProvider
from app.services.ingestion import ingest_incidents
from app.services.retrieval import Retriever, calculate_confidence


def test_schema_initializes_from_empty_database(temp_data_dir) -> None:
    connection = connect(temp_data_dir / "assistant.db")
    vector_available = init_db(connection)

    rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')").fetchall()
    names = {row["name"] for row in rows}

    assert "incidents" in names
    assert "chunks" in names
    assert isinstance(vector_available, bool)


def test_ingestion_is_idempotent_and_fts_finds_exact_terms(temp_data_dir) -> None:
    connection = connect(temp_data_dir / "assistant.db")
    provider = HashEmbeddingProvider()

    first = ingest_incidents(connection, temp_data_dir / "incidents", provider)
    second = ingest_incidents(connection, temp_data_dir / "incidents", provider)

    assert first.incidents_indexed == 1
    assert second.incidents_indexed == 1
    assert connection.execute("SELECT COUNT(*) AS count FROM incidents").fetchone()["count"] == 1
    assert connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()["count"] == 3

    rows = connection.execute(
        "SELECT incident_id FROM chunks_fts WHERE chunks_fts MATCH ?",
        ("Credit AND Limit",),
    ).fetchall()
    assert rows
    assert rows[0]["incident_id"] == "INC0010245"


def test_retrieval_finds_credit_limit_incident(temp_data_dir) -> None:
    connection = connect(temp_data_dir / "assistant.db")
    provider = HashEmbeddingProvider()
    ingest_incidents(connection, temp_data_dir / "incidents", provider)

    results = Retriever(connection, provider).search("Credit Limit disappeared from Account form")

    assert results
    assert results[0].source.id == "INC0010245"
    assert results[0].source.snippet
    assert calculate_confidence(results) in {"high", "medium"}


def test_low_confidence_when_no_sources() -> None:
    assert calculate_confidence([]) == "low"
