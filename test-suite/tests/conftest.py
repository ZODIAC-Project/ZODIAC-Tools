import pytest
import uuid
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from . import helper
from .purpose_client import PurposeClient

def _retain_agents(request):
    return request.node.get_closest_marker("retain_agents") is not None


@pytest.fixture(autouse=True)
def cleanup_agents(request):
    """Autouse fixture that deletes agents after each test unless test is marked to retain them."""
    yield
    if _retain_agents(request):
        return
    try:
        helper.delete_all_agents()
    except Exception:
        # don't fail tests because cleanup failed
        pass


@pytest.fixture
def mqtt_client():
    """Provide every test with an isolated, fully connected MQTT client."""
    raw_client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"purpose-test-{uuid.uuid4().hex}",
        clean_session=True,
    )
    raw_client.reconnect_delay_set(min_delay=1, max_delay=5)
    current_client = PurposeClient(raw_client)

    current_client.connect(helper.MQTT_BROKER, helper.MQTT_PORT, 60)
    current_client.loop_start()
    try:
        current_client._ensure_connected(timeout=10)
    except Exception:
        current_client.loop_stop()
        raise

    yield current_client

    try:
        current_client.client.disconnect()
    finally:
        current_client.loop_stop()


@pytest.fixture(autouse=True)
def isolated_mqtt_client(mqtt_client):
    """Make the per-test client available through the existing helper API."""
    helper.client.set_current(mqtt_client)
    yield
    helper.client.clear_current()
    
def pytest_addoption(parser):
    parser.addoption(
        "--run-config", action="store", default=None,
        help="Path to YAML file with run-specific test parameters",
    )
    parser.addoption(
        "--broker-enabled", action="store_true", default=False,
        help="Enable broker purpose filtering for workload tests",
    )
    parser.addoption(
        "--mcp-enabled", action="store_true", default=False,
        help="Enable MCP purpose filtering for workload tests",
    )
    parser.addoption(
        "--vector-enabled", action="store_true", default=False,
        help="Enable vector purpose filtering for workload tests",
    )
    parser.addoption(
        "--amount-messages", action="store", type=int, default=1,
        help="Number of messages to simulate in workload tests",
    )
    parser.addoption(
        "--randomness", action="store", default="False",
        help="Whether to inject random faults in the workload scenario. Use True/False.",
    )
    
