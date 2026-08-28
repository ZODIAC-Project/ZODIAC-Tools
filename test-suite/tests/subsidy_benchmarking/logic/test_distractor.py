import json
import pytest
from ... import helper
from ..shared.prompts import build_matching_task
from ..shared.parsing import parse_match_response, matches_to_dict
from .data import DISTRACTOR_CUSTOMERS, DISTRACTOR_SUBSIDIES, DISTRACTOR_EXPECTED

@pytest.mark.model_quality
def test_agent_picks_best_fit_not_surface_keyword(topic_factory, purpose_factory):
    """
    Test that the agent correctly matches customers to subsidies based on the provided data.
    Distractor: two customers and two subsidies share a surface keyword, only one actually fits
    """
    
    input_topic = topic_factory("input")
    result_topic = topic_factory("matches")
    purpose = purpose_factory("logic")

    helper.reserve_topic(input_topic, aip=[purpose])
    helper.create_agent(
        runOnce=True,
        text=build_matching_task(result_topic),
        purpose=purpose, memoryWindow=5, listenTopic=input_topic,
    )

    payload = json.dumps({"customers": DISTRACTOR_CUSTOMERS, "subsidies": DISTRACTOR_SUBSIDIES})
    helper.publish_message(input_topic, payload)

    raw = helper.listen_to_a_mqtt_topic(result_topic, timeout=300)
    print(f"Raw response from agent: {raw}")
    actual = matches_to_dict(parse_match_response(raw))
    assert actual == DISTRACTOR_EXPECTED, (
        f"Agent hat vermutlich nur auf Keyword-Ähnlichkeit reagiert statt auf Empfängertyp: {actual}"
    )