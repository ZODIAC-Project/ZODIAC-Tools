# Structurizr Workspace

The ZODIAC architecture model lives in [workspace.dsl](./workspace.dsl).

## Run locally

```bash
cd ZODIAC-Tools/architecture/structurizr
docker compose up -d
```

Then open:

```text
http://localhost:8082
```

## What is covered

- system context for the overall ZODIAC platform
- container view for the main runtime services
- purpose-aware MQTT broker and PBAC extension
- MCP client/server split
- agent API and stream manager
- RAG service with embedded Chroma store
- observability and external LLM dependencies

## Notes

- The model is derived from the current codebase, Helm chart, and service READMEs.
- The Chroma store is modeled as an embedded data store owned by the RAG service, not as a standalone deployable service.
- The HivePBAC extension is modeled explicitly because it is architecturally important even though it runs inside the broker process.

## Suggested next refinements

- add a deployment view for the Kubernetes namespace `zodiac`
- add a dynamic view for the subsidy demo flow
- add a separate view focused on PBAC and purpose propagation
