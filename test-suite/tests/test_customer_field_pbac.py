"""End-to-end tests for field-level customer PBAC.

The test uses the regular MCP chat path and pins every session to the
restricted knowledge base. It verifies the fields returned for each customer
purpose, rather than only checking collection-level access.
"""

from __future__ import annotations

import uuid

import pytest
import requests

from . import helper


QUERY = "Unternehmen Förderung"
CUSTOMER_FIELDS = frozenset(
    {
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
        "jahresUmsatz",
        "personalAnzahl",
    }
)
EXPECTED_FIELDS_BY_PURPOSE = {
    "general": {
        "id",
        "name",
        "state",
        "location",
        "district",
        "legalEntity",
        "businessSector",
        "companySize",
        "clientRole",
        "fundingPlan",
    },
    "subsidy/discovery": {
        "id",
        "name",
        "state",
        "location",
        "district",
        "legalEntity",
        "businessSector",
        "companySize",
        "fundingPlan",
        "jahresUmsatz",
        "personalAnzahl",
    },
    "subsidy/eligibility": {
        "location",
        "district",
        "legalEntity",
        "businessSector",
        "companySize",
        "jahresUmsatz",
        "personalAnzahl",
    },
    "subsidy": {
        "location",
        "legalEntity",
        "businessSector",
        "companySize",
        "fundingPlan",
        "jahresUmsatz",
    },
    "financial_audit": {"jahresUmsatz"},
    "personal": {"personalAnzahl"},
}


def _has_field(response: str, field: str) -> bool:
    """Accept either RAG text or JSON rendered by the MCP chat model."""
    return f"{field}:" in response or f'"{field}":' in response


def _query_customers(purpose: str) -> str:
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
            "purposes": ["admin"],
        },
        timeout=120,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    search_calls = [
        call
        for call in payload.get("tool_calls", [])
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
@pytest.mark.parametrize("purpose", sorted(EXPECTED_FIELDS_BY_PURPOSE))
def test_customer_fields_match_the_requested_purpose(purpose: str) -> None:
    response = _query_customers(purpose)
    expected_fields = EXPECTED_FIELDS_BY_PURPOSE[purpose]

    for field in CUSTOMER_FIELDS:
        assert _has_field(response, field) is (field in expected_fields), (
            f"Unexpected visibility for {field!r} with purpose {purpose!r}: {response}"
        )
