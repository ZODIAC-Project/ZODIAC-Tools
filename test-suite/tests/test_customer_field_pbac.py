"""Integration tests for purpose-specific customer-field projection.

Run against the restricted RAG service.  When the service is not exposed on
localhost, set RAG_SERVICE_URL to its reachable URL (for example via
``kubectl port-forward service/rag-service 30110:30110 -n zodiac``).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import requests


RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:30110").rstrip("/")
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


def _query_customers(purpose: str) -> dict[str, Any]:
    response = requests.post(
        f"{RAG_SERVICE_URL}/collections/customers/query",
        json={
            "query_texts": [QUERY],
            "n_results": 3,
            "purpose": purpose,
            "include": ["documents", "metadatas"],
        },
        timeout=15,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["documents"] and payload["documents"][0], payload
    return payload


@pytest.mark.access_control
@pytest.mark.parametrize("purpose", ["admin", "subsidy", "subsidy/eligibility"])
def test_existing_customer_purposes_return_only_base_fields(purpose: str) -> None:
    """Existing purposes keep customer retrieval but never expose sensitive fields."""
    payload = _query_customers(purpose)

    for document, metadata in zip(payload["documents"][0], payload["metadatas"][0]):
        for field in BASE_FIELD_LABELS:
            assert f"{field}:" in document
        assert "jahresUmsatz:" not in document
        assert "personalAnzahl:" not in document
        assert "jahresUmsatz" not in metadata
        assert "personalAnzahl" not in metadata


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
    payload = _query_customers(purpose)

    for document, metadata in zip(payload["documents"][0], payload["metadatas"][0]):
        assert f"{allowed_field}:" in document
        assert f"{blocked_field}:" not in document
        assert allowed_field in metadata
        assert blocked_field not in metadata
