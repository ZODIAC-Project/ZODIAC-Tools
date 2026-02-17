#!/usr/bin/env python3
"""
Subscribe to a topic and print the retained (or latest) message then exit.

Usage:
  python fetch.py [--topic TOPIC] [--broker HOST] [--port PORT] [--timeout SECS]

Reads `TOPIC`, `BROKER`, `PORT` from local `env` file or environment variables.
"""
import os
import argparse
import threading
from pathlib import Path

import paho.mqtt.client as mqtt


def load_env(path: str = "env") -> dict:
    data = {}
    p = Path(path)
    if not p.exists():
        return data
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def main():
    env = load_env("env")
    parser = argparse.ArgumentParser(description="Fetch retained MQTT message")
    parser.add_argument("--topic", "-t", help="Topic to subscribe to")
    parser.add_argument("--broker", "-b", help="MQTT broker host")
    parser.add_argument("--port", "-p", type=int, help="MQTT broker port")
    parser.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for message")
    args = parser.parse_args()

    broker = args.broker or env.get("BROKER") or os.environ.get("BROKER") or "localhost"
    port = args.port or int(env.get("PORT", os.environ.get("PORT", 1883)))
    topic = args.topic or env.get("TOPIC") or os.environ.get("TOPIC") or "hivezodiac/test"

    msg_event = threading.Event()
    result = {}

    client = mqtt.Client()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(topic, qos=0)
        else:
            print(f"Connect failed with rc={rc}")
            msg_event.set()

    def on_message(client, userdata, msg):
        payload = msg.payload.decode(errors="replace")
        print("--- Message received ---")
        print(f"Topic: {msg.topic}")
        print(f"Payload: {payload}")
        print(f"QoS: {msg.qos}")
        print(f"Retained: {msg.retain}")
        result['topic'] = msg.topic
        result['payload'] = payload
        result['qos'] = msg.qos
        result['retain'] = msg.retain
        msg_event.set()

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker, port, 60)
    client.loop_start()

    # Wait for a message or timeout
    waited = msg_event.wait(timeout=args.timeout)
    client.loop_stop()
    client.disconnect()

    if not waited:
        print(f"No message received on topic '{topic}' within {args.timeout} seconds.")


if __name__ == "__main__":
    main()
