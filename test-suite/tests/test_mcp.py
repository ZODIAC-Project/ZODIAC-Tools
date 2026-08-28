from .helper import *
import threading
import json
import time


def test_secret_animal_tool():
    response= send("What is the secret animal? purpose secret")
    assert "cat" in response.lower(), f"Expected 'cat' in response but got: {response}"

def test_tool_recognition():
    response = send("What tools do you have access to? Especially mentioning animals.")
    assert all(
    tool_name in response.lower().replace("_", " ")
    for tool_name in ["public animal", "publish"]), f"Response should at least mention two known tools but was: {response}"

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

def test_mcp_denied_purpose_limitation_by_response():
    response = send("Use the private animal tool.")
    assert "turtle" not in response.lower(), f"private tool was called without the required purpose"
    assert "cat" not in response.lower(), f"while the private animal tool was (correctly) not called, the public animal tool was called unintentionally: {response}"

def test_mcp_allowed_purpose_limitation_by_response():
    response = send("Use the private animal tool.", purposes=["sensitive"])
    assert "turtle" in response.lower(), f"private tool was not called, but had the permission to do so. message: {response}"

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
    # print the subscriptions for debugging
    print("Current subscriptions:", json.dumps(subscriptions, indent=2))
    
    # Extract all topics from the session-based structure
    active_topics = []
    if "sessions" in subscriptions:
        for session in subscriptions["sessions"]:
            for sub in session.get("subscriptions", []):
                active_topics.append(sub.get("topic"))
    
    assert topic in active_topics, \
        f"Expected '{topic}' in active subscriptions but got: {active_topics}"
        
def test_unsubscribe_tool():
    topic = "zodiac/test/unsubscribe-verify"
    session_id = str(uuid.uuid4())

    def sub_call():
        time.sleep(1)
        send(f"Use the subscribe tool to subscribe to the MQTT topic '{topic}' for session '{session_id}'.", session_id=session_id)
    t = threading.Thread(target=sub_call)
    t.start()
    toolcall_listen()
    t.join()

    # Extract all topics from the session-based structure
    subscriptions = get_subscriptions()
    active_topics = []
    if "sessions" in subscriptions:
        for session in subscriptions["sessions"]:
            for sub in session.get("subscriptions", []):
                active_topics.append(sub.get("topic"))

    assert topic in active_topics, \
        f"Expected '{topic}' in active subscriptions before unsubscribe test but got: {active_topics}"

    result2 = {}
    def unsub_call():
        result2["response"] = send(
            f"Use the unsubscribe tool to unsubscribe from '{topic}' for session '{session_id}' and confirm. "
            f"Explicitly use the session ID '{session_id}'.",
            session_id=session_id
        )
    t = threading.Thread(target=unsub_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "unsubscribe" in ws_message.lower(), f"Expected 'unsubscribe' tool call but got: {ws_message}"

    subscriptions = get_subscriptions()
    active_topics = []
    if "sessions" in subscriptions:
        for session in subscriptions["sessions"]:
            for sub in session.get("subscriptions", []):
                active_topics.append(sub.get("topic"))

    assert topic not in active_topics, \
        f"Expected '{topic}' to be removed from subscriptions but it still exists: {active_topics}"


def test_list_subscriptions_tool():
    topic = "zodiac/test/list-check"
    session_id = str(uuid.uuid4())

    # Subscribe to a known topic first
    result = {}
    def sub_call():
        result["response"] = send(f"Use the subscribe tool to subscribe to '{topic}' for session '{session_id}'.", session_id=session_id)
    t = threading.Thread(target=sub_call)
    t.start()
    toolcall_listen()  # drain subscribe event
    t.join()

    # Now list subscriptions
    result2 = {}
    def list_call():
        result2["response"] = send(
            f"Use the list subscriptions tool and tell me all currently subscribed topics for session '{session_id}'.",
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


