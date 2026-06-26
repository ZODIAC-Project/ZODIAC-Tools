# Sustainability Measurement In ZODIAC

This directory contains a first deployment template for running the `sustainability-measurement-agent` as a Kubernetes Job in the `zodiac` namespace.

## Current cluster inputs

- Namespace: `zodiac`
- Prometheus: `http://prometheus.zodiac.svc.cluster.local:9090`
- Relevant workloads:
  - `mcp-client`
  - `mcp-server`
  - `rag-service`
  - `stream-manager`
  - `new-agent`

## Current scrape reality

Prometheus currently exposes only these `up` targets in the `zodiac` cluster:

- `agent-api.zodiac.svc.cluster.local:30086`
- `otel-collector.zodiac.svc.cluster.local:8889`

That means the first SMA smoke test can measure the `agent` job, but not yet `mcp-client`, `mcp-server`, or `rag-service`. To measure the MCP path end-to-end, those services need to be scraped first.

## Before the first run

Verify which energy metrics Kepler currently exposes in Prometheus. Common candidates are:

- `kepler_container_joules_total`
- `kepler_container_package_joules_total`
- `kepler_container_watts`

Quick checks:

```bash
kubectl port-forward -n zodiac svc/prometheus 9090:9090
```

Then open `http://localhost:9090` and try:

```promql
kepler_container_joules_total
```

If that returns nothing, try:

```promql
kepler_container_package_joules_total
```

In the current cluster state, all three typical Kepler candidates returned no data, so the checked-in config uses currently available process metrics for a first smoke test instead of energy metrics.

## Files

- `sma-config.yaml`: ConfigMap with the SMA configuration
- `sma-job.yaml`: one-shot Job that runs SMA

## First deployment flow

1. Adjust the PromQL query in `sma-config.yaml` if your Kepler metric name differs.
2. Apply the ConfigMap:

```bash
kubectl apply -f sma-config.yaml
```

3. Start the Job:

```bash
kubectl apply -f sma-job.yaml
```

4. Watch the Job:

```bash
kubectl logs -n zodiac job/sma-benchmark-run -f
```

5. In parallel, run the benchmark scenarios from `ZODIAC-Tools/test-suite`:

```bash
python3 benchmark/run_benchmark.py \
  --base-url http://localhost:8001 \
  --scenario baseline_no_tool \
  --scenario calculator_tool \
  --scenario rag_search \
  --repeats 5 \
  --warmup 1
```

## Important note

The current Job installs the Python package at runtime using `pip`. That is the fastest way to test the integration, but it requires outbound network access from the cluster. If that is blocked, the next step is to build a dedicated image and replace the container image and command in `sma-job.yaml`.
