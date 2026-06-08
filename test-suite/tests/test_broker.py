"""This test uses PurposeClient to reserve topics, subscribe with purposes, and verify message flow."""

import logging
import time
import pytest

from .helper import client, reset, reserve_topic, send_and_expect, send_and_reject, subscribe_with_purpose

TOPIC = "zodiac/tests/broker_tests/purpose_topic"
PURPOSE_ALLOWED = "allowed"
PURPOSE_NOT_ALLOWED = "not_allowed"


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield

def test_allowed_subscription():
    reserve_response = reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    assert reserve_response["status"] == "success", f"Failed to reserve topic: {reserve_response}"

    subscribe_response = subscribe_with_purpose(TOPIC, PURPOSE_ALLOWED)
    assert subscribe_response["status"] == "success", f"Failed to subscribe with allowed purpose: {subscribe_response}"

    client.wait_for_subscriptions()

    publish_response = send_and_expect(TOPIC, b"Test message for allowed subscription")
    assert publish_response["status"] == "success", f"Failed to publish expected message: {publish_response}"

    time.sleep(1)
    assert client.show_stats() == 0, "Expected allowed message to be received"

def test_not_allowed_subscription():
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
    """Was antwortet der Broker im SUBACK wenn der Purpose nicht erlaubt ist?"""
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
    """Wird die Verbindung nach einer abgelehnten Subscription getrennt?"""
    client.set_purpose_setting("filter_on_subscribe", True)
    client.set_purpose_setting("filter_on_publish", False)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(TOPIC, aip=[PURPOSE_ALLOWED])
    subscribe_with_purpose(TOPIC, PURPOSE_NOT_ALLOWED)
    client.wait_for_subscriptions()

    time.sleep(1)

    is_connected = client.client.is_connected()
    print(f"\nConnected after forbidden subscription: {is_connected}")
    
    # Kann der Client noch publizieren?
    try:
        pub = publish_message(TOPIC, "probe after forbidden sub")
        print(f"Publish after forbidden sub: {pub}")
    except Exception as e:
        print(f"Publish failed after forbidden sub: {e}")