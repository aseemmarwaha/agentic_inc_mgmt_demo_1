from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from app.models import Confidence, Source
from app.services.embeddings import EmbeddingProvider, cosine_similarity


@dataclass
class RetrievalResult:
    source: Source
    content: str
    vector_score: float
    keyword_score: float


def fts_query(text: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text)
    useful = [token for token in tokens if len(token) > 2][:10]
    return " OR ".join(useful) or text


class Retriever:
    def __init__(self, connection: sqlite3.Connection, embedding_provider: EmbeddingProvider) -> None:
        self.connection = connection
        self.embedding_provider = embedding_provider

    def search(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        query_embedding = self.embedding_provider.embed(query)
        keyword_scores = self._keyword_scores(query)
        vector_results = self._vector_scores(query_embedding)
        merged: dict[int, tuple[sqlite3.Row, float, float]] = {}

        for row, score in vector_results:
            merged[row["id"]] = (row, score, keyword_scores.get(row["id"], 0.0))

        for chunk_id, keyword_score in keyword_scores.items():
            if chunk_id in merged:
                row, vector_score, _ = merged[chunk_id]
                merged[chunk_id] = (row, vector_score, keyword_score)
            else:
                row = self.connection.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
                if row:
                    merged[chunk_id] = (row, 0.0, keyword_score)

        ranked = sorted(
            merged.values(),
            key=lambda item: (0.72 * item[1]) + (0.28 * item[2]),
            reverse=True,
        )
        return [self._to_result(row, vector_score, keyword_score) for row, vector_score, keyword_score in ranked[:limit]]

    def _keyword_scores(self, query: str) -> dict[int, float]:
        try:
            rows = self.connection.execute(
                """
                SELECT chunk_id, bm25(chunks_fts) AS rank
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                LIMIT 12
                """,
                (fts_query(query),),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}

        scores: dict[int, float] = {}
        for index, row in enumerate(rows):
            scores[int(row["chunk_id"])] = max(0.1, 1.0 - (index * 0.08))
        return scores

    def _vector_scores(self, query_embedding: list[float]) -> list[tuple[sqlite3.Row, float]]:
        rows = self.connection.execute("SELECT * FROM chunks").fetchall()
        scored: list[tuple[sqlite3.Row, float]] = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            score = cosine_similarity(query_embedding, embedding)
            scored.append((row, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:12]

    def _to_result(self, row: sqlite3.Row, vector_score: float, keyword_score: float) -> RetrievalResult:
        combined = (0.72 * vector_score) + (0.28 * keyword_score)
        metadata = json.loads(row["metadata_json"])
        source = Source(
            type=row["source_type"],
            id=row["incident_id"],
            title=row["title"],
            section=row["section"],
            snippet=row["snippet"],
            score=round(combined, 4),
            metadata=metadata,
        )
        return RetrievalResult(source=source, content=row["content"], vector_score=vector_score, keyword_score=keyword_score)


def calculate_confidence(results: list[RetrievalResult]) -> Confidence:
    if not results:
        return "low"
    top_score = results[0].source.score or 0.0
    if top_score >= 0.68 and len(results) >= 2:
        return "high"
    if top_score >= 0.38:
        return "medium"
    return "low"
