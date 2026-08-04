import random
import pytest
from ... import helper
from ..shared.prompts import build_routing_task

@pytest.fixture
def n_agents(run_config):
    return run_config.get("n_agents", 8)   # 8 = local-dev default

@pytest.mark.access_control
def test_n_agent_random_purposes(topic_factory, purpose_factory, n_agents):
    N = n_agents
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    helper.reserve_topic(input_topic, aip=[allowed])

    agents = []
    for i in range(N):
        is_allowed = random.random() < 0.5
        p = allowed if is_allowed else purpose_factory(f"blocked-{i}")
        result_topic = topic_factory(f"result-{i}")
        helper.create_agent(
            runOnce=False,
            text=build_routing_task("Addiere 100 zur empfangenen Zahl.", result_topic),
            purpose=p,
            memoryWindow=5,
            listenTopic=input_topic,
        )
        agents.append({"allowed": is_allowed, "result_topic": result_topic})

    helper.publish_message(input_topic, "1")

    topics_with_timeouts = [
        (a["result_topic"], 120 if a["allowed"] else 12)
        for a in agents
    ]
    results = helper.listen_to_multiple_mqtt_topics(topics_with_timeouts)

    failures = []
    for i, (a, result) in enumerate(zip(agents, results)):
        if a["allowed"] and (result is None or "101" not in result):
            failures.append(f"agent {i} (allowed) got: {result}")
        if not a["allowed"] and result is not None:
            failures.append(f"agent {i} (blocked) leaked: {result}")
    assert not failures, "\n".join(failures)
