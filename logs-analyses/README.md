# Log Collection System

This directory contains a script for collecting logs from a main application pod for later analysis.

## Overview

The system consists of a single deployment that:
- Monitors the main application's log file
- Extracts `[ANALYSIS_LOG]` entries containing system prompts, user messages, and responses
- Stores them in JSON Lines format (limited to prevent disk bloat)
- Provides a way to later analyze which system and user prompts result in what responses

## Setup
```

Mount this PVC in your main application pod at `/shared`.

### 3. Build Image

Build the Docker image:

```bash
docker build -f Dockerfile -t mathiskae/log-collector:latest .
docker push mathiskae/log-collector:latest
```

```bash
minikube image load mathiskae/log-collector:latest
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

## Image tagging script
./image-tagging-script/image_tagging_script.sh --token-file image-tagging-script/token-file.txt -f logs-analyses/Dockerfile git.tu-berlin.de:5000/zodiac/zodiac-meta/log-collector logs-analyses/deployment-collector.yaml

./image-tagging-script/image_tagging_script.sh --token-file image-tagging-script/token-file.txt -p linux/amd64 -f logs-analyses/Dockerfile git.tu-berlin.de:5000/zodiac/zodiac-meta/log-collector logs-analyses/deployment-collector.yaml