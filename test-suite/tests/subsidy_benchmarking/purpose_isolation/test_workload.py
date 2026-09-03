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


def create_agents(mcp: bool, vector: bool, input_topic: str, midway_topic: str, issue_topic: str, allowed: str, wildcard_purpose: str, agent_purpose_1: str = "query", agent_purpose_2: str = "advertisement", vector_purpose: str = "subsidy/eligibility") -> tuple[str, str]:
    # (RAG tool has purpose: ![query, knowledge, search, admin])
    # Do we want to use real purposes for the mcp tool calls?
    # Yes we want 
    if mcp == True:
        # Do we want to use the state of the incomming message as purpose for the RAG Tool Call?
        # Yes we want
        if vector == True:
            agent_id_1 = create_agent(
                runOnce=False,
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose=vector_purpose),
                purpose=agent_purpose_1,
                memoryWindow=5,
                listenTopic=input_topic,
            )
        # No we dont 
        else:
            agent_id_1 = create_agent(
                runOnce=False,
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose= "admin"),
                purpose=agent_purpose_1,
                memoryWindow=5,
                listenTopic=input_topic,
            )
    # No we dont 
    else:
        if vector == True:
            agent_id_1 = create_agent(
                runOnce=False,
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose=vector_purpose),
                purpose=wildcard_purpose,
                memoryWindow=5,
                listenTopic=input_topic,
            )
        else:
            agent_id_1 = create_agent(
                runOnce=False,
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose= "admin"),
                purpose=wildcard_purpose,
                memoryWindow=5,
                listenTopic=input_topic,
            )

    # (Email tool has purpose: ![advertisement, external, admin])
    # Do we want to use real purposes for the mcp tool calls?
    # Yes we want
    if mcp == True:
        agent_id_2 = create_agent(
            runOnce=False,
            text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
            purpose=agent_purpose_2,
            memoryWindow=5,
            listenTopic=midway_topic,
        )
    else:
        agent_id_2 = create_agent(
            runOnce=False,
            text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
            purpose=wildcard_purpose,
            memoryWindow=5,
            listenTopic=midway_topic,
        ) 
    return agent_id_1, agent_id_2


def _cleanup_agents(branch: str, agent_id_1: str | None, agent_id_2: str | None) -> None:
    _log(branch, f"Cleaning up agents (agent_id_1={agent_id_1}, agent_id_2={agent_id_2})...")
    if agent_id_1:
        delete_agent(agent_id_1)
        _log(branch, f"Deleted agent 1: {agent_id_1}")
    if agent_id_2:
        delete_agent(agent_id_2)
        _log(branch, f"Deleted agent 2: {agent_id_2}")


def _select_workload_branch(broker: bool, mcp: bool, vector: bool, randomness: bool) -> tuple[str, bool, bool, bool]:
    """Return the branch to run AND the broker/mcp/vector flags that branch
    needs in order for create_agents() to actually apply its fault-injection
    purposes. Picking a branch name alone is not enough: create_agents()
    only honors agent_purpose_1 for Agent 1 when mcp=True, and only honors
    vector_purpose when vector=True. If those don't line up with the chosen
    branch, the fault never gets applied and the branch's assertions either
    fail (message arrives when it shouldn't) or hang until MESSAGE_TIMEOUT
    (expected denial never happens).
    """
    explicit_branches = [
        branch_name
        for branch_name, enabled in (
            ("broker", broker),
            ("mcp", mcp),
            ("vector", vector),
        )
        if enabled
    ]
    if explicit_branches:
        branch_name = explicit_branches[0]
    elif randomness:
        branch_name = choice(["no-fault", "broker", "mcp", "vector", "passthrough"])
    else:
        branch_name = "passthrough"

    # Flags required for each branch's fault injection to actually take effect.
    required_flags = {
        "broker": (True, True, vector),        # needs mcp=True so agent_purpose_1 ("wrong_purpose") is honored
        "mcp": (False, True, vector),           # workflow_mcp_fault_scenario forces mcp=True itself either way
        "vector": (False, mcp, True),           # needs vector=True so vector_purpose ("Leipzig") is honored
        "passthrough": (False, False, False),   # needs all PBAC layers off
        "no-fault": (broker, mcp, vector),      # actual flags picked separately by _select_no_fault_pbac_layers
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
        payload = make_trigger_message()
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
            f"Agent 2 did not call the Email Tool in its own session. "
            f"Captured messages: {email_calls}. Agent_id_2: {agent_id_2}"
        )
        _log(branch, f"Agent 2 called the Email Tool in session {agent_id_2}. Tool Call Message(s): {email_calls}")

        _log(branch, f"All test validation asserts passed. Iteration {iteration}/{total_iterations} was successful.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_broker_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector, iteration=1, total_iterations=1):
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
        payload = make_trigger_message()
        publish_message(input_topic, json.dumps(payload))
        _log(branch, "Message published.")

        _log(branch, f"Waiting to confirm Agent 1 (id={agent_id_1}) receives NO message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) == 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received NO message. This is expected. Agent History: {agent_history_1}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_mcp_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, vector, iteration=1, total_iterations=1):
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
        payload = make_trigger_message()
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that send_email was NOT called by Agent1...")
        toolcall_exists, toolcall_message = toolcall_listen_for_tool_and_word("send_email", "Agent1")
        assert not toolcall_exists, f"Tool call was made with wrong purpose. This is unexpected. Tool Call Message: {toolcall_message}"
        _log(branch, f"send_email was correctly not called. This is expected. Tool Call Message: {toolcall_message}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)


def workflow_vector_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector, iteration=1, total_iterations=1):
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
        payload = make_trigger_message()
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that search_knowledge_base was called...")
        toolcall_exists, toolcall_message = toolcall_listen_for_tool("search_knowledge_base")
        assert toolcall_exists, f"Expected search_knowledge_base to be called. Tool Call Message: {toolcall_message}"
        _log(branch, f"search_knowledge_base was called. Tool Call Message: {toolcall_message}")

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


def workflow_passthrough_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector, iteration=1, total_iterations=1):
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
        payload = make_trigger_message()
        publish_response = publish_message(input_topic, json.dumps(payload))
        _log(branch, f"Message published: {publish_response}")

        _log(branch, f"Waiting for Agent 1 (id={agent_id_1}) to receive the message (timeout={MESSAGE_TIMEOUT}s)...")
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        _log(branch, f"Agent 1 received a message. Agent History: {agent_history_1}")

        _log(branch, "Checking that send_email was called...")
        toolcall_exists, toolcall_message = toolcall_listen_for_tool("send_email")
        assert toolcall_exists, f"Expected send_email to be called. Tool Call Message: {toolcall_message}"
        _log(branch, f"send_email was called as expected. Tool Call Message: {toolcall_message}")
        _log(branch, f"Iteration {iteration}/{total_iterations} passed.")
    finally:
        _cleanup_agents(branch, agent_id_1, agent_id_2)



def test_workload_purpose_isolation_scenario(request, topic_factory, purpose_factory):
    branch = "SETUP"
    broker_enabled = request.config.getoption("--broker-enabled")
    mcp_enabled = request.config.getoption("--mcp-enabled")
    vector_enabled = request.config.getoption("--vector-enabled")
    amount_messages = request.config.getoption("--amount-messages")
    randomness = request.config.getoption("--randomness").lower() == "true"

    # Broker on/of, MCP on/off, Vector on/off
    broker = broker_enabled
    mcp = mcp_enabled
    vector = vector_enabled

    amount_messages = amount_messages
    
    input_topic = topic_factory("input")
    midway_topic = topic_factory("midway")
    issue_topic = topic_factory("issue")
    # purposes for broker
    allowed = purpose_factory("allowed")
    wildcard_purpose = "admin"

    print("")
    print("================================================================")
    _log(branch, f"Broker={broker}, MCP={mcp}, Vector={vector}, Amount of Messages={amount_messages}, Randomness={randomness}")
    _log(branch, f"Topics: input={input_topic}, midway={midway_topic}, issue={issue_topic}")

    # Generate Random number X per message.
    #   X % 2 == 0 --> no fault 
    #   X % 2 == 1 --> fault injected 
    if randomness == False:
        Random_Number = 2  # Set to even number for deterministic behavior
        _log(branch, f"Randomness disabled. Using deterministic Random Number: {Random_Number}")
        _log(branch, f"Entering NO-FAULT branch for {amount_messages} iteration(s).")

        for i in range(amount_messages):
            workflow_no_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                Random_Number=Random_Number,
                broker=broker,
                mcp=mcp,
                vector=vector,
                amount_messages=amount_messages,
                iteration=i + 1,
                total_iterations=amount_messages,
            )
        return # Exit the test after running the no-fault scenario

    selected_branch, broker, mcp, vector = _select_workload_branch(broker, mcp, vector, randomness)
    _log(branch, f"Randomness enabled. Selected branch: {selected_branch} (Broker={broker}, MCP={mcp}, Vector={vector})")

    if selected_branch == "no-fault":
        broker, mcp, vector = _select_no_fault_pbac_layers()
        _log(branch, f"Selected NO-FAULT branch with PBAC config: Broker={broker}, MCP={mcp}, Vector={vector}")

        for i in range(amount_messages):
            workflow_no_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                Random_Number=randint(1, 100),
                broker=broker,
                mcp=mcp,
                vector=vector,
                amount_messages=amount_messages,
                iteration=i + 1,
                total_iterations=amount_messages,
            )
        return
        
    #######################################
    # states with fault injection from here on. 
    # If the broker is on we are going to fail when the braker is used the first time, since the messages are not goingin to arrive at the agents that are supposed to receive them.
    #       we test this by listening to the agent history of the agent that is suppose to get the message.
    # If MCP is on we are going to fail when a tool is supposed to be used but is not used in the periode of a timeout. 
    #       We test this by listening to the tool call websocket 
    # If RAG is on we are going to fail when the search knowlege base tool is called. Ther still no clear way of determining if the RAG call failed withput looking at the response manually.
    #       In the case of filtration, RAG gives back a empty list. In our test case, we could just let the RAG tool throw an error if the result is empty since we know what should come back. This would be an issue in the real usecase, since we could not distinguish between there beeing no result and RAG using the wrong purpose. on the other hand, it does not really matter at the moment. 
    # 
    # 

    # If Broker on:
    #   reserve the needed topic with the purposes
    #   THIS MEANS FAULT INNJECTION ON THE BROKER LEVEL
    #   CHANGE THE SUBSCRIPTION PURPOSE TO A WRONG ONE ON PURPOSE 
    #   TODO: Switch to purpose on publish and then publish here with a differend purpose than the one the agent is subscribed to. This will be a more realistic test case. 
    #
    #   Trigger this branch with the command: 
    #   uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=1 --randomness=True
    if selected_branch == "broker":
        _log(branch, f"Selected BROKER-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            workflow_broker_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                mcp=mcp,
                vector=vector,
                iteration=i + 1,
                total_iterations=amount_messages,
            )
    elif selected_branch == "mcp":
        _log(branch, f"Selected MCP-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            workflow_mcp_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                vector=vector,
                iteration=i + 1,
                total_iterations=amount_messages,
            )
    elif selected_branch == "vector":
        _log(branch, f"Selected VECTOR-FAULT branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            workflow_vector_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                mcp=mcp,
                vector=vector,
                iteration=i + 1,
                total_iterations=amount_messages,
            )
    else:
        _log(branch, f"Selected PASSTHROUGH branch for {amount_messages} iteration(s).")
        for i in range(amount_messages):
            workflow_passthrough_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=wildcard_purpose,
                wildcard_purpose=wildcard_purpose,
                mcp=mcp,
                vector=vector,
                iteration=i + 1,
                total_iterations=amount_messages,
            )