#!/usr/bin/env python3
"""
Publish a retained MQTT message to topic from `env` file (or env vars / defaults).

Usage:
  python send.py --message "hello" [--topic TOPIC] [--broker HOST] [--port PORT] [--qos N]

This script prefers values from a local `env` file with lines like `KEY=VALUE`.
"""
import os
import time
import argparse
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

    parser = argparse.ArgumentParser(description="Publish retained MQTT message")
    parser.add_argument("--message", "-m", required=True, help="Message payload to publish")
    parser.add_argument("--topic", "-t", help="Topic to publish to (overrides env)")
    parser.add_argument("--broker", "-b", help="MQTT broker host")
    parser.add_argument("--port", "-p", type=int, help="MQTT broker port")
    parser.add_argument("--qos", type=int, default=0, choices=[0, 1, 2], help="QoS level")
    args = parser.parse_args()

    broker = args.broker or env.get("BROKER") or os.environ.get("BROKER") or "localhost"
    port = args.port or int(env.get("PORT", os.environ.get("PORT", 1883)))
    topic = args.topic or env.get("TOPIC") or os.environ.get("TOPIC") or "hivezodiac/test"

    client = mqtt.Client()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to {broker}:{port}")
        else:
            print(f"Connect failed with rc={rc}")

    client.on_connect = on_connect

    client.connect(broker, port, 60)
    client.loop_start()

    print(f"Publishing retained message to topic: {topic}")
    (rc, mid) = client.publish(topic, payload=args.message, qos=args.qos, retain=True)
    # small wait to allow broker to accept retained message
    time.sleep(1.0)
    client.loop_stop()
    client.disconnect()
    print("Published (retained=True).")


if __name__ == "__main__":
    main()
