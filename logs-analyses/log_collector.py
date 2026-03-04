#!/usr/bin/env python3
import json
import os
import re
import sys
from collections import deque
from pathlib import Path
from datetime import datetime
from kubernetes import client, config, watch
import time

STORAGE_FILE = os.getenv('STORAGE_FILE', '/shared/analysis_logs.jsonl')
HTML_FILE = os.getenv('HTML_FILE', '/shared/index.html')
MAX_LOGS = int(os.getenv('MAX_LOGS', '1000'))
KUBE_NAMESPACE = os.getenv('KUBE_NAMESPACE', 'default')
KUBE_POD = os.getenv('KUBE_POD')
KUBE_CONTAINER = os.getenv('KUBE_CONTAINER')
KUBE_LABEL_SELECTOR = os.getenv('KUBE_LABEL_SELECTOR')

# HTML Template for the Dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Zodiac Log Collector</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 20px; }}
        .badge {{ background: #007bff; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .live-pulse {{ width: 10px; height: 10px; background: #28a745; border-radius: 50%; display: inline-block; margin-right: 5px; animation: pulse 1.5s infinite; }}
        @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: fixed; }}
        th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #eee; overflow-wrap: break-word; }}
        th {{ background-color: #f8f9fa; text-transform: uppercase; font-size: 13px; color: #666; }}
        tr:hover {{ background-color: #f9f9f9; }}
        pre {{ background: #272822; color: #f8f8f2; padding: 10px; border-radius: 5px; font-size: 12px; overflow-x: auto; margin: 0; }}
        .timestamp {{ color: #888; font-family: monospace; font-size: 13px; }}
        .event-tag {{ background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Zodiac Analysis Logs</h1>
                <p style="color: #666; margin: 0;">Monitoring Pod: <strong>{pod}</strong></p>
            </div>
            <div style="text-align: right;">
                <span class="live-pulse"></span> <span style="font-size: 14px; font-weight: bold;">LIVE</span><br>
                <small>Last updated: {last_update}</small>
            </div>
        </header>
        <table>
            <thead>
                <tr>
                    <th style="width: 15%;">Time</th>
                    <th style="width: 15%;">Event</th>
                    <th style="width: 70%;">Data Payload</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

def parse_analysis_log(line):
    if '[ANALYSIS_LOG]' not in line:
        return None
    match = re.search(r'\[ANALYSIS_LOG\]\s*(\{.*\})', line)
    if match:
        try:
            data = json.loads(match.group(1))
            if 'timestamp' not in data:
                data['_captured_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return data
        except json.JSONDecodeError:
            return None
    return None

def update_dashboard(logs, pod):
    """Generates the HTML dashboard."""
    rows = ""
    for log in reversed(logs): 
        time = log.get('_captured_at') or log.get('timestamp') or "N/A"
        event = log.get('event', 'unknown')

        display_data = {k: v for k, v in log.items() if k != '_captured_at'}
        
        pretty_json = json.dumps(display_data, indent=2)
        rows += f"""
        <tr>
            <td class="timestamp">{time}</td>
            <td><span class="event-tag">{event}</span></td>
            <td><pre>{pretty_json}</pre></td>
        </tr>
        """
    
    html_content = HTML_TEMPLATE.format(
        pod=pod,
        last_update=datetime.now().strftime("%H:%M:%S"),
        rows=rows
    )
    
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)

def save_logs(logs, storage_path):
    with open(storage_path, 'w', encoding='utf-8') as f:
        for log in logs:
            f.write(json.dumps(log) + '\\n')

def stream_pod_logs(namespace, pod, container=None):
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    v1 = client.CoreV1Api()
    w = watch.Watch()
    try:
        for line in w.stream(v1.read_namespaced_pod_log, name=pod, namespace=namespace, 
                             container=container, follow=True, _request_timeout=None):
            yield line
    except Exception as e:
        print(f"API Error: {e}", file=sys.stderr)


def is_pod_ready(pod):
    """Return True if pod is Running and all container_statuses are ready."""
    if not pod:
        return False
    if pod.status.phase != 'Running':
        return False
    statuses = pod.status.container_statuses or []
    if not statuses:
        return False
    return all((getattr(s, 'ready', False) for s in statuses))


def wait_for_pod_by_label(v1, namespace, label_selector, timeout_seconds=None):
    """Return the name of a pod matching the label selector that is Running+Ready.
    First checks existing pods and returns the newest ready pod. If none found,
    it watches for pod events and returns the first that becomes ready.
    """
    try:
        pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
    except Exception as e:
        print(f"Failed listing pods for selector {label_selector}: {e}", file=sys.stderr)
        pods = []

    ready_pods = [p for p in pods if is_pod_ready(p)]
    if ready_pods:
        # prefer the most recently started/created
        ready_pods.sort(key=lambda p: p.status.start_time or p.metadata.creation_timestamp, reverse=True)
        return ready_pods[0].metadata.name

    w = watch.Watch()
    try:
        for event in w.stream(v1.list_namespaced_pod, namespace=namespace, label_selector=label_selector, timeout_seconds=timeout_seconds):
            pod = event.get('object')
            if is_pod_ready(pod):
                w.stop()
                return pod.metadata.name
    except Exception as e:
        print(f"Watch failed for selector {label_selector}: {e}", file=sys.stderr)
    return None


def main():
    storage_path = Path(STORAGE_FILE)
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine target pod
    target_pod = KUBE_POD

    if not target_pod and not KUBE_LABEL_SELECTOR:
        print("Error: Either KUBE_POD or KUBE_LABEL_SELECTOR must be set.")
        sys.exit(1)

    logs = deque(maxlen=MAX_LOGS)
    
    if storage_path.exists():
        with open(storage_path, 'r') as f:
            for line in f:
                try: logs.append(json.loads(line.strip()))
                except: continue

    print(f"Starting dashboard...")

    # If explicit pod given, use it. Otherwise resolve by label selector and watch for changes.
    if target_pod:
        update_dashboard(logs, target_pod)
        for line in stream_pod_logs(KUBE_NAMESPACE, target_pod, KUBE_CONTAINER):
            data = parse_analysis_log(line)
            if data:
                logs.append(data)
                save_logs(logs, storage_path)
                update_dashboard(logs, target_pod)
                print(f"Log stored and Dashboard updated. Total: {len(logs)}")
    else:
        # use label selector and watch for pods becoming ready; restart streaming on pod changes
        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            v1 = client.CoreV1Api()
        except Exception as e:
            print(f"Failed to initialize Kubernetes client: {e}", file=sys.stderr)
            sys.exit(1)

        while True:
            pod_name = wait_for_pod_by_label(v1, KUBE_NAMESPACE, KUBE_LABEL_SELECTOR)
            if not pod_name:
                print("No ready pod found yet, retrying in 2s...", file=sys.stderr)
                time.sleep(2)
                continue

            print(f"Selected pod {pod_name} for label {KUBE_LABEL_SELECTOR}")
            update_dashboard(logs, pod_name)

            try:
                for line in stream_pod_logs(KUBE_NAMESPACE, pod_name, KUBE_CONTAINER):
                    data = parse_analysis_log(line)
                    if data:
                        logs.append(data)
                        save_logs(logs, storage_path)
                        update_dashboard(logs, pod_name)
                        print(f"Log stored and Dashboard updated. Total: {len(logs)}")
            except Exception as e:
                print(f"Streaming error for pod {pod_name}: {e}", file=sys.stderr)

            print("Stream ended for pod, will attempt to find new pod (if any)...")
            time.sleep(1)

if __name__ == '__main__':
    main()