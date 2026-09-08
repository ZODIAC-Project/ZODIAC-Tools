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
    payload = {
        "message": f"msg: {PROMPT}",
        "session_id": session_id,
        "purposes": ["admin"],
    }
    if helper.DEFAULT_LLM_MODEL is not None:
        payload["model"] = helper.DEFAULT_LLM_MODEL
    response = requests.post(
        f"{helper.MCP_URL}/chat",
        json=payload,
        timeout=120,
    )
    duration_ms = (time.perf_counter() - started) * 1_000
    assert response.status_code == 200, response.text
    result = response.json()
    assert result.get("response", "").strip(), "The chat pipeline returned an empty response."
    search_calls = [
        tool_call
        for tool_call in result.get("tool_calls", [])
        if tool_call.get("name") == "search_knowledge_base"
    ]
    assert len(search_calls) == 1, (
        "Expected exactly one search_knowledge_base call, got "
        f"{result.get('tool_calls', [])}"
    )
    return duration_ms


@pytest.mark.rag_latency
def test_rag_latency_through_llm_and_mcp(pytestconfig) -> None:
    """Measure both knowledge bases sequentially through the complete pipeline."""
    repeats = pytestconfig.getoption("rag_latency_repeats")
    for knowledgebase in (
        "restricted_knowledgebase",
        "unrestricted_knowledgebase",
    ):
        durations = [_measure_full_pipeline(knowledgebase) for _ in range(repeats)]
        print(
            f"{knowledgebase}: runs={repeats}, "
            f"mean={statistics.mean(durations):.1f}ms, "
            f"median={statistics.median(durations):.1f}ms, "
            f"samples_ms={[round(duration, 1) for duration in durations]}"
        )
