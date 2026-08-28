import json
import pytest
from ... import helper
from ..shared.prompts import build_matching_task
from ..shared.parsing import parse_match_response, matches_to_dict
from .data import NOMATCH_CUSTOMERS, NOMATCH_SUBSIDIES, NOMATCH_EXPECTED


@pytest.mark.model_quality
def test_agent_does_not_force_a_match(topic_factory, purpose_factory):
    input_topic = topic_factory("input")
    result_topic = topic_factory("matches")
    purpose = purpose_factory("logic")

    helper.reserve_topic(input_topic, aip=[purpose])
    helper.create_agent(
        runOnce=True,
        text=build_matching_task(result_topic, allow_no_match=True),
        purpose=purpose, memoryWindow=5, listenTopic=input_topic,
    )

    payload = json.dumps({"customers": NOMATCH_CUSTOMERS, "subsidies": NOMATCH_SUBSIDIES})
    helper.publish_message(input_topic, payload)

    raw = helper.listen_to_a_mqtt_topic(result_topic, timeout=120)
    actual = matches_to_dict(parse_match_response(raw))

    assert "sub-3" not in actual.values(), (
        f"Agent hat der nicht passenden Subsidy 'sub-3' trotzdem einen Customer zugeordnet: {actual}"
    )
    for cust_id, sub_id in NOMATCH_EXPECTED.items():
        assert actual.get(cust_id) == sub_id, f"Erwartetes Matching für {cust_id} fehlt/falsch: {actual}"