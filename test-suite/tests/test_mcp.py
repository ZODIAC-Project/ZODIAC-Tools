from helper import *

def test_tool_recognition():
    response = send("What tools do you have access to?")
    assert all(
    tool_name in response.lower().replace("_", " ")
    for tool_name in ["public animal", "secret animal"]), f"Response should at least mention two known tools but was: {response}"

def test_simple_tool_by_response():
    response = send("Use the public animal tool and respond with the result.")
    assert "cat" in response.lower(), f"Expected a response but got: {response}"

def test_simple_tool_by_websocket():
    response = send("Use the public animal tool and respond with the result.")
    received, message = toolcall_listen()
    print(response)
    assert received, "Expected to receive a message on the tool use websocket, but did not receive any within the timeout period. (10s)"
    assert "public_animal" in message, f"Expected the tool use message to mention 'public_animal' but got: {message}"