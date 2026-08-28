import json
import pytest
from ... import helper
from ..shared.prompts import build_matching_task
from ..shared.parsing import parse_match_response, matches_to_dict
from .data import CLEAN_CUSTOMERS, CLEAN_SUBSIDIES, CLEAN_EXPECTED

@pytest.mark.model_quality
def test_agent_matches_customers_to_subsidies(topic_factory, purpose_factory):
    """Test that the agent correctly matches customers to subsidies based on the provided data.
        Simple two customers and two Subsidies, where each customer has a clear best match.
    """
    
    input_topic = topic_factory("input")
    result_topic = topic_factory("matches")
    purpose = purpose_factory("logic")
    
    print(f"Input topic: {input_topic}, Result topic: {result_topic}, Purpose: {purpose}")

    helper.reserve_topic(input_topic, aip=[purpose])
    helper.create_agent(
        runOnce=True,
        text=build_matching_task(result_topic),
        purpose=purpose, 
        memoryWindow=5, 
        listenTopic=input_topic,
    )

    payload = json.dumps({"customers": CLEAN_CUSTOMERS, "subsidies": CLEAN_SUBSIDIES})
    helper.publish_message(input_topic, payload)

    raw = helper.listen_to_a_mqtt_topic(result_topic, timeout=120)
    print(f"Raw response from agent: {raw}")
    actual = matches_to_dict(parse_match_response(raw))
    assert actual == CLEAN_EXPECTED, f"Matching falsch: {actual}"