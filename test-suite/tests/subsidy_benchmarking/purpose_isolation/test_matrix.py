import pytest
from tests import helper
from ..shared.matrix import PBAC_MATRIX
from ..shared.prompts import build_instruction, ADMIN

RAG_DOC_ID = "isolation-test-doc"

@pytest.mark.access_control
@pytest.mark.parametrize("vector_on,broker_on,mcp_on", PBAC_MATRIX)
def test_isolation_matrix(vector_on, broker_on, mcp_on, topic_factory, purpose_factory):
    topic = topic_factory("proposal")
    purpose_a = purpose_factory("A") if broker_on else ADMIN
    purpose_b = purpose_factory("B") if broker_on else ADMIN
    vector_purpose = purpose_factory("rag") if vector_on else None
    mcp_purpose = purpose_factory("mcp") if mcp_on else None
    result_topic = topic_factory("result")

    if vector_on:
        helper.seed_rag([{"id": RAG_DOC_ID, "text": "geheime testinformation"}], vector_purpose)

    helper.reserve_topic(topic, aip=[purpose_a])

    base_task = (
        f"Höre auf eingehende Nachrichten. Wenn du eine erhältst, suche in RAG nach "
        f"'{RAG_DOC_ID}' und veröffentliche das Ergebnis (Inhalt oder 'ACCESS_DENIED') "
        f"auf Topic '{result_topic}'."
    )
    helper.create_agent(
        runOnce=False,
        text=build_instruction(base_task, vector_purpose, mcp_purpose),
        purpose=purpose_a, memoryWindow=5, listenTopic=topic,
    )

    helper.send_and_expect(topic, "trigger", purposes=[purpose_a])
    result = helper.listen_to_a_mqtt_topic(result_topic, timeout=30)

    assert result is not None, "Agent hat nicht reagiert"
    if vector_on:
        assert "ACCESS_DENIED" not in result, f"Erwarteter RAG-Zugriff wurde verweigert: {result}"
