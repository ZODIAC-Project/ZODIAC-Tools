import json
import pytest
import time
import requests
from ...helper import *
from ..shared.prompts import build_routing_task


MESSAGE_TIMEOUT = 30.0


def get_agent_history(agent_id: str, limit: int = 80) -> list:
    response = requests.get(f"{AGENT_URL}/agents/{agent_id}/history", params={"limit": limit}, timeout=10.0)
    assert response.status_code == 200, f"Failed to fetch history for agent {agent_id}: {response.text}"
    data = response.json()
    if isinstance(data, dict):
        return data.get("history", [])
    return data


def wait_for_message_in_history(agent_id: str, expected_payload: str, timeout: float = MESSAGE_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = get_agent_history(agent_id)
        for entry in history:
            content = entry.get("content", "") or entry.get("message", "") or entry.get("text", "") or str(entry)
            if expected_payload in content:
                return True
        time.sleep(0.5)
    return False



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
    agents_response = requests.get(f"{AGENT_URL}/agents", timeout=30)
    assert agents_response.status_code == 200, f"Failed to retrieve agent list: {agents_response.text}"
    agents = agents_response.json()
    agent1_info = next((a for a in agents if a.get("id") == id_1), None)
    print(f"Agent 1 info: {agent1_info}")
    agent2_info = next((a for a in agents if a.get("id") == id_2), None)
    print(f"Agent 2 info: {agent2_info}")
    assert agent1_info is not None, f"Failed to retrieve info for Agent 1: {agent1_info}"
    assert agent2_info is not None, f"Failed to retrieve info for Agent 2: {agent2_info}"
    
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
    