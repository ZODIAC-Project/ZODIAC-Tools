#!/usr/bin/env python3
"""
Log Collector Script (Kubernetes API Version)

This script tails a log file from a specific Kubernetes Pod using the API, 
parses lines containing [ANALYSIS_LOG], extracts the JSON payload, 
and stores them in a storage file.
"""

import json
import os
import re
import sys
from collections import deque
from pathlib import Path
from kubernetes import client, config, watch

# Configuration from Environment Variables
STORAGE_FILE = os.getenv('STORAGE_FILE', '/shared/analysis_logs.jsonl')
MAX_LOGS = int(os.getenv('MAX_LOGS', '1000'))
KUBE_NAMESPACE = os.getenv('KUBE_NAMESPACE', 'default')
KUBE_POD = os.getenv('KUBE_POD')
KUBE_CONTAINER = os.getenv('KUBE_CONTAINER') # Optional

def parse_analysis_log(line):
    """
    Parse a log line for ANALYSIS_LOG entries.
    Expected format: [INFO] [ANALYSIS_LOG] {"event": "analysis_log", ...}
    """
    if '[ANALYSIS_LOG]' not in line:
        return None

    # Find the JSON part after [ANALYSIS_LOG]
    match = re.search(r'\[ANALYSIS_LOG\]\s*(\{.*\})', line)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            print(f"Failed to parse JSON in line: {line.strip()}", file=sys.stderr)
            return None
    else:
        # Marker present but JSON not found — short, infrequent diagnostic
        snippet = line.strip()
        if len(snippet) > 200:
            snippet = snippet[:200] + '...'
        print(f"Found [ANALYSIS_LOG] but couldn't extract JSON: {snippet}", file=sys.stderr)
    return None

def save_logs(logs, storage_path):
    """Save the current deque of logs to the storage file (JSONL format)."""
    try:
        with open(storage_path, 'w', encoding='utf-8') as storage_file:
            for log in logs:
                json.dump(log, storage_file)
                storage_file.write('\n')
    except Exception as e:
        print(f"Error writing to storage file: {e}", file=sys.stderr)

def stream_pod_logs(namespace, pod, container=None):
    """
    Streams logs from the Kubernetes API.
    Replaces the need for the 'kubectl' binary.
    """
    # Initialize K8s client
    try:
        # Load config from the Pod's ServiceAccount
        config_source = 'in-cluster'
        config.load_incluster_config()
    except config.ConfigException:
        # Fallback for local development (uses ~/.kube/config)
        config.load_kube_config()
        config_source = 'kubeconfig'

    v1 = client.CoreV1Api()
    w = watch.Watch()

    print(f"--- Starting log stream for pod: {pod} (namespace: {namespace}) ---")
    print(f"Kubernetes config source: {config_source}")

    try:
        # read_namespaced_pod_log with follow=True acts like 'kubectl logs -f'
        for line in w.stream(
            v1.read_namespaced_pod_log,
            name=pod,
            namespace=namespace,
            container=container,
            follow=True,
            _request_timeout=None # Prevent the stream from timing out
        ):
            yield line
    except Exception as e:
        print(f"API Connection Error: {e}", file=sys.stderr)
    else:
        # If the generator exits normally
        print("Log stream ended normally.")

def main():
    storage_path = Path(STORAGE_FILE)
    
    # Ensure storage directory exists
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    if not KUBE_POD:
        print("Error: Environment variable 'KUBE_POD' is not set.", file=sys.stderr)
        sys.exit(1)

    # Load existing logs into memory (up to MAX_LOGS)
    logs = deque(maxlen=MAX_LOGS)
    if storage_path.exists():
        print(f"Loading existing logs from {STORAGE_FILE}...")
        with open(storage_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        print(f"Loaded {len(logs)} existing entries.")

    # Start processing the stream
    try:
        for line in stream_pod_logs(KUBE_NAMESPACE, KUBE_POD, KUBE_CONTAINER):
            analysis_data = parse_analysis_log(line)
            
            if analysis_data:
                logs.append(analysis_data)
                save_logs(logs, storage_path)
                
                event_type = analysis_data.get('event', 'unknown')
                print(f"Captured: {event_type} | Total in storage: {len(logs)}")
                
    except KeyboardInterrupt:
        print("\nStopping collector...")
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()