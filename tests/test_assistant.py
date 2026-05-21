from __future__ import annotations

from app.models import Source
from app.services.assistant import select_trusted_results
from app.services.retrieval import RetrievalResult


def result(source_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        source=Source(
            type="internal_incident",
            id=source_id,
            title=f"{source_id} title",
            section="resolution.steps",
            snippet="snippet",
            score=score,
        ),
        content="content",
        vector_score=score,
        keyword_score=0.0,
    )


def test_trusted_results_hide_all_sources_for_low_confidence() -> None:
    assert select_trusted_results([result("INC1", 0.2)], "low") == []


def test_trusted_results_keep_only_top_incident_family() -> None:
    selected = select_trusted_results(
        [
            result("INC1", 0.7),
            result("INC2", 0.68),
            result("INC1", 0.55),
        ],
        "medium",
    )

    assert [item.source.id for item in selected] == ["INC1", "INC1"]
