# this test is not part of the test suite but rather a manual test
# that can be quickly configured

import requests
import uuid, os

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")
TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")
MQTT_BROKER = os.getenv("MQTT_BROKER", "130.149.158.133")
MQTT_PORT = int(os.getenv("MQTT_PORT", "30069"))
STREAM_MANAGER_URL = os.getenv("STREAM_MANAGER_URL", "http://130.149.158.32:30002")

model="academic/devstral-2-123b-instruct-2512"

def send(msg, session_id = None):
    global model
    print("using model: ", model)
    if session_id is None:
        session_id = str(uuid.uuid4())
    response = requests.post(f"{MCP_URL}/chat", json={"message": msg, "session_id": session_id, "model": model})
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code} (response was: '{response.text}')"
    data = response.json()
    assert "response" in data, f"Response JSON should contain 'response' key but was: {data}"
    return data["response"]

print("=" * 20)
print(send("send the public animal as an email"))
print("=" * 20)
print(send("give me a random number between 50 and 100"))
print("=" * 20)

print(send("""Use the tool search_knowledge_base with collection="subsidies" and purpose="wrong-purpose". use "subsidy entries" as the query.
            Retrieve subsidy entries only from the "subsidies" collection. Do not use the default collection and do not query foerderprogramme_export."""))
print("=" * 20)
print(send("""Use the tool search_knowledge_base with collection="subsidies" and purpose="admin". use "subsidy entries" as the query.
            Retrieve subsidy entries only from the "subsidies" collection. Do not use the default collection and do not query foerderprogramme_export."""))
print("end")
print("=" * 20)