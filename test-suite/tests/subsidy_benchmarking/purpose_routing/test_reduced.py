import json
import pytest
import httpx
import time
from ...helper import *
from ..shared.prompts import build_routing_task



@pytest.mark.access_control
def test_two_agents_one_allowed_one_blocked(topic_factory, purpose_factory):
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    blocked = purpose_factory("blocked")
    result_allowed = topic_factory("result-allowed")
    result_blocked = topic_factory("result-blocked")
    
    reserve_topic(input_topic, aip=[allowed])
    reserve_topic(result_allowed, aip=["Admin"])   # add
    reserve_topic(result_blocked, aip=["Admin"])   # add

    
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
    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent1_info = next((a for a in agents if a.get("id") == id_1), None)
    print(f"Agent 1 info: {agent1_info}")
    agent2_info = next((a for a in agents if a.get("id") == id_2), None)
    print(f"Agent 2 info: {agent2_info}")
    assert agent1_info is not None, f"Failed to retrieve info for Agent 1: {agent1_info}"
    assert agent2_info is not None, f"Failed to retrieve info for Agent 2: {agent2_info}"
    assert allowed in agent1_info.get("purposes", []), (
        f"Expected Agent 1 to have purpose '{allowed}' but got {agent1_info.get('purposes')}"
    )
    assert blocked in agent2_info.get("purposes", []), (
        f"Expected Agent 2 to have purpose '{blocked}' but got {agent2_info.get('purposes')}"
    )
    
    # send a message and check both histories 
    publish_response = send_and_expect(input_topic, json.dumps({"number": 5}), purposes=[allowed, blocked])
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
    time.sleep(10)
    
    agentHistory_1 = httpx.get(f"{AGENT_URL}/{id_1}/history", timeout=5.0).json()
    print(f"Agent 1 history: {agentHistory_1}")
    agentHistory_2 = httpx.get(f"{AGENT_URL}/{id_2}/history", timeout=5.0).json()
    print(f"Agent 2 history: {agentHistory_2}")
    
    # assert correct routing 
    # Check if '15' exists in the allowed agent's history strings
    assert any("5" in entry for entry in agentHistory_1), f"Result '5' not found in Agent 1 history: {agentHistory_1}"
    
    # Check if '15' is NOT in the blocked agent's history strings
    # (Using 'not any' is cleaner than 'any(...) is False')
    assert not any("5" in entry for entry in agentHistory_2), f"Result '5' should not be in Agent 2 history: {agentHistory_2}"
    
    # assert correct result for allowed agent
    agentHistory_1 = httpx.get(f"{AGENT_URL}/{id_1}/history", timeout=5.0).json()

    assert any("15" in entry.get("message", "") for entry in agentHistory_1), f"Result '15' not found in Agent 1 history: {agentHistory_1}"
