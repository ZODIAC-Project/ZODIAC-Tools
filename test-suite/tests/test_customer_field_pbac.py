"""End-to-end tests for purpose-specific customer-field projection.

The test uses the same MCP chat path as the other RAG tests.  Each session is
explicitly pinned to ``restricted_knowledgebase`` before it requests customer
data.
"""

from __future__ import annotations

import uuid

import pytest
import requests

from . import helper

QUERY = "Unternehmen Förderung"
BASE_FIELD_LABELS = (
    "id",
    "name",
    "state",
    "location",
    "legalEntity",
    "fundingPlan",
    "district",
    "companySize",
    "clientRole",
    "businessSector",
)


def _has_field(response: str, field: str) -> bool:
    """Accept the two record formats the MCP chat response may use.

    The RAG tool formats records as ``field: value``.  The LLM can preserve
    that text or render the same record as JSON (``"field": "value"``).
    """
    return f"{field}:" in response or f'"{field}":' in response


def _query_customers(purpose: str) -> str:
    """Query customers through MCP, using the restricted knowledge base."""
    session_id = f"customer-field-pbac-{uuid.uuid4()}"
    helper.set_knowledgebase_access(session_id, unrestricted=False)

    response = requests.post(
        f"{helper.MCP_URL}/chat",
        json={
            "message": (
                "Rufe genau einmal das Tool search_knowledge_base mit "
                f"query='{QUERY}', collection='customers', top_k=1 und "
                f"purpose='{purpose}' auf. Rufe kein weiteres Tool auf. "
                "Gib anschließend den vollständigen Inhalt des einen "
                "zurückgegebenen Kundendatensatzes unverändert wieder."
            ),
            "session_id": session_id,
            # ``search_knowledge_base`` is an MCP tool available to the
            # administrative test client.  The purpose under test is passed
            # to the tool itself above, where RAG applies field projection.
            "purposes": ["admin"],
        },
        timeout=120,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    search_calls = [
        call for call in payload.get("tool_calls", [])
        if call.get("name") == "search_knowledge_base"
    ]
    assert len(search_calls) == 1, payload.get("tool_calls", [])
    arguments = search_calls[0].get("args", {})
    assert arguments.get("collection") == "customers"
    assert arguments.get("purpose") == purpose
    assert arguments.get("query") == QUERY
    assert payload.get("response", "").strip(), payload
    return payload["response"]


@pytest.mark.access_control
@pytest.mark.parametrize("purpose", ["admin", "subsidy", "subsidy/eligibility"])
def test_existing_customer_purposes_return_only_base_fields(purpose: str) -> None:
    """Existing purposes keep customer retrieval but never expose sensitive fields."""
    response = _query_customers(purpose)

    for field in BASE_FIELD_LABELS:
        assert _has_field(response, field)
    assert not _has_field(response, "jahresUmsatz")
    assert not _has_field(response, "personalAnzahl")


@pytest.mark.access_control
@pytest.mark.parametrize(
    ("purpose", "allowed_field", "blocked_field"),
    [
        ("subsidy/customer/revenue", "jahresUmsatz", "personalAnzahl"),
        ("subsidy/customer/headcount", "personalAnzahl", "jahresUmsatz"),
    ],
)
def test_customer_sensitive_fields_are_scoped_to_their_purpose(
    purpose: str, allowed_field: str, blocked_field: str
) -> None:
    """Each new purpose returns precisely its one additional customer field."""
    response = _query_customers(purpose)

    assert _has_field(response, allowed_field)
    assert not _has_field(response, blocked_field)
