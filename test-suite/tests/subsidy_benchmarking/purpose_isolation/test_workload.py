
"""Start with: 
    broker only: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled
    broker + mcp: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled
    broker + vector: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --vector-enabled
    broker + mcp + vector: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled
    broker + mcp + vector + amount of messages: uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=5
"""

import json
from random import randint
import pytest
import time
import requests
import threading
from ...helper import *
from ..shared.prompts import *

import logging
logging.disable(logging.CRITICAL)


def create_agents(mcp: bool, vector: bool, input_topic: str, midway_topic: str, issue_topic: str, allowed: str, wildcard_purpose: str, agent_purpose_1: str = "query", agent_purpose_2: str = "advertisement") -> tuple[str, str]:
    # (RAG tool has purpose: ![query, knowledge, search, admin])
    # Do we want to use real purposes for the mcp tool calls?
    # Yes we want 
    if mcp == True:
        # Do we want to use the state of the incomming message as purpose for the RAG Tool Call?
        # Yes we want
        if vector == True:
            agent_id_1 = create_agent(
                runOnce=False,
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose= "subsidy/eligibility"),
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
                text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose= "Subsidy/eligibility"),
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


def _cleanup_agents(agent_id_1: str | None, agent_id_2: str | None) -> None:
    if agent_id_1:
        delete_agent(agent_id_1)
    if agent_id_2:
        delete_agent(agent_id_2)


def workflow_no_fault_scenario(input_topic,
                               allowed, 
                               midway_topic, 
                               issue_topic, 
                               wildcard_purpose, 
                               Random_Number, 
                               broker, 
                               mcp, 
                               vector,
                               amount_messages):
    """This Branch is used when the random number is even.
        Trigger this branch manually with the --randomness flag set to False.
        uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=1 --randomness=False
    """
    print("")
    print("--------------------------------------------------------------")
    print(f"Test Scenario: Broker: {broker}, MCP: {mcp}, Vector: {vector}, Amount of Messages: {amount_messages}, Random Number: {Random_Number}")
    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        if broker == True:
            reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement", "admin"])
            reserve_topic(midway_topic, aip=[allowed, wildcard_purpose , "advertisement", "admin"])
        else:
            print("--------------------------------------------------------------")
            print("Broker is disabled. No purpose Reservation was made.")
        #create the agents once 
        agent_id_1, agent_id_2 = create_agents(mcp, vector, input_topic, midway_topic, issue_topic, allowed, wildcard_purpose)
        # check they are healthy 
        print("--------------------------------------------------------------")
        print("Check if both agents exist and are healthy...")
        time.sleep(2)
        agent1_existis = check_agent_exists(agent_id_1)
        assert agent1_existis, f"---> Agent 1 with ID {agent_id_1} does not exist."
        time.sleep(2)
        agent2_existis = check_agent_exists(agent_id_2)
        assert agent2_existis, f"---> Agent 2 with ID {agent_id_2} does not exist."
        print ("---> Both Agents exist and are healthy. Continue with the test scenario.")
        # Publish Message 
        print("--------------------------------------------------------------")
        print(f"Publish a message to the input topic: {input_topic}. This message will be processed by Agent 1.")
        payload = make_trigger_message(state="Bayern")
        publish_response = publish_message(input_topic, json.dumps(payload))
        assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
        
        print("----------------------------------------------------------------------------")
        print("---------------------- Starting the test validation. -----------------------")
        print("-- This can take some tome since we have to wait for the turn to complete --")
        
        collected_tool_calls = []
        collected_tool_calls_lock = threading.Lock()
        stop_tool_call_collector = threading.Event()

        async def collect_tool_calls_async():
            async with websockets.connect(TOOL_USE_WS) as ws:
                while not stop_tool_call_collector.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue

                    with collected_tool_calls_lock:
                        collected_tool_calls.append(data)

        def start_tool_call_collector():
            def runner():
                asyncio.run(collect_tool_calls_async())

            thread = threading.Thread(target=runner, daemon=True)
            thread.start()
            return thread

        tool_call_collector_thread = start_tool_call_collector()

        def tool_calls_for(tool_name: str, session_id: str | None = None) -> list[dict]:
            with collected_tool_calls_lock:
                return [
                    m
                    for m in collected_tool_calls
                    if m.get("tool") == tool_name and (session_id is None or m.get("session_id") == session_id)
                ]

        def wait_for_tool_call(tool_name: str, timeout: float, session_id: str | None = None) -> list[dict]:
            deadline = time.time() + timeout
            while time.time() < deadline:
                matches = tool_calls_for(tool_name, session_id)
                if matches:
                    stop_tool_call_collector.set()
                    return matches
                time.sleep(2)

            stop_tool_call_collector.set()
            return tool_calls_for(tool_name, session_id)

        # Agent 1 got Message?
        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        print(f"---> Agent 1 received a message. Agent History: {agent_history_1}")

        # Agent 2 got a Message? Wait for MESSAGE_TIMEOUT seconds 
        agent_history_2 = get_agent_history(agent_id_2, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_2) > 0, f" No message was received by Agent 2. Agent History: {agent_history_2}"
        print(f"---> Agent 2 received a message. Agent History: {agent_history_2}")

        # Agent 2 called the Email Tool for its own session?
        email_calls = wait_for_tool_call("send_email", timeout=MESSAGE_TIMEOUT)
        assert email_calls, (
            f"Agent 2 did not call the Email Tool in its own session. "
            f"Captured messages: {collected_tool_calls}. Agent_id_2: {agent_id_2}"
        )
        print(f"---> Agent 2 called the Email Tool in session {agent_id_2}. Tool Call Message(s): {email_calls}")

        print("|")
        print("-> All test validation asserts passed. The test scenario was successful.")
    finally:
        _cleanup_agents(agent_id_1, agent_id_2)


def workflow_broker_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector):
    print("")
    print("--------------------------------------------------------------")
    print("Test Scenario: Broker fault branch")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
        reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement"])

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
        print("--------------------------------------------------------------")
        print("Check if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        time.sleep(2)
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."

        payload = make_trigger_message(state="Bayern")
        publish_message(input_topic, json.dumps(payload))

        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) == 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
        print(f"---> Agent 1 received NO message. This is expected.Agent History: {agent_history_1}")
    finally:
        _cleanup_agents(agent_id_1, agent_id_2)


def workflow_mcp_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, vector):
    print("")
    print("--------------------------------------------------------------")
    print("Test Scenario: MCP fault branch")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
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

        print("--------------------------------------------------------------")
        print("Check if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."

        payload = make_trigger_message(state="Bayern")
        publish_response = publish_message(input_topic, json.dumps(payload))
        print(f"Message published: {publish_response}")

        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"

        toolcall_exists, toolcall_message = toolcall_listen_for_tool_and_word("send_email", "Agent1")
        assert not toolcall_exists, f"Tool call was made with wrong purpose. This is unexpected. Tool Call Message: {toolcall_message}"
    finally:
        _cleanup_agents(agent_id_1, agent_id_2)


def workflow_vector_fault_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector):
    print("")
    print("--------------------------------------------------------------")
    print("Test Scenario: Vector fault branch")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
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
        )
        print("--------------------------------------------------------------")
        print("Check if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."

        payload = make_trigger_message(state="Leipzig")
        publish_response = publish_message(input_topic, json.dumps(payload))
        print(f"Message published: {publish_response}")

        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"

        toolcall_exists, toolcall_message = toolcall_listen_for_tool("search_knowledge_base")
        assert toolcall_exists, f"Expected search_knowledge_base to be called. Tool Call Message: {toolcall_message}"

        issue_message = listen_to_a_mqtt_topic(issue_topic, timeout=MESSAGE_TIMEOUT)
        assert issue_message is not None, f"Expected an error message on {issue_topic}, but none was received."
        assert "ACCESS_DENIED_PURPOSE_ISSUE" in issue_message, (
            f"Expected ACCESS_DENIED_PURPOSE_ISSUE on {issue_topic}, but got: {issue_message}"
        )
    finally:
        _cleanup_agents(agent_id_1, agent_id_2)


def workflow_passthrough_scenario(input_topic, midway_topic, issue_topic, allowed, wildcard_purpose, mcp, vector):
    print("")
    print("--------------------------------------------------------------")
    print("Test Scenario: PBAC-disabled pass-through branch")

    agent_id_1: str | None = None
    agent_id_2: str | None = None
    try:
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
        print("--------------------------------------------------------------")
        print("Check if both agents exist and are healthy...")
        assert check_agent_exists(agent_id_1), f"Agent 1 with ID {agent_id_1} does not exist."
        assert check_agent_exists(agent_id_2), f"Agent 2 with ID {agent_id_2} does not exist."

        payload = make_trigger_message(state="admin")
        publish_response = publish_message(input_topic, json.dumps(payload))
        print(f"Message published: {publish_response}")

        agent_history_1 = get_agent_history(agent_id_1, timeout=MESSAGE_TIMEOUT)
        assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"

        toolcall_exists, toolcall_message = toolcall_listen_for_tool("send_email")
        assert toolcall_exists, f"Expected send_email to be called. Tool Call Message: {toolcall_message}"
    finally:
        _cleanup_agents(agent_id_1, agent_id_2)



def test_workload_purpose_isolation_scenario(request, topic_factory, purpose_factory):
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

    # Generate Random number X per message.
    #   X % 2 == 0 --> no fault 
    #   X % 2 == 1 --> fault injected 
    if randomness == True:
        Random_Number = randint(1, 100)
        print("--------------------------------------------------------------")
        print(f"Test Scenario: Broker: {broker}, MCP: {mcp}, Vector: {vector}, Amount of Messages: {amount_messages}, Random Number: {Random_Number}")

    else:
        Random_Number = 2  # Set to even number for deterministic behavior
        print("--------------------------------------------------------------")
        print(f"Test Scenario: Broker: {broker}, MCP: {mcp}, Vector: {vector}, Amount of Messages: {amount_messages}, Random Number: {Random_Number}")

        for _ in range(amount_messages):
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
                amount_messages=amount_messages
            )
        
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
    if broker == True:
        for _ in range(amount_messages):
            workflow_broker_fault_scenario(
                input_topic=input_topic,
                midway_topic=midway_topic,
                issue_topic=issue_topic,
                allowed=allowed,
                wildcard_purpose=wildcard_purpose,
                mcp=mcp,
                vector=vector,
            )

    else:
        # from here we go one layer deeper in the tree. We need to now act differently depending on weather the MCP is on or of 
        
        # The broker is not anabled so we we dont fail on the broker level. we send the message to the agend and it should arrive. 
        # We then chek if the tool calle was made and that is where we want to fail on this test path.
        # The tool call should be made with the wrong purpose. Since the tool call is made with the same purpose as used for the creation of the agent,
        # we want to create the agent with a purpose that is not allowe for the tool call. This will not effect the arrival of the message, since we dont reserve on this path. 
        # Trigger this with the command:
        # uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --mcp-enabled --vector-enabled --amount-messages=1 --randomness=True
        if mcp == True:
            for _ in range(amount_messages):
                workflow_mcp_fault_scenario(
                    input_topic=input_topic,
                    midway_topic=midway_topic,
                    issue_topic=issue_topic,
                    allowed=allowed,
                    wildcard_purpose=wildcard_purpose,
                    vector=vector,
                )

        else:
            # MCP is not enabled so we dont fail through mcp
            # We go into the vektor layer and if vector is enabled we want to faild here 
            # If vector is not enabled, every layer of the PBAC is diabled so we want our scenario to pass.
            # no reservation 
            # wildcard purpose for agent creation 
            if vector == True:
                for _ in range(amount_messages):
                    workflow_vector_fault_scenario(
                        input_topic=input_topic,
                        midway_topic=midway_topic,
                        issue_topic=issue_topic,
                        allowed=allowed,
                        wildcard_purpose=wildcard_purpose,
                        mcp=mcp,
                        vector=vector,
                    )
            else:
                for _ in range(amount_messages):
                    workflow_passthrough_scenario(
                        input_topic=input_topic,
                        midway_topic=midway_topic,
                        issue_topic=issue_topic,
                        allowed=wildcard_purpose,
                        wildcard_purpose=wildcard_purpose,
                        mcp=mcp,
                        vector=vector,
                    )




