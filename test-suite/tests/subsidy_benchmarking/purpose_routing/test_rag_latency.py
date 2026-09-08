"""End-to-end latency comparison of the two knowledge bases.

The timer deliberately wraps the public `/chat` call, not the RAG HTTP call.
Each measurement therefore includes the LLM and MCP tool invocation path.
"""

from __future__ import annotations

import statistics
import time
import uuid

import pytest
import requests

from ... import helper


PROMPT = (
    "Rufe genau einmal das Tool search_knowledge_base mit collection='subsidies', "
    "purpose='admin' und query='Förderprogramme für Digitalisierung' auf. "
    "Rufe kein weiteres Tool auf und antworte "
    "danach kurz mit dem Ergebnis."
)


def _measure_full_pipeline(knowledgebase: str) -> float:
    session_id = f"rag-latency-{uuid.uuid4()}"
    selection = requests.put(
        f"{helper.MCP_URL}/sessions/{session_id}/knowledgebase",
        json={"knowledgebase": knowledgebase},
        timeout=10,
    )
    assert selection.status_code == 200, selection.text
    started = time.perf_counter()
    response = helper.send(
        PROMPT,
        session_id=session_id,
        purposes=["admin"],
    )
    duration_ms = (time.perf_counter() - started) * 1_000
    assert response.strip(), "The chat pipeline returned an empty response."
    return duration_ms


@pytest.mark.rag_latency
@pytest.mark.parametrize(
    "knowledgebase",
    ["restricted_knowledgebase", "unrestricted_knowledgebase"],
)
def test_rag_latency_through_llm_and_mcp(pytestconfig, knowledgebase: str) -> None:
    """Measure complete chat-to-RAG latency for one knowledge base."""
    repeats = pytestconfig.getoption("rag_latency_repeats")
    durations = [_measure_full_pipeline(knowledgebase) for _ in range(repeats)]

    print(
        f"{knowledgebase}: runs={repeats}, "
        f"mean={statistics.mean(durations):.1f}ms, "
        f"median={statistics.median(durations):.1f}ms, "
        f"samples_ms={[round(duration, 1) for duration in durations]}"
    )
