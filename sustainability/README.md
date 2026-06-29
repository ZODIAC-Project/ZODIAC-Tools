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
- `mcp-client-service.zodiac.svc.cluster.local:9101`
- `mcp-server-service.zodiac.svc.cluster.local:9100`

That means the current setup can now measure both infrastructure-level process metrics and MCP-specific application metrics for `mcp-client` and `mcp-server`.

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

In the current cluster state, all three typical Kepler candidates returned no data, so the checked-in config uses currently available Prometheus metrics from `mcp-client` and `mcp-server` instead of energy metrics.

The checked-in SMA configuration currently measures:

- `mcp_client_cpu`
- `mcp_client_memory`
- `mcp_server_cpu`
- `mcp_server_memory`
- `mcp_client_chat_success_rate`
- `mcp_client_avg_request_duration`
- `mcp_client_tool_call_rate`
- `mcp_server_tool_call_rate`

## Files

- `sma-config.yaml`: ConfigMap with the SMA configuration
- `sma-job.yaml`: one-shot Job that runs SMA
- `sma-pvc.yaml`: persistent volume claim for generated SMA reports
- `sma-report-reader.yaml`: helper Pod to inspect or copy reports from the PVC

## First deployment flow

1. Adjust the PromQL queries in `sma-config.yaml` if you want to target other MCP metrics or if Kepler becomes available later.
2. Apply the ConfigMap:

```bash
kubectl apply -f sma-config.yaml
```

3. Create the PVC for persistent reports:

```bash
kubectl apply -f sma-pvc.yaml
```

4. Start the Job:

```bash
kubectl apply -f sma-job.yaml
```

5. Watch the Job:

```bash
kubectl logs -n zodiac job/sma-benchmark-run -f
```

The checked-in config writes reports to a relative directory `reports/` while the
container runs with `/output` as its working directory. That is necessary because
SMA rejects absolute report locations such as `/output`.

6. In parallel, run the benchmark scenarios from `ZODIAC-Tools/test-suite` so the MCP metrics actually change during the SMA observation window:

```bash
python3 benchmark/run_benchmark.py \
  --base-url http://localhost:8001 \
  --scenario baseline_no_tool \
  --scenario calculator_tool \
  --scenario rag_search \
  --repeats 5 \
  --warmup 1
```

## Reading the generated reports

Because the Job now writes to a PVC, the generated files remain available after
the Pod has finished. Since `kubectl cp` from a completed Job Pod is often not
possible, the simplest reliable flow is to mount the same PVC in a small helper
Pod:

```bash
kubectl apply -f sma-report-reader.yaml
kubectl exec -n zodiac sma-report-reader -- ls -R /output/reports
kubectl cp zodiac/sma-report-reader:/output/reports ./reports
```

Afterwards you can remove the helper Pod again:

```bash
kubectl delete pod sma-report-reader -n zodiac --ignore-not-found
```

If you want to rerun the benchmark cleanly, remove the old Job first:

```bash
kubectl delete job sma-benchmark-run -n zodiac --ignore-not-found
kubectl apply -f sma-job.yaml
```

## Important note

The current Job installs the Python package at runtime using `pip`. That is the fastest way to test the integration, but it requires outbound network access from the cluster. If that is blocked, the next step is to build a dedicated image and replace the container image and command in `sma-job.yaml`.
