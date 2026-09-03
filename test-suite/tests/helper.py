from logging import config
import os
import json
import requests
import websockets
import asyncio
from dotenv import load_dotenv
import uuid
import logging
from typing import Optional
import time

import aiomqtt 
load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")
TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")
MQTT_BROKER = os.getenv("MQTT_BROKER", "130.149.158.133")
MQTT_PORT = int(os.getenv("MQTT_PORT", "30069"))
STREAM_MANAGER_URL = os.getenv("STREAM_MANAGER_URL", "http://130.149.158.32:30002")
MESSAGE_TIMEOUT = 30

DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", None)

class PurposeClientProxy:
    """Keep imports stable while pytest swaps in a fresh client per test."""

    def __init__(self):
        self._current = None

    def set_current(self, current):
        self._current = current

    def clear_current(self):
        self._current = None

    def __getattr__(self, name):
        if self._current is None:
            raise RuntimeError("The MQTT test client is not active for this test.")
        return getattr(self._current, name)


# Tests import this name directly. The proxy ensures those imports always use
# the function-scoped client installed by the pytest fixture.
client = PurposeClientProxy()

def send(msg, session_id=None, model=None, purposes=None):
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {"message": "msg: " + msg, "session_id": session_id}
    if DEFAULT_LLM_MODEL is not None:
        payload["model"] = DEFAULT_LLM_MODEL
    if model is not None:
        payload["model"] = model
    if purposes is not None:
        payload["purposes"] = purposes
    response = requests.post(f"{MCP_URL}/chat", json=payload)
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
                    message = await asyncio.wait_for(ws.recv(), timeout=100)
                    return True, message
                except asyncio.TimeoutError:
                    return False, None
        except (ConnectionRefusedError, OSError) as exc:
            raise ConnectionError(f"Could not connect to {TOOL_USE_WS!r}: {exc}") from exc
    return asyncio.run(handle())

def toolcall_listen_for_tool(tool_name: str, timeout: float = MESSAGE_TIMEOUT) -> tuple[bool, str | None]:
    async def handle():
        async with websockets.connect(TOOL_USE_WS) as ws:
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        if data.get("tool") == tool_name:
                            return True, msg
            except TimeoutError:
                return False, None
    return asyncio.run(handle())

def toolcall_listen_for_tool_and_word(tool_name: str, word: str, timeout: float = MESSAGE_TIMEOUT):
    async def handle():
        async with websockets.connect(TOOL_USE_WS) as ws:
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        print("Received message:", msg)
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        if data.get("tool") == tool_name and word in json.dumps(data.get("parameters", {})):
                            return True, msg
            except TimeoutError:
                return False, None
    return asyncio.run(handle())

def toolcall_listen_for_tool_and_session_id(tool_name: str, session_id: str, timeout: float = MESSAGE_TIMEOUT):
    async def handle():
        async with websockets.connect(TOOL_USE_WS) as ws:
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        if data.get("tool") == tool_name and data.get("session_id") == session_id:
                            return True, msg
            except TimeoutError:
                return False, None
    return asyncio.run(handle())

def toolcall_listen_for_multiple(word_a, word_b, timeout=MESSAGE_TIMEOUT):
    async def handle():
        result = {word_a: (False, None), word_b: (False, None)}
        remaining = {word_a, word_b}
        async with websockets.connect(TOOL_USE_WS) as ws:
            try:
                async with asyncio.timeout(timeout):
                    async for msg in ws:
                        for w in list(remaining):
                            if w in msg:
                                result[w] = (True, msg)
                                remaining.discard(w)
                        if not remaining:
                            break
            except TimeoutError:
                pass
        return result
    return asyncio.run(handle())

def collect_tool_calls(timeout: float = MESSAGE_TIMEOUT) -> list[dict]:
    """
    collect every message on the tool-use websocket
    for the given window, decoded as JSON. Needed instead of toolcall_listen
    because that stops at the first message — this needs to see everything
    to detect duplicate/extra tool calls.
    """
    import json

    messages = []

    def on_message(msg):
        try:
            messages.append(json.loads(msg))
        except json.JSONDecodeError:
            pass

    async def handle():
        try:
            async with websockets.connect(TOOL_USE_WS) as ws:
                try:
                    async with asyncio.timeout(timeout):
                        async for msg in ws:
                            on_message(msg)
                except TimeoutError:
                    pass
        except (ConnectionRefusedError, OSError) as exc:
            raise ConnectionError(f"Could not connect to {TOOL_USE_WS!r}: {exc}") from exc

    asyncio.run(handle())
    return messages


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
        
def listen_to_a_mqtt_topic(topic: str, timeout: float = 10.0) -> str | None:
    async def handle():
        async with aiomqtt.Client(MQTT_BROKER, port=MQTT_PORT) as c:
            await c.subscribe(topic)
            try:
                async with asyncio.timeout(timeout):
                    async for message in c.messages:
                        return str(message.payload.decode())
            except TimeoutError:
                return None  # kein Timeout-Exception nach außen

    return asyncio.run(handle())

async def _listen_many(topics_with_timeouts):
    async def one(topic, timeout):
        async with aiomqtt.Client(MQTT_BROKER, port=MQTT_PORT) as c:
            await c.subscribe(topic)
            try:
                async with asyncio.timeout(timeout):
                    async for message in c.messages:
                        return str(message.payload.decode())
            except TimeoutError:
                return None
    return await asyncio.gather(*(one(t, to) for t, to in topics_with_timeouts))

def listen_to_multiple_mqtt_topics(topics_with_timeouts: list[tuple[str, float]]) -> list[str | None]:
    return asyncio.run(_listen_many(topics_with_timeouts))

def get_subscriptions():
    response = requests.get(f"{STREAM_MANAGER_URL}/subscriptions")
    assert response.status_code == 200, f"Could not reach stream manager: {response.text}"
    return response.json()
    
    
def create_agent(runOnce: bool, text: str, purpose: str | None, memoryWindow: int, intervalMs: Optional[int] = None, listenTopic: Optional[str] = None, purposes: Optional[list[str]] = None):
    if purposes is None:
        purposes = [purpose] if purpose else None
    if not purposes:
        raise ValueError("create_agent requires 'purpose' or 'purposes' to be provided")

    payload = {
        "runOnce": runOnce,
        "text": text,
        "purposes": purposes,
        "memoryWindow": memoryWindow,
    }
    if DEFAULT_LLM_MODEL is not None:
        payload["llmModel"] = DEFAULT_LLM_MODEL
    if intervalMs:
        payload["intervalMs"] = intervalMs
    if listenTopic:
        payload["listenTopic"] = listenTopic
    
    response = requests.post(f"{AGENT_URL}/agents", json=payload)
    assert response.status_code == 200, (
        f"Failed to create agent: status {response.status_code}, response {response.text}"
    )
    data = response.json()
    assert "id" in data, f"Agent creation response missing id: {data}"
    return data["id"]


def subscribe_with_purpose(topic: str, ap: str, qos=0, presub=False):
    response = client.subscribe_with_purpose(topic, ap, qos=qos)
    logging.debug(f"Subscribed to topic {topic} with purpose {ap} and QoS {qos}. Response: {response}")
    if isinstance(response, tuple):
        result, mid = response
        return {"status": "success" if result == 0 else "error", "result": result, "mid": mid}
    return response
    
    
def publish_message(topic: str, payload: str, qos=0, retain=False):
    response = client.send(topic, payload, qos=qos)
    if hasattr(response, "rc"):
        return {"status": "success" if response.rc == 0 else "error", "rc": response.rc, "mid": getattr(response, "mid", None)}
    logging.debug(f"Published message to topic {topic} with payload '{payload}', QoS {qos}, retain {retain}.")
    return response

def reserve_topic(topic: str, aip: list = [], pip: list = [], dontwait=False):
    response = client.reserve(topic, aip=aip, pip=pip, dontwait=dontwait)
    if isinstance(response, int):
        return {"status": "success", "mid": response}
    logging.debug(f"Reserved topic {topic} with AIP {aip} and PIP {pip}. Response: {response}")
    return response

def send_and_expect(topic: str, payload: str, purposes: list = []):
    response = client.send_and_expect(topic, payload, purposes=purposes)
    if hasattr(response, "rc"):
        status = "success" if response.rc == 0 else "error"
        return {"status": status, "rc": response.rc, "mid": getattr(response, "mid", None)}
    return response

def send_and_reject(topic: str, payload: str, purposes: list = []):
    response = client.send_and_reject(topic, payload, purposes=purposes)
    if hasattr(response, "rc"):
        status = "success" if response.rc == 0 else "error"
        return {"status": status, "rc": response.rc, "mid": getattr(response, "mid", None)}
    return response

def reset():
    client.reset_broker()
    time.sleep(1)
    client.reset_connection()
    
def delete_all_agents():
    response = requests.get(f"{AGENT_URL}/agents")
    assert response.status_code == 200, f"Failed to fetch agents: {response.text}"
    agents = response.json()
    for agent in agents:
        delete_agent(agent["id"])

def delete_agent(agent_id: str):
    response = requests.delete(f"{AGENT_URL}/agents/{agent_id}")
    if response.status_code == 404:
        return
    assert response.status_code == 200, f"Failed to delete agent {agent_id}: {response.text}"
    
def remove_all_subscriptions():
    response = requests.get(f"{STREAM_MANAGER_URL}/clear_all")
    
    
def get_agent_history(agent_id: str, limit: int = 80, timeout: float = 10.0) -> list:
    deadline = time.time() + timeout
    while True:
        response = requests.get(f"{AGENT_URL}/agents/{agent_id}/history", params={"limit": limit}, timeout=10.0)
        assert response.status_code == 200, f"Failed to fetch history for agent {agent_id}: {response.text}"
        data = response.json()
        if isinstance(data, dict):
            history = data.get("history", [])
        else:
            history = data

        if history or time.time() >= deadline:
            return history

        time.sleep(2)


def wait_for_message_in_history(agent_id: str, expected_payload: str, timeout: float = MESSAGE_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = get_agent_history(agent_id)
        for entry in history:
            content = entry.get("content", "") or entry.get("message", "") or entry.get("text", "") or str(entry)
            if expected_payload in content:
                return True
        time.sleep(0.5)
    return False

def check_agent_exists(agent_id):
    try:
      agents_response = requests.get(f"{AGENT_URL}/agents", timeout=30)
    except requests.RequestException as e:
        print(f"Error occurred while checking agent existence: {e}")
        return False
    agents = agents_response.json()
    agent_info = next((a for a in agents if a.get("id") == agent_id), None)
    if agent_info is None:
        return False
    return True
