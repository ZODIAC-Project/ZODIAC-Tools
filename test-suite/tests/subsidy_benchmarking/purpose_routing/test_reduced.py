import pytest
from ... import helper
from ..shared.prompts import build_routing_task

@pytest.mark.access_control
def test_two_agents_one_allowed_one_blocked(topic_factory, purpose_factory):
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    blocked = purpose_factory("blocked")
    result_allowed = topic_factory("result-allowed")
    result_blocked = topic_factory("result-blocked")

    helper.reserve_topic(input_topic, aip=[allowed])

    helper.create_agent(
        runOnce=False,
        text=build_routing_task("Addiere 10 zur empfangenen Zahl.", result_allowed),
        purpose=allowed,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    helper.create_agent(
        runOnce=False,
        text=build_routing_task("Addiere 10 zur empfangenen Zahl.", result_blocked),
        purpose=blocked,
        memoryWindow=5,
        listenTopic=input_topic,
    )

    helper.send_and_expect(input_topic, "5", purposes=[allowed])

    result = helper.listen_to_a_mqtt_topic(result_allowed, timeout=30)
    assert result is not None, "Allowed agent hat nicht reagiert"
    assert "15" in result, f"Falsches Ergebnis: '{result}'"

    leaked = helper.listen_to_a_mqtt_topic(result_blocked, timeout=10)
    assert leaked is None, f"Blocked agent hat trotzdem geantwortet: {leaked}"
