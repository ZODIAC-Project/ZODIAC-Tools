
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
    
    def create_agents():
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
                    purpose="query",
                    memoryWindow=5,
                    listenTopic=input_topic,
                )
            # No we dont 
            else:
                agent_id_1 = create_agent(
                    runOnce=False,
                    text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic, vektor_purpose= "admin"),
                    purpose="query",
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
                purpose="advertisement",
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
                
    if broker == True:
        reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement", "admin"])
        reserve_topic(midway_topic, aip=[allowed, wildcard_purpose , "advertisement", "admin"])
    else:   
        print("--------------------------------------------------------------")
        print("Broker is disabled. No purpose Reservation was made.")
    #create the agents once 
    agent_id_1, agent_id_2 = create_agents()
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
    agent_history_1 = get_agent_history(agent_id_1, timeout=200)
    assert len(agent_history_1) > 0, f" No message was received by Agent 1. Agent History: {agent_history_1}"
    print(f"---> Agent 1 received a message. Agent History: {agent_history_1}")

    # Agent 2 got a Message? Wait for 300 seconds 
    agent_history_2 = get_agent_history(agent_id_2, timeout=300)
    assert len(agent_history_2) > 0, f" No message was received by Agent 2. Agent History: {agent_history_2}"
    print(f"---> Agent 2 received a message. Agent History: {agent_history_2}")

    # Agent 2 called the Email Tool?
    email_calls = wait_for_tool_call("send_email", timeout=300)
    assert email_calls, f"Agent 2 did not call the Email Tool. Captured messages: {collected_tool_calls}. Agent_id_2: {agent_id_2}"
    print(f"---> Agent 2 called the Email Tool. Tool Call Message(s): {email_calls}")

    print("|")
    print("-> All test validation asserts passed. The test scenario was successful.")
    delete_agent(agent_id_1)
    delete_agent(agent_id_2)

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
    else:
        Random_Number = 2  # Set to even number for deterministic behavior
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
    return 
        
    #######################################
    # From here on is work in progress. The test scenario is not yet fully implemented. 
        
        
    # If Broker on:
    #   reserve the needed topic with the purposes
    if broker == True:
        reserve_topic(input_topic, aip=[allowed, wildcard_purpose, "query", "advertisement"])

    print("--------------------------------------------------------------")
    print(f"Test Scenario: Broker: {broker}, MCP: {mcp}, Vector: {vector}, Amount of Messages: {amount_messages}, Random Number: {Random_Number}")

    if mcp == True:
        agent_id_1 = create_agent(
            runOnce=False,
            text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic),
            purpose="query",
            memoryWindow=5,
            listenTopic=input_topic,
        )
    else:
        agent_id_1 = create_agent(
            runOnce=False,
            text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic),
            purpose=wildcard_purpose,
            memoryWindow=5,
            listenTopic=input_topic,
        )

    time.sleep(2)
    agent1_existis = check_agent_exists(agent_id_1)
    assert agent1_existis, f"Agent 1 with ID {agent_id_1} does not exist."

    if mcp == True:
        agent_id_2 = create_agent(
            runOnce=False,
            text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
            purpose="advertisement",
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

    time.sleep(2)
    agent2_existis = check_agent_exists(agent_id_2)
    assert agent2_existis, f"Agent 2 with ID {agent_id_2} does not exist."

    payload = trigger_message(state="Bayern & BW")
    publish_response = publish_message(input_topic, json.dumps(payload))

    time.sleep(300)
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    time.sleep(5)
    agentHistory_1 = get_agent_history(agent_id_1)
    if broker == True:
        if Random_Number % 2 == 0:
            print("--------------------------------------------------------------")
            print(f"Agent 1 should receive the message. Check using Agent Histoy.")
            print(f"Agent 1 history: {agentHistory_1}")
            assert any(msg.get("text") == payload for msg in agentHistory_1), f"Agent 1 did not receive the message: {payload}. This is unexpected. Test fails."
        if Random_Number % 2 == 1:
            print("--------------------------------------------------------------")
            print(f"Agent 1 should not receive the message. Check using Agent Histoy.")
            print(f"Agent 1 history: {agentHistory_1}")
            assert not any(msg.get("text") == payload for msg in agentHistory_1), f"Agent 1 did receive the message: {payload}. This is unexpected. Test fails."

    # This wrapper exists so the file is executable with pytest flags.
    # Example:
    # uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
    #   --broker-enabled --mcp-enabled --vector-enabled --amount-messages 3
    # Broker on/of, MCP on/off, Vector on/off
    broker = broker_enabled
    mcp = mcp_enabled
    vector = vector_enabled 
    
    amount_messages = amount_messages
    
    # Generate Random number X per message. 
    #   X % 2 == 0 --> no fault 
    #   X % 2 == 1 --> fault injected
    Random_Number = randint(1, 100)
    
    input_topic = topic_factory("input")
    
    result_topic = topic_factory("result")
    midway_topic = topic_factory("midway")
    issue_topic = topic_factory("issue")
    # purposes for broker 
    allowed = purpose_factory("allowed")
    blocked = purpose_factory("blocked")
    
    wildcard_purpose = "admin"
    
    # If Broker on:
    #   reserve the needet topic with the purposes 
    if broker == True:
        reserve_topic(input_topic, aip=[allowed])
    
    print("--------------------------------------------------------------")
    print(f"Test Scenario: Broker: {broker}, MCP: {mcp}, Vector: {vector}, Amount of Messages: {amount_messages}, Random Number: {Random_Number}")
    
    # Spawn Agent 1
    #   check that exists 
    #       Task: Wait For incomming Messages. If The Incomming Message is a Subsidy/Customer Description use RAG to find a Matching Customer/Subsidy. Choose One if there are multiple. Publish the Result to the topic: {Result Topic}. For the RAG Tool Call use the State of the incomming message as Purpose for the RAG Tool Call. For the Publish use the Purpose: {Purpose}. If the Toolcall or the RAG call fails, send a message: "ACCESS_DENIED_PURPOSE_ISSUE" to the Issue topic: {Issue_Topic}.
    
    if mcp == True:
        # (Email tool has purpose: ![query, knowledge, search, admin])
        agent_id_1 = create_agent(
            runOnce=False,
            text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic),
            purpose= "query",  
            memoryWindow=5,
            listenTopic=input_topic,
        )
    else:
        agent_id_1 = create_agent(
            runOnce=False,
            text=Agent_1_task(midway_topic=midway_topic, allowed_purpose=allowed, issue_topic=issue_topic),
            purpose= wildcard_purpose,  
            memoryWindow=5,
            listenTopic=input_topic,
        )
    
    time.sleep(2) 
    # check if agent is there 
    agent1_existis = check_agent_exists(agent_id_1)
    assert agent1_existis, f"Agent 1 with ID {agent_id_1} does not exist."

    # Spawn Agent 2
    #   check that exists
    #      Task: Wait For incomming Messages. If The an Message arrives and it is an Customer/Subsidy Pair, Extract Only the ids and use the Email Tool to send an email with the content: {customer: id, subsidy: id}. For the Email Tool Call use the Purpose: {Purpose}. If the Toolcall fails, send a message: "ACCESS_DENIED_PURPOSE_ISSUE" to the Issue topic: {Issue_Topic}.
    
    #(Email tool has purpose: ![advertisement, external, admin])
    if mcp == True:
        agent_id_2 = create_agent(
            runOnce=False,
            text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
            purpose= "advertisement",  
            memoryWindow=5,
            listenTopic=midway_topic,
        )
    else:
        agent_id_2 = create_agent(
            runOnce=False,
            text=Agent_2_task(allowed_purpose=allowed, issue_topic=issue_topic),
            purpose= wildcard_purpose,  
            memoryWindow=5,
            listenTopic=midway_topic,
        )
    
    time.sleep(2)
    # check if agent is there
    agent2_existis = check_agent_exists(agent_id_2)
    assert agent2_existis, f"Agent 2 with ID {agent_id_2} does not exist."

    # Publish a Message (subsidy or customer description) to the topic Agent 1 is listening to. (This is done from the Test Suite and not from an Agent)
    input_message = trigger_message(state="Bayern & BW")
    publish_response = publish_message(input_topic, json.dumps(input_message))
    
    time.sleep(300)  # wait for agents to process the message
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"
    
    # If Broker is on
    #   If X % 2 == 0
    #       Agent 1 should receive the message. Check using Agent Histoy.
    #       Fail if Agent 1 did not receive the message. This is unexpected and the Test fails.
    #   If X % 2 == 1
    #       Agent 1 should not receive the message. Check using Agent Histoy.
    #       If Agent 1 did not receive the message, The whole Test is skipped, because the MCP and Vector Layer will not be reached. This ia expected and the Test finishes as passed.
    #       If Ageent 1 did receive the message, we fail the test, because this is unexpected. The Test fails.
    # If Broker is off, we just test if the message was received by Agent 1. If not, we fail the test. If yes, we continue to the next step.
    time.sleep(5)  # wait for agents to process the message
    agentHistory_1 = get_agent_history(agent_id_1)
    if broker == True:
        if Random_Number % 2 == 0:
            print("--------------------------------------------------------------")
            print(f"Agent 1 should receive the message. Check using Agent Histoy.")
            print(f"Agent 1 history: {agentHistory_1}")
            assert any(msg.get("text") == input_message for msg in agentHistory_1), f"Agent 1 did not receive the message: {input_message}. This is unexpected. Test fails."
        if Random_Number % 2 == 1:
            print("--------------------------------------------------------------")
            print(f"Agent 1 should not receive the message. Check using Agent Histoy.")
            print(f"Agent 1 history: {agentHistory_1}")
            assert not any(msg.get("text") == input_message for msg in agentHistory_1), f"Agent 1 did receive the message: {input_message}. This is unexpected. Test fails."
        
    # If MCP is on 
    #  If X % 2 == 0
    #       Agent 1 should be able to call the RAG Tool. Check using the Tool Call History.
    #       If the Tool Call was successful, we continue to the next step.
    #       If the Tool Call was not successful, we fail the test, because this is unexpected. The Test fails.
    #  If X % 2 == 1
    #       Agent 1 should not be able to call the RAG Tool. Check using the Tool Call History and listen to the Issue Topic.
    #       If the Tool Call was not successful, we skip the rest of the test, because the Vector Layer will not be reached. This is expected and the Test finishes as passed.
    #       If the Tool Call was successful, we fail the test, because this is unexpected. The Test fails.
    # If MCP is off, we just test if the Tool Call was successful. And that nothing arrived on the Issue Topic. Since we use the wildcard purpose "Admin" for the Tool Call, it should always be successful. If not, we fail the test.
    
    # If Vector is on 
    #   If X % 2 == 0
    #       Agent 1 should be able to get a result from the RAG Tool Call. Check using the Tool Call History.
    #       We send a Subsidy For Berlin so the result should be a Customer from Berlin and no other state.
    #       If the Result is correct, we continue to the next step.
    #       If the Result is not correct, we fail the test, because this is unexpected. The Test fails.
    #   If X % 2 == 1
    #       Agent 1 should not be able to get a result from the RAG Tool Call. Check using the Tool Call History.
    #       We Send a Subsidy for Sachsenanhalt so there should be no Customer returned, since we dont have any Customer from Sachsenanhalt in the Database. If a Customer is returned, we fail the test, because this is unexpected. The Test fails.
    # If Vector is off, we use the wildcard purpose "Admin" for RAG, this shoudl return all Customers. So also one that fits. 
    
    # We listen to the result topic directly to validate that is going through until this point. 
    # When A message appears on the result topic, we check if Agent 2 received it. 
    
    # We Check the tool Call history with the id of Agent 2 and see if the Email Tool was called. If not, we fail the test, because this is unexpected. The Test fails.
    
    # If the MCP is on
    #   If X % 2 == 0
    #       Agent 2 should be able to call the Email Tool. Check using the Tool Call History.
    #       If the Tool Call was successful, we continue to the next step.
    #       If the Tool Call was not successful, we fail the test, because this is unexpected. The Test fails.
    #   If X % 2 == 1
    #       Agent 2 should not be able to call the Email Tool since we give the wrong purpose. 
    #       Check using the Tool Call History and listen to the Issue Topic.
    #       If the Tool Call was not successful, we skip the rest of the test, because the Vector Layer will not be reached. This is expected and the Test finishes as passed.
    #  If MCP is off, we use admin purpose for the Email Tool Call, this shoudl always be successful. If not, we fail the test.
    
    # Do this workflow for every message in the amount of messages. The setup stays the same but we just send a new message to the input topic with a new random number.