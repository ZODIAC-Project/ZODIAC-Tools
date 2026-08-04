import json
import time
import pytest
from ... import helper
from ..shared.prompts import build_multi_message_matching_task
from ..shared.parsing import parse_match_response, matches_to_dict
from .data import CLEAN_CUSTOMERS, CLEAN_SUBSIDIES, CLEAN_EXPECTED

@pytest.mark.model_quality
def test_agent_accumulates_multiple_messages(topic_factory, purpose_factory):
    """
    Test that the agent correctly accumulates multiple messages and matches customers to subsidies based on the provided data.
    Simple two customers and two Subsidies, where each customer has a clear best match.
    """
    
    input_topic = topic_factory("input")
    result_topic = topic_factory("matches")
    purpose = purpose_factory("logic")

    helper.reserve_topic(input_topic, aip=[purpose])
    helper.create_agent(
        runOnce=False,
        text=build_multi_message_matching_task(result_topic),
        purpose=purpose, 
        memoryWindow=10, 
        listenTopic=input_topic,
    )

    helper.publish_message(input_topic, json.dumps({"customers": CLEAN_CUSTOMERS}))
    helper.publish_message(input_topic, json.dumps({"subsidies": CLEAN_SUBSIDIES}))

    raw = helper.listen_to_a_mqtt_topic(result_topic, timeout=200)
    actual = matches_to_dict(parse_match_response(raw))
    
    time.sleep(300)
    assert actual == CLEAN_EXPECTED, f"Matching falsch: {actual}"