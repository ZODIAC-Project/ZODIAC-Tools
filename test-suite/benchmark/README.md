# Benchmark Setup

This directory contains a small benchmark harness for reproducible `/chat` requests against the `mcp-client` service.

## Files

- `scenarios.json`: fixed benchmark scenarios
- `run_benchmark.py`: executes warmup and measured runs, then writes a JSON report

## Recommended first scenarios

- `baseline_no_tool`: LLM-only baseline with `no_tools=true`
- `calculator_tool`: cheap MCP tool call
- `rag_search`: retrieval-heavy scenario through the RAG service
- `mqtt_subscribe`: live subscription setup
- `agent_subscribe`: event-based agent creation plus subscription

## Example usage

Against a local port-forward:

```bash
python3 benchmark/run_benchmark.py \
  --base-url http://localhost:8001 \
  --repeats 5 \
  --warmup 1
```

Against the NodePort from outside the cluster:

```bash
python3 benchmark/run_benchmark.py \
  --base-url http://130.149.158.133:30084 \
  --scenario baseline_no_tool \
  --scenario rag_search
```

## Notes for sustainability measurements

- Keep the same model, prompt, and scenario file across runs.
- Change only one factor at a time, for example model size or `memory_window`.
- Run each scenario multiple times because tool and network latency vary.
- For MQTT scenarios, keep the publisher behavior stable during every measurement window.

## Output

The script writes a JSON report with per-run durations, status codes, and returned responses. This can later be joined with measurements from the sustainability agent by timestamp and scenario name.
