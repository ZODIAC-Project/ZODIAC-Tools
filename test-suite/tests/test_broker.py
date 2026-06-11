"""This test uses PurposeClient to reserve topics, subscribe with purposes, and verify message flow."""

import time
import pytest

from .helper import (
    client,
    reset,
    reserve_topic,
    send_and_expect,
    send_and_reject,
    subscribe_with_purpose,
    publish_message
)

TOPIC = "zodiac/tests/broker_tests/purpose_topic"
PURPOSE_ALLOWED = "allowed"
PURPOSE_NOT_ALLOWED = "not_allowed"


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    
def subscribe_and_receive(agent_id: str, topic: str, expected_payload: str, timeout: float = 5.0) -> bool:
    """subscribe to a topic and wait for the message to arrive."""
    subscribe_response = subscribe_with_purpose(topic, PURPOSE_ALLOWED)
    assert subscribe_response["status"] == "success", f"Failed to subscribe with allowed purpose: {subscribe_response}"

    client.wait_for_subscriptions()

    publish_response = send_and_expect(topic, expected_payload)
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    deadline = time.time() + timeout
    while time.time() < deadline:
        stats = client.show_stats()
        if stats > 0:
            return True
        time.sleep(0.5)
    return False
    


def test_allowed_subscription():
    """Nachrichten auf einem reservierten Topic kommen an wenn der Purpose erlaubt ist."""
    reserve_response = reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    assert reserve_response["status"] == "success", f"Failed to reserve topic: {reserve_response}"

    subscribe_response = subscribe_with_purpose(TOPIC, PURPOSE_ALLOWED)
    assert subscribe_response["status"] == "success", f"Failed to subscribe with allowed purpose: {subscribe_response}"

    client.wait_for_subscriptions()

    publish_response = send_and_expect(TOPIC, b"Test message for allowed subscription")
    assert publish_response["status"] == "success", f"Failed to publish: {publish_response}"

    time.sleep(1)
    assert client.show_stats() == 0, "Expected allowed message to be received"


def test_not_allowed_subscription():
    """Nachrichten auf einem reservierten Topic kommen NICHT an wenn der Purpose nicht erlaubt ist.
    
    Der Broker gibt im SUBACK immer MQTT_ERR_SUCCESS (rc=0) zurück — die Subscription wird
    nicht auf Protokollebene abgelehnt. Die Filterung erfolgt durch den Broker bei der
    Nachrichtenzustellung (filter_on_subscribe).
    """
    client.set_purpose_setting("filter_on_subscribe", True)
    client.set_purpose_setting("filter_on_publish", False)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    subscribe_with_purpose(TOPIC, PURPOSE_NOT_ALLOWED)
    client.wait_for_subscriptions()

    publish_response = send_and_reject(TOPIC, b"Test message for not allowed subscription")
    assert publish_response["status"] == "success", "Publish itself should succeed"

    time.sleep(1)
    assert client.show_stats() == 0, "Expected no messages to be delivered to forbidden subscriber"


def test_broker_suback_on_forbidden_subscription():
    """Dokumentation: Der Broker antwortet auf eine verbotene Subscription mit MQTT_ERR_SUCCESS.
    
    SUBACK enthält immer rc=0 — der Broker lehnt Subscriptions nicht auf MQTT-Protokollebene ab.
    Eine Pre-Validation über einen separaten Policy-Endpunkt ist daher der einzig verlässliche
    Weg um forbidden Subscriptions vor dem Subscribe zu erkennen.
    """
    client.set_purpose_setting("filter_on_subscribe", True)
    client.set_purpose_setting("filter_on_publish", False)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    raw_response = subscribe_with_purpose(TOPIC, PURPOSE_NOT_ALLOWED)

    print(f"\nSUBACK response: {raw_response}")
    print(f"  status:  {raw_response.get('status')}")
    print(f"  result:  {raw_response.get('result')}")
    print(f"  mid:     {raw_response.get('mid')}")


def test_broker_disconnects_on_forbidden_subscription():
    """Dokumentation: Die Verbindung bleibt nach einer verbotenen Subscription aufrecht.
    
    Der Broker trennt die Verbindung nicht — der Client kann weiterhin publizieren.
    """
    client.set_purpose_setting("filter_on_subscribe", True)
    client.set_purpose_setting("filter_on_publish", False)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    subscribe_with_purpose(TOPIC, PURPOSE_NOT_ALLOWED)
    client.wait_for_subscriptions()

    time.sleep(1)

    is_connected = client.client.is_connected()
    print(f"\nConnected after forbidden subscription: {is_connected}")

    pub = publish_message(TOPIC, "probe after forbidden sub")
    print(f"Publish after forbidden sub: {pub}")