import os
import requests
import websockets
import asyncio
from dotenv import load_dotenv
import uuid

load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")
TOOL_USE_WS = os.getenv("TOOL_USE_WS", "ws://130.149.158.133:30084/tool-use")

def send(msg, session_id = None):
    if session_id is None:
        session_id = str(uuid.uuid4())
    response = requests.post(f"{MCP_URL}/chat", json={"message": msg, "session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
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
 
