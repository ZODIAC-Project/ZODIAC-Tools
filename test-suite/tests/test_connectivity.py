import os
import requests
from dotenv import load_dotenv

load_dotenv()

MCP_URL = os.getenv("MCP_URL", "http://130.149.158.32:30084")
AGENT_URL = os.getenv("AGENTS_URL", "http://130.149.158.132:30086")

def test_mcp_client_connectivity():
    response = requests.get(f"{MCP_URL}/health")
    assert response.status_code == 200

def test_agent_connectivity():
    response = requests.get(f"{AGENT_URL}/health")
    assert response.status_code == 200

def test_agent_listing():
    response = requests.get(f"{AGENT_URL}/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)