from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def detect_vector_extension(connection: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec  # type: ignore

        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return True
    except Exception:
        return False


def init_db(connection: sqlite3.Connection) -> bool:
    vector_available = detect_vector_extension(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT 'internal_incident',
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            content TEXT NOT NULL,
            snippet TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            incident_id,
            title,
            section,
            content,
            tokenize = 'porter'
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS draft_actions (
            action_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            draft_note TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sources_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ticket_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id TEXT NOT NULL REFERENCES draft_actions(action_id),
            target_ticket_id TEXT NOT NULL,
            update_note TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    connection.commit()
    return vector_available


def replace_incident(
    connection: sqlite3.Connection,
    incident_id: str,
    title: str,
    payload: dict[str, Any],
    metadata: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> int:
    connection.execute(
        """
        INSERT INTO incidents(incident_id, title, payload_json, metadata_json, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(incident_id) DO UPDATE SET
            title = excluded.title,
            payload_json = excluded.payload_json,
            metadata_json = excluded.metadata_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (incident_id, title, json.dumps(payload), json.dumps(metadata)),
    )
    existing_ids = [
        row["id"]
        for row in connection.execute("SELECT id FROM chunks WHERE incident_id = ?", (incident_id,)).fetchall()
    ]
    if existing_ids:
        placeholders = ",".join("?" for _ in existing_ids)
        connection.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", existing_ids)
    connection.execute("DELETE FROM chunks WHERE incident_id = ?", (incident_id,))

    count = 0
    for chunk in chunks:
        cursor = connection.execute(
            """
            INSERT INTO chunks(
                incident_id, source_type, title, section, content, snippet, embedding_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                chunk.get("source_type", "internal_incident"),
                chunk["title"],
                chunk["section"],
                chunk["content"],
                chunk["snippet"],
                json.dumps(chunk["embedding"]),
                json.dumps(chunk.get("metadata", {})),
            ),
        )
        chunk_id = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO chunks_fts(chunk_id, incident_id, title, section, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chunk_id, incident_id, chunk["title"], chunk["section"], chunk["content"]),
        )
        count += 1
    connection.commit()
    return count
