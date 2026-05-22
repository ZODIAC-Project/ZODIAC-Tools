import os
import requests
import websockets
import asyncio
from dotenv import load_dotenv
import uuid

import aiomqtt 

load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")
TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")
MQTT_BROKER = os.getenv("MQTT_BROKER", "130.149.158.133")
MQTT_PORT = int(os.getenv("MQTT_PORT", "30069"))
STREAM_MANAGER_URL = os.getenv("STREAM_MANAGER_URL", "http://130.149.158.32:30002")

def send(msg, session_id = None):
    if session_id is None:
        session_id = str(uuid.uuid4())
    response = requests.post(f"{MCP_URL}/chat", json={"message": msg, "session_id": session_id})
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code} (response was: '{response.text}')"
    data = response.json()
    assert "response" in data, f"Response JSON should contain 'response' key but was: {data}"
    return data["response"]

def tools_listen(on_message):
    async def handle():
        async with websockets.connect(TOOL_USE_WS) as ws:
            async for msg in ws:
                print("Received message:", msg)
                on_message(msg) 
    asyncio.run(handle())


def toolcall_listen() -> tuple[bool, str | None]:
    async def handle():
        try:
            async with websockets.connect(TOOL_USE_WS) as ws:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=10)
                    return True, message
                except asyncio.TimeoutError:
                    return False, None
        except (ConnectionRefusedError, OSError) as exc:
            raise ConnectionError(f"Could not connect to {TOOL_USE_WS!r}: {exc}") from exc
    return asyncio.run(handle())

# test the output of llms with another llm, allowing for some fuzziness in the response (e.g. different wording, additional text, etc.)
def fuzzy_assert(test_string, rule):
    out_prompt = (
        f"Does the following message satisfy this condition? "
        f"Message: '{test_string}' "
        f"Condition: {rule} "
        f"Answer with 'True' if the condition is satisfied, or 'False' if not, followed by a brief explanation."
    )

    response = send(out_prompt, session_id=str(uuid.uuid4()))
    if "False" in response:
        assert False, f"LLM returned '{response}' for test string: '{test_string}'"
    if "True" not in response:
        assert False, f"While the LLM did not return 'False' it also did not return 'True' - it returned '{response}' instead for test string: '{test_string}'"
        
def listen_to_a_mqtt_topic(topic:str,timeout: float = 10.0) -> str:
    """
    This function establishes a mqtt connection to a broker and listens to a topic
    Return:
        The message received on the topic
    """
    async def handle():
        async with aiomqtt.Client(MQTT_BROKER, port=MQTT_PORT) as client:
            await client.subscribe(topic)
            async with asyncio.timeout(timeout):
                async for message in client.messages:
                    return str(message.payload.decode())

    return asyncio.run(handle())

def get_subscriptions():
    response = requests.get(f"{STREAM_MANAGER_URL}/subscriptions")
    assert response.status_code == 200, f"Could not reach stream manager: {response.text}"
    return response.json()
    