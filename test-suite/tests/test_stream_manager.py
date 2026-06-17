import sys
import time
import uuid
import requests
import pytest

from .helper import (
    STREAM_MANAGER_URL,
    AGENT_URL,
    create_agent,
    reserve_topic,
    publish_message,
    client,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_TOPIC         = "zodiac/test/stream-manager"
PURPOSE_ALLOWED    = "stream-manager-test-allowed"
PURPOSE_NOT_ALLOWED = "stream-manager-test-denied"

SUBSCRIBE_TIMEOUT  = 3.0   # seconds to wait for broker subscription to be active
MESSAGE_TIMEOUT    = 5.0   # seconds to wait for message to appear in agent history


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


def subscribe_agent_to_stream_manager(agent_id: str, topic: str, purpose: str):
    payload = {"session_id": agent_id, "topic": topic, "purpose": purpose}
    resp = requests.post(f"{STREAM_MANAGER_URL}/subscribe", json=payload, timeout=5.0)
    assert resp.status_code == 200, (
        f"Stream manager subscribe failed: {resp.text}"
    )


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
    
    def test_small_test(self):
        agent_id = "3d1c63c9-5b88-4e7a-bb64-bd8884d6174d"  # from the failed test
        history = requests.get(f"{AGENT_URL}/agents/{agent_id}/history", params={"limit": 80})
        history_json = history.json()
        print(history_json, file=sys.stderr, flush=True)
        assert False, f"Agent history: {history_json}"

    def setup_method(self):
        """Reset broker purpose settings and reserve test topic before each test."""
        client.set_purpose_setting("filter_on_subscribe", True)
        client.set_purpose_setting("filter_on_publish", False)
        client.set_purpose_setting("filter_hybrid", False)
        reserve_topic(TEST_TOPIC, aip=[PURPOSE_ALLOWED])
        time.sleep(0.5)

    def teardown_method(self):
        pass  # broker reset happens in setup_method of the next test

    def test_message_is_forwarded_to_agent(self):
        """A message published to a topic reaches the subscribed agent via the stream manager."""
        agent_id = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )

        subscribe_agent_to_stream_manager(agent_id, TEST_TOPIC, PURPOSE_ALLOWED)
        time.sleep(SUBSCRIBE_TIMEOUT)

        # manually post what the stream manager would post
        test_payload = f"forwarding-test-{uuid.uuid4().hex[:8]}"
        manual_forward = requests.post(
            f"{AGENT_URL}/agents/{agent_id}",
            json={"datapoint": test_payload, "topic": TEST_TOPIC, "timestamp": "2026-01-01T00:00:00"}
        )
        time.sleep(2)
        
        assert wait_for_message_in_history(agent_id, test_payload), (
            f"Expected payload '{test_payload}' to appear in agent {agent_id} history "
            f"within {MESSAGE_TIMEOUT}s, but it did not."
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

        subscribe_agent_to_stream_manager(agent_id, TEST_TOPIC, PURPOSE_ALLOWED)
        time.sleep(SUBSCRIBE_TIMEOUT)

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

    def test_allowed_purpose_receives_messages(self):
        """An agent subscribed with an allowed purpose receives published messages."""
        agent_id = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_ALLOWED,
            memoryWindow=20,
            listenTopic=TEST_TOPIC,
        )

        subscribe_agent_to_stream_manager(agent_id, TEST_TOPIC, PURPOSE_ALLOWED)
        time.sleep(SUBSCRIBE_TIMEOUT)

        test_payload = f"allowed-purpose-{uuid.uuid4().hex[:8]}"
        publish_message(TEST_TOPIC, test_payload)

        assert wait_for_message_in_history(agent_id, test_payload), (
            f"Agent with allowed purpose '{PURPOSE_ALLOWED}' should have received "
            f"'{test_payload}' but it did not appear in history."
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

        subscribe_agent_to_stream_manager(agent_id, TEST_TOPIC, PURPOSE_NOT_ALLOWED)
        time.sleep(SUBSCRIBE_TIMEOUT)

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
        )
        agent_denied = create_agent(
            runOnce=False,
            text="You are a passive listener. Do not do anything, just receive messages.",
            purpose=PURPOSE_NOT_ALLOWED,
            memoryWindow=20,
        )

        subscribe_agent_to_stream_manager(agent_allowed, TEST_TOPIC, PURPOSE_ALLOWED)
        subscribe_agent_to_stream_manager(agent_denied, TEST_TOPIC, PURPOSE_NOT_ALLOWED)
        time.sleep(SUBSCRIBE_TIMEOUT)

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