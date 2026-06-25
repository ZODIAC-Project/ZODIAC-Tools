import pytest
import os
import requests
import websockets
import asyncio
from dotenv import load_dotenv
import uuid
import logging
from typing import Optional
import time

import aiomqtt 
import paho.mqtt.client as mqtt
from .purpose_client import PurposeClient
from paho.mqtt.enums import CallbackAPIVersion


load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")
TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")
MQTT_BROKER = os.getenv("MQTT_BROKER", "130.149.158.133")
MQTT_PORT = int(os.getenv("MQTT_PORT", "30069"))
STREAM_MANAGER_URL = os.getenv("STREAM_MANAGER_URL", "http://130.149.158.32:30002")

paho_client = mqtt.Client(
    callback_api_version=CallbackAPIVersion.VERSION1, 
    client_id="purpose_paho_func", 
    clean_session=True
)

client = PurposeClient(paho_client)
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

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
                    message = await asyncio.wait_for(ws.recv(), timeout=100)
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

def register_subscription_of_agent_in_stream_manager(agent_id: str, topic: str, purpose: str):
    payload = {
        "session_id": agent_id,
        "topic": topic,
        "purpose": purpose,
    }
    response = requests.post(f"{STREAM_MANAGER_URL}/subscribe", json=payload)
    assert response.status_code == 200, (
        f"Failed to register subscription in stream manager: status {response.status_code}, response {response.text}"
    )
    return response.json()

def raw_register_subscription_of_agent_in_stream_manager(agent_id: str, topic: str, purpose: str):
    payload = {
        "session_id": agent_id,
        "topic": topic,
        "purpose": purpose,
    }
    response = requests.post(f"{STREAM_MANAGER_URL}/subscribe", json=payload)
    assert response.status_code == 200, (
        f"Failed to register subscription in stream manager: status {response.status_code}, response {response.text}"
    )
    return response.json()

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
    assert response.status_code == 200, f"Failed to delete agent {agent_id}: {response.text}"
    
def remove_all_subscriptions():
    response = requests.get(f"{STREAM_MANAGER_URL}/clear_all")

@pytest.fixture(autouse=True)
def cleanup_agents():
    yield
    delete_all_agents()
