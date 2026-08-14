import json
import pytest
import time
import requests
from ...helper import *
from ..shared.prompts import build_routing_task


MESSAGE_TIMEOUT = 30.0

@pytest.mark.access_control
def test_two_agents_one_allowed_one_blocked(topic_factory, purpose_factory):
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    blocked = purpose_factory("blocked")
    result_allowed = topic_factory("result-allowed")
    result_blocked = topic_factory("result-blocked")
    
    reserve_topic(input_topic, aip=[allowed])
    
    id_1 = create_agent(
        runOnce=False,
        text=build_routing_task("Addiere 10 zur empfangenen Zahl.", result_allowed),
        purpose=allowed,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    id_2 = create_agent(
        runOnce=False,
        text=build_routing_task("Addiere 10 zur empfangenen Zahl.", result_blocked),
        purpose=blocked,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    
    time.sleep(2)  # wait for agents to be ready
    # check if agent is there 
    agent1_existis = check_agent_exists(id_1)
    assert agent1_existis, f"Agent 1 with ID {id_1} does not exist."
    agent2_existis = check_agent_exists(id_2)
    assert agent2_existis, f"Agent 2 with ID {id_2} does not exist."
    
    # send a message and check both histories 
    publish_response = publish_message(input_topic, json.dumps({"number": 5}))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
    
    agentHistory_1 = get_agent_history(id_1)
    print(f"Agent 1 history: {agentHistory_1}")
    agentHistory_2 = get_agent_history(id_2)
    print(f"Agent 2 history: {agentHistory_2}")
    
    # Listen to the result topics to ensure messages are received
    result_1 = listen_to_a_mqtt_topic(result_allowed, timeout=120)
    result_2 = listen_to_a_mqtt_topic(result_blocked, timeout=10)
    
    assert result_1 is not None and "15" in result_1, f"Agent 1 (allowed) did not receive expected result: {result_1}"
    assert result_2 is None, f"Agent 2 (blocked) should not have received a result, but got: {result_2}"
    