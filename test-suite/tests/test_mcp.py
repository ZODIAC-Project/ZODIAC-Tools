from helper import *
import threading

def test_tool_recognition():
    response = send("What tools do you have access to?")
    assert all(
    tool_name in response.lower().replace("_", " ")
    for tool_name in ["public animal", "secret animal"]), f"Response should at least mention two known tools but was: {response}"

def test_simple_tool_by_response():
    response = send("Use the public animal tool and respond with the result.")
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

def test_send_tool():
    """
    Instruct the LLM to send a message to a specific topic,
    then verify delivery by listening to that topic directly via MQTT.
    """
    topic = "zodiac/test/send"
    expected_payload = "hello-send-test"

    # Send instruction first, then listen
    # Since listen_to_a_mqtt_topic blocks, we fire the LLM call in a thread
    result = {}

    def llm_call():
        result["response"] = send(f"Use the send tool to publish the message '{expected_payload}' to the MQTT topic '{topic}'.")

    t = threading.Thread(target=llm_call)
    t.start()

    received = listen_to_a_mqtt_topic(topic, timeout=15.0)
    t.join()

    assert received is not None, "Expected to receive a message on the topic but timed out"
    assert expected_payload in received, f"Expected '{expected_payload}' in MQTT message but got: '{received}'"
    fuzzy_assert(result["response"], f"The response confirms a message was sent to topic '{topic}'")

def test_publish_tool():
    topic = "zodiac/test/publish-retained"
    expected_payload = "hello-retained-test"

    result = {}

    # LLM runs in background thread
    def llm_call():
        result["response"] = send(
            f"Use the publish tool to publish the message '{expected_payload}' "
            f"to the MQTT topic '{topic}' with retain=True."
        )

    t = threading.Thread(target=llm_call)
    t.start()

    # Main thread blocks here waiting for the websocket event
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
    # TODO CHECK IF THE SUBSCRIPTION WORKS BY CONNECTING TO THE STREAM_MANAGER
    topic = "zodiac/test/subscribe-verify"
    session_id = str(uuid.uuid4())
    result = {}

    def llm_call():
        result["response"] = send(
            f"Use the subscribe tool to subscribe to the MQTT topic '{topic}' and confirm when done.",
            session_id=session_id
        )

    t = threading.Thread(target=llm_call)
    t.start()

    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "subscribe" in ws_message.lower(), f"Expected 'subscribe' tool call but got: {ws_message}"
    fuzzy_assert(result["response"], f"The response confirms a subscription to topic '{topic}'")

def test_unsubscribe_tool():
    
    topic = "zodiac/test/unsubscribe-verify"
    session_id = str(uuid.uuid4())

    result = {}
    def sub_call():
        result["response"] = send(f"Use the subscribe tool to subscribe to the MQTT topic '{topic}'.", session_id=session_id)
    t = threading.Thread(target=sub_call)
    t.start()
    toolcall_listen() 
    t.join()

    result2 = {}
    def unsub_call():
        result2["response"] = send(f"Use the unsubscribe tool to unsubscribe from '{topic}' and confirm.", session_id=session_id)

    t = threading.Thread(target=unsub_call)
    t.start()
    received_ws, ws_message = toolcall_listen()
    t.join()

    assert received_ws, "Expected a tool call on the websocket but got none"
    assert "unsubscribe" in ws_message.lower(), f"Expected 'unsubscribe' tool call but got: {ws_message}"
    fuzzy_assert(result2["response"], f"The message states that unsubscription from topic '{topic}' was successful")


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


def test_create_agent_and_subscibe_tool():
    """
    Docstring for test_create_agent_and_subscibe_tool
    """
    pass