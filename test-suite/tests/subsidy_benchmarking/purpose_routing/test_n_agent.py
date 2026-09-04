import random
import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from ... import helper
from ..shared.prompts import build_routing_task

@pytest.fixture
def n_agents(pytestconfig):
    n_agents_from_cli = pytestconfig.getoption("n_agents")
    return 8 if n_agents_from_cli is None else n_agents_from_cli  # 8 = local-dev default

@pytest.mark.access_control
def test_n_agent(topic_factory, purpose_factory, n_agents):
    N = n_agents
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    helper.reserve_topic(input_topic, aip=[allowed])

    agents = []
    for i in range(N):
        is_allowed = random.random() < 0.5
        purpose = allowed if is_allowed else purpose_factory(f"blocked-{i}")
        result_topic = topic_factory(f"result-{i}")
        helper.create_agent(
            runOnce=False,
            text=build_routing_task("Addiere 100 zur empfangenen Zahl.", result_topic),
            purpose=purpose,
            memoryWindow=5,
            listenTopic=input_topic,
        )
        agents.append({"allowed": is_allowed, "result_topic": result_topic})

    # Give agents a moment to subscribe before sending the trigger message.
    time.sleep(1)

    topics_with_timeouts = [
        (a["result_topic"], 240 if a["allowed"] else 12)
        for a in agents
    ]

    # Start listeners first to avoid racing and missing fast responses.
    with ThreadPoolExecutor(max_workers=N) as executor:
        futures = [
            executor.submit(helper.listen_to_a_mqtt_topic, topic, timeout)
            for topic, timeout in topics_with_timeouts
        ]
        time.sleep(1)
        helper.publish_message(input_topic, "1")
        results = [future.result() for future in futures]

    failures = []
    for i, (a, result) in enumerate(zip(agents, results)):
        if a["allowed"] and (result is None or "101" not in result):
            failures.append(f"agent {i} (allowed) got: {result}")
        if not a["allowed"] and result is not None:
            failures.append(f"agent {i} (blocked) leaked: {result}")
            
    assert not failures, "\n".join(failures)

