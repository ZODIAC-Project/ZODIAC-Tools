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
import threading
import pytest
import time as time
import requests
import threading
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
    results = toolcall_listen_for_multiple("Agent1", "Agent2")
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
      1. Documents in the 'subsidies' collection carry the baseline purpose
         'subsidy/discovery', not 'subsidy/eligibility' (that purpose is
         only used by other collections, e.g. 'customers', 'state').
      2. One agent is spawned to search 'subsidies' using the purpose
         'subsidy/eligibility' — a purpose the subsidies documents don't
         carry.
      3. No subsidies documents should be returned, showing that a
         mismatched purpose is correctly filtered out.
    - Disabled case:
      1. An agent is spawned to search 'subsidies' using the shared,
         universally allowed purpose 'admin'.
      2. Subsidies documents should be present in the result, showing that
         the common baseline purpose bypasses the more specific isolation
         boundary.
    """

    # A representative sample of document names known to exist in the
    # 'subsidies' collection.
    SUBSIDY_DOC_NAMES = {
        "Bayerisches Handwerk Erweiterungsprogramm",
        "Ingolstadt Gewerbeförderung Kleinstunternehmen",
        "Bayern Gastgewerbe Modernisierungshilfe",
        "Bundesweites Ausbildungsförderungsprogramm Handwerk",
        "Optische Technologien & Lasertechnik BW",
    }

    def validate_search_and_get_publish(
        messages: list,
        session_id: str,
        expected_purpose: str,
        result_topic: str,
    ) -> str:
        search_calls = [m for m in messages if m.get("tool") == "search_knowledge_base"]
        assert search_calls, f"No search_knowledge_base call found for {session_id}. Captured: {messages}"
        publish_calls = [
            m for m in messages
            if m.get("tool") == "publish"
            and m.get("parameters", {}).get("topic") == result_topic
        ]

        assert len(search_calls) == 1, (
            f"Expected exactly one search_knowledge_base call from session {session_id}, "
            f"found {len(search_calls)}: {[c['parameters'] for c in search_calls]}"
        )
        actual_purpose = search_calls[0].get("parameters", {}).get("purpose")
        assert actual_purpose == expected_purpose, (
            f"search_knowledge_base called with purpose '{actual_purpose}', expected '{expected_purpose}'"
        )

        assert publish_calls, f"No publish call found for {result_topic}. Captured: {messages}"
        return " ".join(c["parameters"]["message"] for c in publish_calls)


    ############
    # Enabled case: purpose filtering is active
    ############
    print(f"Enabled case: purpose filtering is active")

    wildcard_purpose = "admin"

    enabled_purpose = "subsidy/eligibility"  

    topic = topic_factory("input-vector-enabled")
    result_topic_enabled = topic_factory("result-vector-enabled")

    id_1 = create_agent(
        runOnce=False,
        text=build_vector_query_task(enabled_purpose, result_topic_enabled),
        purpose=wildcard_purpose,
        memoryWindow=5,
        listenTopic=topic,
    )
    time.sleep(5)  # wait for agent to be ready
    agent1_exists = check_agent_exists(id_1)
    assert agent1_exists, f"Agent 1 with ID {id_1} does not exist."

    collected = {}
    def collect_enabled():
        collected["enabled"] = collect_tool_calls(session_id=id_1)

    t = threading.Thread(target=collect_enabled)
    t.start()
    time.sleep(1)

    print(f"Publishing to topic '{topic}' to trigger search for purpose '{enabled_purpose}'")

    publish_response = publish_message(topic, json.dumps("Search"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    t.join()
    print(f"Collected messages for purpose '{enabled_purpose}': {collected['enabled']}")
    result_enabled = validate_search_and_get_publish(
        collected["enabled"],
        session_id=id_1,
        expected_purpose=enabled_purpose,
        result_topic=result_topic_enabled,
    )
    print(f"(Enabled) Result for purpose '{enabled_purpose}': {result_enabled}")

    found_subsidies = {name for name in SUBSIDY_DOC_NAMES if name in result_enabled}
    assert not found_subsidies, (
        f"(Enabled) Subsidies document(s) leaked into a '{enabled_purpose}' query "
        f"they should not match: {found_subsidies}"
    )
    ############
    # Disabled case: purpose filtering is inactive (shared baseline purpose)
    ############
    print(f"Disabled case: purpose filtering is inactive (shared baseline purpose)")

    topic_diabled = topic_factory("input-vector-disabled")
    wildcard_purpose = "admin"
    result_topic_disabled = topic_factory("result-vector-disabled")

    id_2 = create_agent(
        runOnce=False,
        text=build_vector_query_task(wildcard_purpose, result_topic_disabled),
        purpose=wildcard_purpose,
        memoryWindow=5,
        listenTopic=topic_diabled,
    )

    time.sleep(5)
    agent2_exists = check_agent_exists(id_2)
    assert agent2_exists, f"Agent 2 with ID {id_2} does not exist."

    def collect_disabled():
        collected["disabled"] = collect_tool_calls(session_id=id_2)

    t2 = threading.Thread(target=collect_disabled)
    t2.start()
    time.sleep(1)

    publish_response = publish_message(topic_diabled, json.dumps("Search"))
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    t2.join()
    result_disabled = validate_search_and_get_publish(
        collected["disabled"],
        session_id=id_2,
        expected_purpose=wildcard_purpose,
        result_topic=result_topic_disabled,
    )
    print(f"(Disabled) Result for purpose '{wildcard_purpose}': {result_disabled}")

    found_subsidies_disabled = {name for name in SUBSIDY_DOC_NAMES if name in result_disabled}
    assert found_subsidies_disabled, (
        f"(Disabled) Expected subsidies document(s) for purpose '{wildcard_purpose}', found none"
    )
