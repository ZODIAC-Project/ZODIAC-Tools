"""Start with: 
    broker only: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled
    broker + mcp: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled
    broker + vector: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --vector-enabled
    broker + mcp + vector: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled
    broker + mcp + vector + amount of messages: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=5
"""

import json
from random import randint
from random import choice
import pytest
import time
import requests
from ...helper import *
from ..shared.prompts import *

import logging
logging.disable(logging.CRITICAL)


def _log(branch: str, message: str) -> None:
    """Single formatting point for all debug output so every line makes clear
    which branch/scenario it came from."""
    print(f"[{branch}] {message}")

def disable_purpose_awareness(agent_id: str) -> None:
    """Turn of purpose awareness in the mcp-client by calling its corresponding endpoint for a session. """
    try: 
        response = requests.post(
            f"{MCP_URL}/disable-purpose",
            json={"session_id": agent_id},
        )
        response.raise_for_status()
        result = response.json()
        assert result.get("status") == "success", (
            f"Failed to disable purpose awareness for agent {agent_id}: {result}"
        )
    except requests.RequestException as e:
        print(f"Error occurred while disabling purpose awareness for agent {agent_id}: {e}")

def create_agents(mcp: bool, 
                vector: bool, 
                input_topic: str, 
                midway_topic: str, 
                issue_topic: str, 
                allowed: str, 
                wildcard_purpose: str, 
                agent_purpose_1: str = "query", 
                agent_purpose_2: str = "advertisement", 
                vector_purpose: str = "subsidy") -> tuple[str, str]:
    # (RAG tool has purpose: ![query, knowledge, search, admin])
    # Agents always get their real (correct or intentionally wrong) purpose.
    # When mcp=False, purpose-awareness is explicitly disabled afterwards via
    # disable_purpose_awareness()
    agent_id_1 = create_agent(
        runOnce=False,
        text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose=vector_purpose),
        purpose=agent_purpose_1,
        memoryWindow=5,
        listenTopic=input_topic,
    )
    if not mcp:
        disable_purpose_awareness(agent_id_1)
        
    set_knowledgebase_access(agent_id_1, unrestricted=not vector)

    # (Email tool has purpose: ![advertisement, external, admin])
    agent_id_2 = create_agent(
        runOnce=False,
        text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
        purpose=agent_purpose_2,
        memoryWindow=5,
        listenTopic=midway_topic,
    )
    if not mcp:
        disable_purpose_awareness(agent_id_2)
        
    return agent_id_1, agent_id_2

def _cleanup_agents(branch: str, agent_id_1: str | None, agent_id_2: str | None) -> None:
    _log(branch, f"Cleaning up agents (agent_id_1={agent_id_1}, agent_id_2={agent_id_2})...")
    if agent_id_1:
        delete_agent(agent_id_1)
        _log(branch, f"Deleted agent 1: {agent_id_1}")
    if agent_id_2:
        delete_agent(agent_id_2)
        _log(branch, f"Deleted agent 2: {agent_id_2}")


def _select_workload_branch(forced_branch: str | None, randomness: bool) -> tuple[str, bool, bool, bool]:
    if forced_branch:
        branch_name = forced_branch
    elif randomness:
        branch_name = choice([
            "no-fault", "passthrough",
            "broker", "broker-success",
            "mcp", "mcp-success",
            "vector", "vector-success",
        ])
    else:
        branch_name = "passthrough"

    # no-fault picks its own random PBAC layer combo separately (see
    # _select_no_fault_pbac_layers); broker/mcp/vector here are placeholders.
    required_flags = {
        "broker": (True, False, False),
        "broker-success": (True, False, False),
        "mcp": (False, True, False),
        "mcp-success": (False, True, False),
        "vector": (False, False, True),
        "vector-success": (False, False, True),
        "passthrough": (False, False, False),
        "no-fault": (False, False, False),
    }
    resolved_broker, resolved_mcp, resolved_vector = required_flags[branch_name]
    return branch_name, resolved_broker, resolved_mcp, resolved_vector

def _select_no_fault_pbac_layers() -> tuple[bool, bool, bool]:
    return choice([
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ])


def workflow_no_fault_scenario(input_topic,
                               allowed, 
                               midway_topic, 
                               issue_topic, 
                               wildcard_purpose, 
                               Random_Number, 
                               broker, 
                               mcp, 
                               vector,
                               amount_messages,
                               customer: dict,
                               iteration=1,
                               total_iterations=1):
    """This Branch is used when the random number is even.
        Trigger this branch manually with the --randomness flag set to False.
        uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=1 --randomness=False
    """
    branch = "NO-FAULT"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: Broker={broker}, MCP={mcp}, Vector={vector}, Amount of Messages={amount_messages}, Random Number={Random_Number}")
    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        if broker == True:
            _log(branch, f"Broker enabled. Reserving topics: input={input_topic}, midway={midway_topic}")
            reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement", "admin"])
            reserve_topic(midway_topic, aip=[allowed, wildcard_purpose , "advertisement", "admin"])
            _log(branch, "Topic reservation complete.")
        else:
            _log(branch, "Broker is disabled. No purpose reservation was made.")
        #create the agents once 
        _log(branch, "Creating Agent 1 and Agent 2...")
        agent_id_1, agent_id_2 = create_agents(mcp, vector, input_topic, midway_topic, issue_topic, allowed, wildcard_purpose)
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")
        # check they are healthy 
        _log(branch, "Checking if both agents exist and are healthy...")
        time.sleep(2)
        agent1_existis = check_agent_exists(agent_id_1)
        assert agent1_existis, f"---> Agent 1 with ID {agent_id_1} does not exist."
        time.sleep(2)
        agent2_existis = check_agent_exists(agent_id_2)
        assert agent2_existis, f"---> Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy. Continue with the test scenario.")
        # Publish Message 
        _log(branch, f"Publishing message to input topic: {input_topic}. This message will be processed by Agent 1.")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
        _log(branch, f"Message published successfully: {publish_response}")
        
        _log(branch, "Starting test validation. This can take some time since we have to wait for the turn to complete.")
        
        # Agent 1 got Message?
        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        # Agent 2 got a Message? Wait for MESSAGE_TIMEOUT seconds 
        _log(branch, f"Waiting for Agent 2 (id={agent_id_2}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_2 = get_agent_history(agent_id_2, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_2) > 0, f" No message was received by Agent 2. Agent History: {agent_history_2}"
        _log(branch, f"Agent 2 received a message. Agent History: {agent_history_2}")

        # Agent 2 called the Email Tool for its own session?
        _log(branch, f"Waiting for Agent 2 (session={agent_id_2}) to call the send_email tool (timeout={MESSAGE_TIMEOUT}s)...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, (
            f"Expected send_email to be called. No tool calls found. "
            f"Captured messages: {email_calls}"
        )
        assert "[Name]" not in str(email_calls), (
            f"Email enthält Platzhalter statt echter Kundendaten — "
            f"kein Match unter Top-10 RAG-Ergebnissen: {email_calls}"
        )
        
        _log(branch, f"Agent 2 called the Email Tool in session {agent_id_2}. Tool Call Message(s): {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed. All expected messages and tool calls were observed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_broker_fault_scenario(input_topic, 
                                   midway_topic, 
                                   issue_topic, 
                                   customer,
                                   allowed, 
                                   wildcard_purpose, 
                                   mcp, 
                                   vector, 
                                   iteration=1, 
                                   total_iterations=1):
    """Fault injection on the broker level: agent 1 subscribes with the wrong purpose,
    so the published message should never arrive at it.
    Trigger this branch with the command:
    uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=1 --randomness=True
    """
    branch = "BROKER-FAULT"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: MCP={mcp}, Vector={vector}. Expecting Agent 1 to NOT receive the message (wrong subscription purpose).")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, f"Reserving input topic: {input_topic}")
        reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement"])

        _log(branch, "Creating Agent 1 (purpose=wrong_purpose) and Agent 2 (purpose=advertisement)...")
        agent_id_1, agent_id_2 = create_agents(
            mcp,
            vector,
            input_topic,
            midway_topic,
            issue_topic,
            allowed,
            wildcard_purpose,
            agent_purpose_1="wrong_purpose",
            agent_purpose_2="advertisement",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        time.sleep(2)
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic}")
        payload = make_trigger_message(customer)
        publish_message(input_topic, json.dumps(payload))
        _log(branch, "Message published.")

        _log(branch, f"Waiting to confirm Agent 1 (id={agent_id_1}) receives NO message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) == 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received NO message. This is expected. Agent History: {agent_history_1}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_mcp_fault_scenario(input_topic, 
                                midway_topic, 
                                issue_topic, 
                                allowed, 
                                wildcard_purpose, 
                                vector, 
                                customer: dict,
                                iteration=1, 
                                total_iterations=1):
    """Fault injection on the MCP level: agent 1 is created with purposes that are not
    allowed for the send_email tool call, so the tool call should not be made.
    Trigger this with the command:
    uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --mcp-enabled --vector-enabled --amount-messages=1 --randomness=True
    """
    branch = "MCP-FAULT"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: Vector={vector}. Expecting send_email to NOT be called (agents created with disallowed purposes).")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, "Creating Agent 1 (purpose=weather-forcasting) and Agent 2 (purpose=automatic-driving)...")
        agent_id_1, agent_id_2 = create_agents(
            True,
            vector,
            input_topic,
            midway_topic,
            issue_topic,
            allowed,
            wildcard_purpose,
            agent_purpose_1="weather-forcasting",
            agent_purpose_2="automatic-driving",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic}")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that send_email was NOT called by Agent1...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert not email_calls, f"Tool call was made with wrong purpose. This is unexpected. Tool Call Message: {email_calls}"
        _log(branch, f"send_email was correctly not called. This is expected. Tool Call Message: {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_vector_fault_scenario(input_topic, 
                                   midway_topic, 
                                   issue_topic, 
                                   allowed, 
                                   wildcard_purpose, 
                                   mcp, 
                                   vector, 
                                   customer: dict,
                                   iteration=1, 
                                   total_iterations=1):
    branch = "VECTOR-FAULT"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: MCP={mcp}, Vector={vector}. Expecting search_knowledge_base to be denied for state=Leipzig.")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, "Creating Agent 1 and Agent 2 (both using wildcard purpose)...")
        agent_id_1, agent_id_2 = create_agents(
            mcp,
            vector,
            input_topic,
            midway_topic,
            issue_topic=issue_topic,
            allowed = wildcard_purpose,
            wildcard_purpose = wildcard_purpose,
            agent_purpose_1=wildcard_purpose,
            agent_purpose_2=wildcard_purpose,
            vector_purpose="Leipzig",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic} (state=Leipzig, no matching knowledge expected)")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that search_knowledge_base was called...")
        rag_calls = wait_for_tool_call("search_knowledge_base", timeout=MESSAGE_TIMEOUT)
        assert rag_calls, f"Expected search_knowledge_base to be called. Tool Call Message: {rag_calls}"
        _log(branch, f"search_knowledge_base was called. Tool Call Message: {rag_calls}")

        _log(branch, f"Waiting for ACCESS_DENIED_PURPOSE_ISSUE on issue topic: {issue_topic} (timeout={MESSAGE_TIMEOUT}s)...")
        issue_message = listen_to_a_mqtt_topic(issue_topic, timeout=MESSAGE_TIMEOUT)
        assert issue_message is not None, f"Expected an error message on {issue_topic}, but none was received."
        assert "ACCESS_DENIED_PURPOSE_ISSUE" in issue_message, (
            f"Expected ACCESS_DENIED_PURPOSE_ISSUE on {issue_topic}, but got: {issue_message}"
        )
        _log(branch, f"Received expected ACCESS_DENIED_PURPOSE_ISSUE on {issue_topic}: {issue_message}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)

### Success scenarios
def workflow_broker_success_scenario(input_topic,
                                     midway_topic,
                                     issue_topic,
                                     customer,
                                     allowed,
                                     wildcard_purpose,
                                     vector,
                                     iteration=1,
                                     total_iterations=1):
    """Gegenstück zu workflow_broker_fault_scenario: Agent 1 subscribt mit
    einem im aip enthaltenen (korrekten) Purpose -> die Nachricht soll
    ankommen und der volle Flow bis send_email durchlaufen.
    Trigger manuell mit:
    uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-success-enabled --amount-messages=1 --randomness=True
    """
    branch = "BROKER-SUCCESS"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: Vector={vector}. Expecting Agent 1 to RECEIVE the message (correct subscription purpose).")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, f"Reserving input topic: {input_topic}")
        reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement"])
        reserve_topic(midway_topic, aip=[allowed, wildcard_purpose, "advertisement", "admin"])

        _log(branch, "Creating Agent 1 (purpose=query) and Agent 2 (purpose=advertisement), both mcp=True...")
        agent_id_1, agent_id_2 = create_agents(
            mcp=True,
            vector=vector,
            input_topic=input_topic,
            midway_topic=midway_topic,
            issue_topic=issue_topic,
            allowed=allowed,
            wildcard_purpose=wildcard_purpose,
            agent_purpose_1="query",
            agent_purpose_2="advertisement",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        time.sleep(2)
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic}")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
        _log(branch, f"Message published successfully: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. This is expected. Agent History: {agent_history_1}")

        _log(branch, f"Waiting for Agent 2 (id={agent_id_2}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_2 = get_agent_history(agent_id_2, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_2) > 0, f" No message was received by Agent 2. Agent History: {agent_history_2}"
        _log(branch, f"Agent 2 received a message. Agent History: {agent_history_2}")

        _log(branch, "Checking that send_email was called...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, f"Expected send_email to be called. Captured messages: {email_calls}"
        assert "[Name]" not in str(email_calls), (
            f"Email enthält Platzhalter statt echter Kundendaten: {email_calls}"
        )
        _log(branch, f"send_email was called as expected. Tool Call Message(s): {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_mcp_success_scenario(input_topic,
                                  midway_topic,
                                  issue_topic,
                                  allowed,
                                  wildcard_purpose,
                                  vector,
                                  customer: dict,
                                  iteration=1,
                                  total_iterations=1):
    """Gegenstück zu workflow_mcp_fault_scenario: Agenten nutzen ihren
    korrekten Purpose (mcp=True, purpose-awareness bleibt an) -> send_email
    soll aufgerufen werden.
    Trigger manuell mit:
    uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --mcp-success-enabled --amount-messages=1 --randomness=True
    """
    branch = "MCP-SUCCESS"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: Vector={vector}. Expecting send_email to BE called (agents created with allowed purposes, purpose-awareness on).")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, "Creating Agent 1 (purpose=query) and Agent 2 (purpose=advertisement), mcp=True...")
        agent_id_1, agent_id_2 = create_agents(
            mcp=True,
            vector=vector,
            input_topic=input_topic,
            midway_topic=midway_topic,
            issue_topic=issue_topic,
            allowed=allowed,
            wildcard_purpose=wildcard_purpose,
            agent_purpose_1="query",
            agent_purpose_2="advertisement",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic}")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that send_email WAS called by Agent2...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, f"Expected send_email to be called with correct purpose. Tool Call Message: {email_calls}"
        _log(branch, f"send_email was correctly called. This is expected. Tool Call Message: {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_vector_success_scenario(input_topic,
                                     midway_topic,
                                     issue_topic,
                                     allowed,
                                     wildcard_purpose,
                                     mcp,
                                     customer: dict,
                                     iteration=1,
                                     total_iterations=1):
    """Gegenstück zu workflow_vector_fault_scenario: vector_purpose passt zu
    den echten Daten (Default "subsidy" statt "Leipzig") -> RAG liefert
    Treffer, kein ACCESS_DENIED_PURPOSE_ISSUE auf issue_topic.
    Trigger manuell mit:
    uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --vector-success-enabled --amount-messages=1 --randomness=True
    """
    branch = "VECTOR-SUCCESS"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: MCP={mcp}. Expecting search_knowledge_base to succeed for the correct vector_purpose.")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, "Creating Agent 1 and Agent 2 (both using wildcard purpose for broker, vector=True)...")
        agent_id_1, agent_id_2 = create_agents(
            mcp=mcp,
            vector=True,
            input_topic=input_topic,
            midway_topic=midway_topic,
            issue_topic=issue_topic,
            allowed=wildcard_purpose,
            wildcard_purpose=wildcard_purpose,
            agent_purpose_1=wildcard_purpose,
            agent_purpose_2=wildcard_purpose,
            vector_purpose="subsidy",
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic} (vector_purpose=subsidy, matching knowledge expected)")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that search_knowledge_base was called...")
        rag_calls = wait_for_tool_call("search_knowledge_base", timeout=MESSAGE_TIMEOUT)
        assert rag_calls, f"Expected search_knowledge_base to be called. Tool Call Message: {rag_calls}"
        _log(branch, f"search_knowledge_base was called. Tool Call Message: {rag_calls}")

        _log(branch, "Checking that send_email was called with real customer data (no ACCESS_DENIED)...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, f"Expected send_email to be called. Captured messages: {email_calls}"
        assert "[Name]" not in str(email_calls), (
            f"Email enthält Platzhalter statt echter Kundendaten: {email_calls}"
        )
        _log(branch, f"send_email was called with real data as expected: {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_passthrough_scenario(input_topic, 
                                  midway_topic, 
                                  issue_topic, 
                                  customer: dict, 
                                  allowed, 
                                  wildcard_purpose, 
                                  mcp, 
                                  vector, 
                                  iteration=1, 
                                  total_iterations=1):
    branch = "PASSTHROUGH"
    print("")
    print("--------------------------------------------------------------")
    _log(branch, f"Starting iteration {iteration}/{total_iterations}")
    _log(branch, f"Config: MCP={mcp}, Vector={vector}. All PBAC layers disabled — expecting the full flow to succeed.")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        _log(branch, "Creating Agent 1 and Agent 2 (both using wildcard purpose)...")
        agent_id_1, agent_id_2 = create_agents(
            mcp,
            vector,
            input_topic,
            midway_topic,
            issue_topic=issue_topic,
            allowed=wildcard_purpose,
            wildcard_purpose=wildcard_purpose,
            agent_purpose_1=wildcard_purpose,
            agent_purpose_2=wildcard_purpose,
        )
        _log(branch, f"Agents created: agent_id_1={agent_id_1}, agent_id_2={agent_id_2}")

        _log(branch, "Checking if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."
        _log(branch, "Both agents exist and are healthy.")

        _log(branch, f"Publishing message to input topic: {input_topic} (state=admin, wildcard purpose)")
        payload = make_trigger_message(customer)
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that send_email was called...")
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, f"Expected send_email to be called. Tool Call Message: {email_calls}"
        assert "[Name]" not in str(email_calls), (
            f"Email enthält Platzhalter statt echter Kundendaten. Tool Call Message: {email_calls}"
        )
        _log(branch, f"send_email was called as expected. Tool Call Message: {email_calls}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)



def test_workload_purpose_isolation_scenario(request, 
                                             topic_factory, 
                                             purpose_factory):
    branch = "SETUP"
    forced_branch = request.config.getoption("--branch")
    amount_messages = request.config.getoption("--amount-messages")
    randomness = request.config.getoption("--randomness").lower() == "true"

    input_topic = topic_factory("input")
    midway_topic = topic_factory("midway")
    issue_topic = topic_factory("issue")
    allowed = purpose_factory("allowed")
    wildcard_purpose = "admin"

    customer = load_customers()

    print("")
    print("================================================================")
    _log(branch, f"Forced Branch={forced_branch}, Amount of Messages={amount_messages}, Randomness={randomness}")
    _log(branch, f"Topics: input={input_topic}, midway={midway_topic}, issue={issue_topic}")

    selected_branch, broker, mcp, vector = _select_workload_branch(forced_branch, randomness)
    _log(branch, f"Selected branch: {selected_branch} (Broker={broker}, MCP={mcp}, Vector={vector})")

    if selected_branch == "no-fault":
        broker, mcp, vector = _select_no_fault_pbac_layers()
        _log(branch, f"Selected NO-FAULT branch with PBAC config: Broker={broker}, MCP={mcp}, Vector={vector}")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_no_fault_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, Random_Number=randint(1, 100),
                broker=broker, mcp=mcp, vector=vector, amount_messages=amount_messages,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
        return

    if selected_branch == "broker":
        _log(branch, f"Selected BROKER-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_broker_fault_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, mcp=mcp, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    elif selected_branch == "broker-success":
        _log(branch, f"Selected BROKER-SUCCESS branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_broker_success_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    elif selected_branch == "mcp":
        _log(branch, f"Selected MCP-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_mcp_fault_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    elif selected_branch == "mcp-success":
        _log(branch, f"Selected MCP-SUCCESS branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_mcp_success_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    elif selected_branch == "vector":
        _log(branch, f"Selected VECTOR-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_vector_fault_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, mcp=mcp, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    elif selected_branch == "vector-success":
        _log(branch, f"Selected VECTOR-SUCCESS branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_vector_success_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=allowed, wildcard_purpose=wildcard_purpose, mcp=mcp,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )
    else:
        _log(branch, f"Selected PASSTHROUGH branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            expected_customer = pick_distinctive_customer(customer)
            workflow_passthrough_scenario(
                input_topic=input_topic, midway_topic=midway_topic, issue_topic=issue_topic,
                allowed=wildcard_purpose, wildcard_purpose=wildcard_purpose, mcp=mcp, vector=vector,
                iteration=i + 1, total_iterations=amount_messages, customer=expected_customer
            )