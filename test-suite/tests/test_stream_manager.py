import time
import uuid
import requests

from .helper import (
    STREAM_MANAGER_URL,
    AGENT_URL,
    create_agent,
    reset,
    reserve_topic,
    publish_message,
    client,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_TOPIC         = f"zodiac/test/debug/{int(time.time()*1000)}"
PURPOSE_ALLOWED    = "stream-manager-test-allowed"
PURPOSE_NOT_ALLOWED = "stream-manager-test-denied"

MESSAGE_TIMEOUT    = 10.0   # seconds to wait for message to appear in agent history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_agent_history(agent_id: str, limit: int = 80) -> list:
    response = requests.get(f"{AGENT_URL}/agents/{agent_id}/history", params={"limit": limit})
    assert response.status_code == 200, (
        f"Failed to fetch history for agent {agent_id}: {response.text}"
    )
    data = response.json()
    if isinstance(data, dict):
        return data.get("history", [])
    return data

def cleanup_session(agent_id: str):
    requests.post(f"{STREAM_MANAGER_URL}/cleanup/{agent_id}", timeout=5.0)


def wait_for_message_in_history(agent_id: str, expected_payload: str, timeout: float = MESSAGE_TIMEOUT) -> bool:
    """Poll agent history until expected_payload appears or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = get_agent_history(agent_id)
        for entry in history:
            content = entry.get("content", "") or entry.get("text", "") or str(entry)
            if expected_payload in content:
                return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestStreamManagerForwarding:

    def setup_method(self):
        """Reset broker purpose settings and reserve test topic before each test."""
        reset()
        client.set_purpose_setting("filter_on_subscribe", True)
        client.set_purpose_setting("filter_on_publish", False)
        client.set_purpose_setting("filter_hybrid", False)
        reserve_topic(TEST_TOPIC, aip=[PURPOSE_ALLOWED])
        time.sleep(0.5)

    def teardown_method(self):
        pass  # broker reset happens in setup_method of the next test

#----------------------------------------------------------------------------

    def test_allowed_purpose_receives_messages(self):
        """An agent subscribed with an allowed purpose receives published messages."""
        agent_id = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )
        
        time.sleep(MESSAGE_TIMEOUT)
    
        response = requests.get(f"{STREAM_MANAGER_URL}/subscriptions/{agent_id}", timeout=5.0)
        print(f"Subscriptions for agent {agent_id}: {response.json()}")
        assert response.status_code == 200, (
            f"Failed to fetch subscriptions for agent {agent_id}: {response.text}"
        )   

        test_payload = f"This is a test message with allowed purpose: {uuid.uuid4().hex[:8]}. Dont do anything with it."
        # expects (topic: str, payload: str, qos=0, retain=False)
        response = publish_message(TEST_TOPIC, test_payload)

        assert wait_for_message_in_history(agent_id, test_payload), (
            f"Agent with allowed purpose '{PURPOSE_ALLOWED}' should have received "
            f"'{test_payload}' but it did not appear in history."
        )

        cleanup_session(agent_id)
    
    def test_multiple_messages_are_forwarded_to_agent(self):
        """Multiple messages published in sequence all reach the subscribed agent."""
        agent_id = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )

        payloads = [f"msg-{uuid.uuid4().hex[:8]}" for _ in range(3)]
        for payload in payloads:
            publish_message(TEST_TOPIC, payload)
            time.sleep(0.2)

        for payload in payloads:
            assert wait_for_message_in_history(agent_id, payload), (
                f"Expected payload '{payload}' to appear in agent {agent_id} history "
                f"within {MESSAGE_TIMEOUT}s, but it did not."
            )

        cleanup_session(agent_id)

    def test_denied_purpose_does_not_receive_messages(self):
        """An agent subscribed with a denied purpose does not receive published messages."""
        agent_id = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_NOT_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )

        test_payload = f"denied-purpose-{uuid.uuid4().hex[:8]}"
        publish_message(TEST_TOPIC, test_payload)

        # Wait the full timeout and assert payload never appears
        appeared = wait_for_message_in_history(agent_id, test_payload)
        assert not appeared, (
            f"Agent with denied purpose '{PURPOSE_NOT_ALLOWED}' should NOT have received "
            f"'{test_payload}' but it appeared in history."
        )

        cleanup_session(agent_id)

    def test_allowed_receives_denied_does_not(self):
        """With two agents on the same topic, only the one with the allowed purpose gets messages."""
        agent_allowed = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )
        agent_denied = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_NOT_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )

        test_payload = f"filter-test-{uuid.uuid4().hex[:8]}"
        publish_message(TEST_TOPIC, test_payload)

        assert wait_for_message_in_history(agent_allowed, test_payload), (
            f"Agent with allowed purpose should have received '{test_payload}' but did not."
        )
        assert not wait_for_message_in_history(agent_denied, test_payload), (
            f"Agent with denied purpose should NOT have received '{test_payload}' but it did."
        )

        cleanup_session(agent_allowed)
        cleanup_session(agent_denied)