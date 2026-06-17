from .helper import *
import threading
import json
import time


def test_tool_recognition():
    response = send("What tools do you have access to?")
    assert all(
    tool_name in response.lower().replace("_", " ")
    for tool_name in ["public animal", "secret animal"]), f"Response should at least mention two known tools but was: {response}"

def test_simple_tool_by_response():
    response = send("Use the public animal tool.")
    assert "cat" in response.lower(), f"Expected a response but got: {response}"

def test_simple_tool_by_websocket():
    result = {}

    def llm_call():
        result["response"] = send("Use the public animal tool and respond with the result.")

    t = threading.Thread(target=llm_call)
    t.start()

    received, message = toolcall_listen()  # connects and waits WHILE llm_call is running
    t.join()

    print(result["response"])
    assert received, "Expected to receive a message on the tool use websocket, but did not receive any within the timeout period. (10s)"
    assert "public_animal" in message, f"Expected 'public_animal' in tool use message but got: {message}"

def test_publish_tool():
    
    topic = "zodiac/test/publish-retained"
    expected_payload = "hello-retained-test"

    result = {}

    def llm_call():
        result["response"] = send(
            f"Use the publish tool to publish the message '{expected_payload}' "
            f"to the MQTT topic '{topic}' with retain=True."
        )

    t = threading.Thread(target=llm_call)
    t.start()

    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "publish" in ws_message.lower(), f"Expected 'publish' tool call but got: {ws_message}"

    # Subscribe AFTER publishing to verify retention
    received = listen_to_a_mqtt_topic(topic, timeout=10.0)
    assert received is not None, "Expected to receive retained message but timed out"
    assert expected_payload in received, f"Expected '{expected_payload}' in retained message but got: '{received}'"
    fuzzy_assert(result["response"], f"The response confirms a retained message was published to topic '{topic}'")


def test_subscribe_tool():
    topic = "zodiac/test/subscribe-verify"
    session_id = str(uuid.uuid4())

    def sub_call():
        result["response"] = send(
            f"Use the subscribe tool to subscribe to the MQTT topic '{topic}' and confirm when done.",
            session_id=session_id
        )

    result = {}
    t = threading.Thread(target=sub_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "subscribe" in ws_message.lower(), f"Expected 'subscribe' tool call but got: {ws_message}"

    # Verify subscription is actually active in stream manager
    subscriptions = get_subscriptions()
    assert topic in subscriptions["topics"], \
        f"Expected '{topic}' in active subscriptions but got: {subscriptions['topics']}"
        
def test_unsubscribe_tool():
    topic = "zodiac/test/unsubscribe-verify"
    session_id = str(uuid.uuid4())

    def sub_call():
        send(f"Use the subscribe tool to subscribe to the MQTT topic '{topic}'.", session_id=session_id)
    t = threading.Thread(target=sub_call)
    t.start()
    toolcall_listen()
    t.join()

    subscriptions = get_subscriptions()
    assert topic in subscriptions["topics"], \
        f"Expected '{topic}' to be subscribed before unsubscribe test but got: {subscriptions['topics']}"

    result2 = {}
    def unsub_call():
        result2["response"] = send(
            f"Use the unsubscribe tool to unsubscribe from '{topic}' and confirm.",
            session_id=session_id
        )
    t = threading.Thread(target=unsub_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "unsubscribe" in ws_message.lower(), f"Expected 'unsubscribe' tool call but got: {ws_message}"

    subscriptions = get_subscriptions()
    assert topic not in subscriptions["topics"], \
        f"Expected '{topic}' to be removed from subscriptions but it still exists: {subscriptions['topics']}"



def test_list_subscriptions_tool():
    topic = "zodiac/test/list-check"
    session_id = str(uuid.uuid4())

    # Subscribe to a known topic first
    result = {}
    def sub_call():
        result["response"] = send(f"Use the subscribe tool to subscribe to '{topic}'.", session_id=session_id)
    t = threading.Thread(target=sub_call)
    t.start()
    toolcall_listen()  # drain subscribe event
    t.join()

    # Now list subscriptions
    result2 = {}
    def list_call():
        result2["response"] = send(
            "Use the list subscriptions tool and tell me all currently subscribed topics.",
            session_id=session_id
        )

    t = threading.Thread(target=list_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "list" in ws_message.lower() or "subscription" in ws_message.lower(), \
        f"Expected list_subscriptions tool call but got: {ws_message}"
    fuzzy_assert(result2["response"], f"The response includes '{topic}' in the list of subscriptions")


def test_create_agent_and_subscribe_tool():
    topic = "zodiac/test/agent-topic"
    session_id = str(uuid.uuid4())
    result = {}

    def llm_call():
        result["response"] = send(
            f"Create an agent that subscribes to the MQTT topic '{topic}' "
            f"and summarizes any incoming messages for data collection purposes. Derive all parameters from the context.",
            session_id=session_id
        )

    t = threading.Thread(target=llm_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "create_agent" in ws_message.lower() or "subscribe" in ws_message.lower(), \
        f"Expected create_agent_and_subscribe tool call but got: {ws_message}"

    # 1. Verify agent exists via REST and get its ID
    agents_response = requests.get(f"{AGENT_URL}/agents")
    assert agents_response.status_code == 200, f"Could not reach agent API: {agents_response.text}"
    agents = agents_response.json()
    matching = [a for a in agents if a.get("listenTopic") == topic]
    assert len(matching) > 0, f"Expected an agent subscribed to '{topic}' but none found"
    agent_id = matching[0]["id"]

    # 2. Verify subscription exists in stream manager
    subscriptions = get_subscriptions()
    subscribed_topics = [
        t
        for session in subscriptions["sessions"]
        if session.get("session_id") == agent_id
        for t in session.get("topics", [])
    ]
    assert topic in subscribed_topics, \
        f"Expected agent '{agent_id}' to be subscribed to '{topic}' but got: {subscribed_topics}"
    
    # 3. Publish a message to the topic and verify it arrives in agent history 
    test_message = "agent-trigger-payload"

    def publish_call():
        send(
            f"Use the publish tool to publish '{test_message}' to the topic '{topic}'.",
            session_id=str(uuid.uuid4())
        )

    pt = threading.Thread(target=publish_call)
    pt.start()
    toolcall_listen()  # drain publish tool call
    pt.join()

    # Wait for the agent to process the message
    time.sleep(5)

    # 4. Check agent history via websocket
    async def get_agent_history_from_ws():
        agent_url_ws = AGENT_URL.replace("http://", "ws://")
        async with websockets.connect(f"{agent_url_ws}/agents/{agent_id}/history") as ws:
            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return json.loads(message)

    history = asyncio.run(get_agent_history_from_ws())
    assert any(test_message in str(e.get("message", "")) for e in history), \
        f"Expected '{test_message}' in agent history but got: {history}"

    # 5. Cleanup
    delete_response = requests.delete(f"{AGENT_URL}/agents/{agent_id}")
    assert delete_response.status_code == 200, f"Failed to delete agent: {delete_response.text}"

    # Manuell unsubscribe da agent manager das noch nicht macht
    unsubscribe_response = requests.post(f"{STREAM_MANAGER_URL}/unsubscribe", json={
        "session_id": agent_id,
        "topic": topic
    })
    assert unsubscribe_response.status_code == 200, f"Failed to unsubscribe: {unsubscribe_response.text}"
    
    # Verify agent is gone
    agents_after = requests.get(f"{AGENT_URL}/agents").json()
    assert not any(a["id"] == agent_id for a in agents_after), "Agent still exists after deletion"

    # Verify subscription is also cleaned up
    subscriptions_after = get_subscriptions()
    assert topic not in subscriptions_after["topics"], \
        f"Expected '{topic}' subscription to be cleaned up after agent deletion but it still exists"