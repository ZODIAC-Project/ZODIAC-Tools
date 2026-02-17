# Log Collection System

This directory contains a script for collecting logs from a main application pod for later analysis.

## Overview

The system consists of a single deployment that:
- Monitors the main application's log file
- Extracts `[ANALYSIS_LOG]` entries containing system prompts, user messages, and responses
- Stores them in JSON Lines format (limited to prevent disk bloat)
- Provides a way to later analyze which system and user prompts result in what responses

## Setup

### 1. Modify Main Application

Ensure your main application logs to a file on a persistent volume. For Python applications using the `logging` module:

```python
import logging

# Configure logging to file on shared volume
logging.basicConfig(
    filename='/shared/logs/app.log',
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
```

### 2. Create Persistent Volume

Create a PVC to store logs:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: logs-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi  # Adjust as needed
```

Mount this PVC in your main application pod at `/shared`.

### 3. Build Image

Build the Docker image:

```bash
docker build -f Dockerfile.fetcher -t your-registry/log-collector:latest .
docker push your-registry/log-collector:latest
```

### 4. Deploy

Update the image name in `deployment-collector.yaml`, then apply:

```bash
kubectl apply -f deployment-collector.yaml
```

## Configuration

Environment variables:
- `LOG_FILE`: Path to the main app's log file (default: `/shared/logs/app.log`)
- `STORAGE_FILE`: Where to store extracted logs (default: `/shared/analysis_logs.jsonl`)
- `POLL_INTERVAL`: Seconds between log checks (default: `1.0`)
- `MAX_LOGS`: Maximum number of logs to keep (default: `1000`)

## Log Format

The script expects logs in the format:
```
[INFO] [ANALYSIS_LOG] {"event": "analysis_log", "system_prompt": "...", "user_message": "...", "llm_response": "...", ...}
```

Only lines containing `[ANALYSIS_LOG]` are processed, and the JSON payload is extracted and stored for later analysis.

## Later Analysis

To analyze the collected logs, you can:
- Mount the PVC and read `/shared/analysis_logs.jsonl`
- Each line is a JSON object containing the analysis log data
- Use tools like `jq` or Python to query and analyze the data