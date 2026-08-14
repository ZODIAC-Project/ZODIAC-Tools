"""
Component-level PBAC isolation tests.

These tests check purpose enforcement independently in each of the three
components that can filter by purpose — the MQTT broker, the MCP tool layer,
and the vector database (RAG) — before those components are exercised
together in the full end-to-end scenario test. Testing each mechanism in
isolation first means that if the combined scenario test later fails, the
failure can be attributed to how the components interact rather than to a
broken purpose-filtering mechanism in any single one of them.

Each test below follows the same enabled/disabled structure: a case where
purpose filtering is active and enforces a restriction, and a case where
filtering is bypassed or absent and access is unrestricted.

"""
import json
import pytest
import time as time
import requests
from ...helper import *
from ..shared.prompts import *

import logging
logging.disable(logging.CRITICAL)

def test_broker_isolation(topic_factory, purpose_factory):
    """
    test_broker_isolation:
    Verifies purpose-based topic access on the MQTT broker, using the
    existing reserve/subscribe mechanism.
    - Enabled case: 
      1. A topic is reserved for a specific purpose. 
      2. Two agents are spawned to subscribe to that topic, 
        one with the correct purpose
        and one with an incorrect purpose. 
      3. A message is published to the topic
      4. check that only the agent with the correct purpose receives it.
    - Disabled case: 
      1. the topic is not reserved, so any purpose (e.g. a
      generic/admin one) can be used to subscribe. 
      2. Both agents should receive the published message, showing that without a reservation no purpose restriction is enforced.
    """
    
    #------------------------------------------------------------------------------------------------------------------
    # Enabled case: purpose filtering is active
    #------------------------------------------------------------------------------------------------------------------
    
    # setup topic and purposes for the test
    input_topic = topic_factory("input")
    allowed = purpose_factory("allowed")
    blocked = purpose_factory("blocked")
    
    # 1. Reserve the topic for the allowed purpose
    reserve_topic(input_topic, aip=[allowed])
    
    id_1 = create_agent(
        runOnce=False,
        text="Answer to the incomming message in the simplest way possible ",
        purpose=allowed,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    id_2 = create_agent(
        runOnce=False,
        text="Answer to the incomming message in the simplest way possible ",
        purpose=blocked,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    
    time.sleep(2) 
    # check if agent is there 
    agent1_existis = check_agent_exists(id_1)
    assert agent1_existis, f"Agent 1 with ID {id_1} does not exist."
    agent2_existis = check_agent_exists(id_2)
    assert agent2_existis, f"Agent 2 with ID {id_2} does not exist."
    
    # send a message and check both histories 
    publish_response = publish_message(input_topic, json.dumps("Ping"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
    
    agentHistory_1 = get_agent_history(id_1)
    print(f"Agent 1 history: {agentHistory_1}")
    agentHistory_2 = get_agent_history(id_2)
    print(f"Agent 2 history: {agentHistory_2}")
    
    remaining_timeout = MESSAGE_TIMEOUT
    while len(agentHistory_1) == 0 and remaining_timeout > 0:
        time.sleep(1)
        remaining_timeout -= 1
        agentHistory_1 = get_agent_history(id_1)
    assert len(agentHistory_1) > 0, f" (Enabled) Agent 1 (allowed) did not receive expected result: {agentHistory_1}"
    assert len(agentHistory_2) == 0, f" (Enabled) Agent 2 (blocked) should not have received a result, but got: {agentHistory_2}"
    
    #------------------------------------------------------------------------------------------------------------------
    # Disabled case: purpose filtering is inactive
    #------------------------------------------------------------------------------------------------------------------
    # new topics to avoid interference with the previous test
    input_topic_disabled = topic_factory("input-disabled")
    
    # no reservation
    id_1 = create_agent(
        runOnce=False,
        text="Answer to the incomming message in the simplest way possible ",
        purpose=allowed,
        memoryWindow=5,
        listenTopic=input_topic_disabled,
    )
    id_2 = create_agent(
        runOnce=False,
        text="Answer to the incomming message in the simplest way possible ",
        purpose=allowed,  
        memoryWindow=5,
        listenTopic=input_topic_disabled,
    )
    time.sleep(2) 
    # check if agent is there 
    agent1_existis = check_agent_exists(id_1)
    assert agent1_existis, f"Agent 1 with ID {id_1} does not exist."
    agent2_existis = check_agent_exists(id_2)   
    assert agent2_existis, f"Agent 2 with ID {id_2} does not exist."
    
    # send a message and check both histories 
    publish_response = publish_message(input_topic_disabled, json.dumps("Ping"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
    
    agentHistory_1 = get_agent_history(id_1)
    agentHistory_2 = get_agent_history(id_2)
    
    remaining_timeout = MESSAGE_TIMEOUT
    while (len(agentHistory_1) == 0 or len(agentHistory_2) == 0) and remaining_timeout > 0:
        time.sleep(1)
        remaining_timeout -= 1
        if len(agentHistory_1) == 0:
            agentHistory_1 = get_agent_history(id_1)
        if len(agentHistory_2) == 0:
            agentHistory_2 = get_agent_history(id_2)
    assert len(agentHistory_1) > 0, f"(deactivated) Agent 1 did not receive expected result: {agentHistory_1}"
    assert len(agentHistory_2) > 0, f"(deactivated) Agent 2 did not receive expected result: {agentHistory_2}"
    
#######################################################################################################################
#######################################################################################################################
def test_mcp_isolation(topic_factory, purpose_factory):
    """
    (Email tool has purpose: ![advertisement, external, admin])
    
    test_mcp_isolation:
    Verifies purpose-based access control on MCP tool calls.
    - Enabled case: 
      1. two agents are spawned with the same task, calling the same tool. 
      2. One agent has the purpose required by the tool, the other does not. 
      3. The tool call should only succeed for the agent with the correct purpose.
    - Disabled case: 
      1. both agents are instructed to use a designated universal purpose (e.g. admin) that is always permitted for any
      tool. 
      2. Both agents should be able to successfully call the tool
    """
    
    #------------------------------------------------------------------------------------------------------------------
    # Enabled case: purpose filtering is active
    #------------------------------------------------------------------------------------------------------------------
    
    input_topic = topic_factory("input")
    allowed = "external"  # purpose required by the tool
    not_allowed = "test"  # purpose not allowed by the tool
    wildcard = "admin"  # purpose that is always allowed for any tool
    
    # with purpose
    id_1 = create_agent(
        runOnce=False,
        text=build_tool_call_task("send_email", "external", "Agent1"),
        purpose= allowed,  # purpose required by the tool
        memoryWindow=5,
        listenTopic=input_topic,
    )
    # without purpose
    id_2 = create_agent(
        runOnce=False,
        text=build_tool_call_task("send_email", "test", "Agent2"),
        purpose=not_allowed,  # using a different purpose for each agent to test MCP isolation
        memoryWindow=5,
        listenTopic=input_topic,
    )
    
    time.sleep(2) 
    # check if agent is there 
    agent1_existis = check_agent_exists(id_1)
    assert agent1_existis, f"Agent 1 with ID {id_1} does not exist."
    agent2_existis = check_agent_exists(id_2)
    assert agent2_existis, f"Agent 2 with ID {id_2} does not exist."

    t_before_publish = time.monotonic()
    publish_response = publish_message(input_topic, json.dumps({"text": "Test email."}))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    t_before_listen = time.monotonic()
    toolcall_exists, toolcall_message = toolcall_listen_for_tool_and_word("send_email", "Agent1")
    t_after_listen = time.monotonic()
    
    print(f"gap publish->listen_start: {t_before_listen - t_before_publish:.2f}s")
    print(f"listen duration: {t_after_listen - t_before_listen:.2f}s")
    
    print(f"Tool call message for Agent1: {toolcall_message}")
    assert toolcall_exists, "Expected tool call not found for Agent1"

    toolcall_exists, toolcall_message = toolcall_listen_for_tool_and_word("send_email", "Agent2")
    print(f"Tool call message for Agent2: {toolcall_message}")
    assert not toolcall_exists, "Unexpected tool call found for Agent2"
    
    #------------------------------------------------------------------------------------------------------------------
    # Disabled case: purpose filtering is inactive - both get the same
    #------------------------------------------------------------------------------------------------------------------
    
    input_topic = topic_factory("input-disabled")
    
    # with purpose
    id_1 = create_agent(
        runOnce=False,
        text=build_tool_call_task("send_email", wildcard, "Agent1"),
        purpose= wildcard,  # purpose required by the tool
        memoryWindow=5,
        listenTopic=input_topic,
    )
    # without purpose
    id_2 = create_agent(
        runOnce=False,
        text=build_tool_call_task("send_email", wildcard, "Agent2"),
        purpose=wildcard,  # using a different purpose for each agent to test MCP isolation
        memoryWindow=5,
        listenTopic=input_topic,
    )
    
    time.sleep(2) 
    # check if agent is there 
    agent1_existis = check_agent_exists(id_1)
    assert agent1_existis, f"Agent 1 with ID {id_1} does not exist."
    agent2_existis = check_agent_exists(id_2)
    assert agent2_existis, f"Agent 2 with ID {id_2} does not exist."

    t_before_publish = time.monotonic()
    publish_response = publish_message(input_topic, json.dumps({"text": "Test email."}))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    t_before_listen = time.monotonic()
    results = toolcall_listen_for_multiple("Agent1", "Agent2", timeout=300)
    t_after_listen = time.monotonic()
    
    print(f"gap publish->listen_start: {t_before_listen - t_before_publish:.2f}s")
    print(f"listen duration: {t_after_listen - t_before_listen:.2f}s")
    
    toolcall_exists_1, msg_1 = results["Agent1"]
    toolcall_exists_2, msg_2 = results["Agent2"]
    print(f"Tool call message for Agent1: {msg_1}")
    print(f"Tool call message for Agent2: {msg_2}")
    agent1_history = get_agent_history(id_1)
    agent2_history = get_agent_history(id_2)
    print(f"Agent 1 history: {agent1_history}")
    print(f"Agent 2 history: {agent2_history}")
    assert toolcall_exists_1, "Expected tool call not found for Agent1"
    assert toolcall_exists_2, "Expected tool call not found for Agent2"
    
#######################################################################################################################
#######################################################################################################################
def test_vector_isolation(topic_factory, purpose_factory):
    """
    test_vector_isolation:
    Verifies purpose-based filtering on vector database queries, driven
    through real agents calling the search_knowledge_base MCP tool (rather
    than querying the RAG service directly), to introduce realistic load
    and exercise the full MCP -> RAG path the way a real user would.

    - Enabled case:
      1. Subsidy documents already exist in the 'subsidies' collection,
         each sharing the common baseline purpose 'admin' but also carrying
         a distinct additional purpose (its state) that the other does not
         have — e.g. one tagged 'Bayern', the other 'Berlin'.
      2. One agent is spawned to search the knowledge base using the
         'Bayern' purpose, and publish the returned document names.
      3. Only Bayern-scoped documents should be present in the result;
         Berlin-scoped documents should not appear.
    - Disabled case:
      1. An agent is spawned to search using the shared, universally
         allowed purpose 'admin'.
      2. Documents from both purpose groups should be present in the
         result, showing that the common baseline purpose bypasses the
         more specific isolation boundary.
    """

    ############
    # Enabled case: purpose filtering is active
    ############

    wildcard_purpose = "admin"  
    enabled_purpose = "Bayern"
    excluded_purpose = "Berlin"
    result_topic_enabled = topic_factory("result-vector-enabled")

    id_1 = create_agent(
        runOnce=False,
        text=build_vector_query_task( wildcard_purpose, enabled_purpose, result_topic_enabled),
        purpose=wildcard_purpose,  
        memoryWindow=5,
        listenTopic=topic_factory("input-vector-enabled"),
    )

    time.sleep(2)
    agent1_exists = check_agent_exists(id_1)
    assert agent1_exists, f"Agent 1 with ID {id_1} does not exist."

    publish_response = publish_message(topic_factory("input-vector-enabled"), json.dumps("Search"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    result_enabled = listen_to_a_mqtt_topic(result_topic_enabled, timeout=300)
    print(f"(Enabled) Result for purpose '{enabled_purpose}': {result_enabled}")

    assert result_enabled is not None, f"(Enabled) No result received for purpose '{enabled_purpose}'"
    assert excluded_purpose not in result_enabled, (
        f"(Enabled) A '{excluded_purpose}'-scoped document leaked into a "
        f"'{enabled_purpose}' query result: {result_enabled}"
    )

    ############
    # Disabled case: purpose filtering is inactive (shared baseline purpose)
    ############

    wildcard_purpose = "admin"
    result_topic_disabled = topic_factory("result-vector-disabled")

    id_2 = create_agent(
        runOnce=False,
        text=build_vector_query_task(wildcard_purpose, wildcard_purpose, result_topic_disabled),
        purpose=wildcard_purpose,
        memoryWindow=5,
        listenTopic=topic_factory("input-vector-disabled"),
    )

    time.sleep(2)
    agent2_exists = check_agent_exists(id_2)
    assert agent2_exists, f"Agent 2 with ID {id_2} does not exist."

    publish_response = publish_message(topic_factory("input-vector-disabled"), json.dumps("Search"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    result_disabled = listen_to_a_mqtt_topic(result_topic_disabled, timeout=300)
    print(f"(Disabled) Result for purpose '{wildcard_purpose}': {result_disabled}")

    assert result_disabled is not None, f"(Disabled) No result received for purpose '{wildcard_purpose}'"
