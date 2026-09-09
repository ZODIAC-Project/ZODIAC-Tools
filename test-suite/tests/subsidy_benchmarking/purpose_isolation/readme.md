## Test Notes
Use this test to verify every workload branch once on its own and then repeat the same branch a few times to catch cleanup or isolation issues.

If you start the test with more then one message (`--amount-messages > 1`), the test will run with the same PBAC configuration that was selected for the first message. If you want to run the test with differend branches or a differend PBAC configuration, just start the test multiple times with `--amount-messages=1`.

## Branch Selection
`test_workload_purpose_isolation_scenario` now behaves like this:

- `--randomness=False` -> always run the no-fault path.
- `--randomness=True` and no BPAC branch flag set -> pick one branch at random, including the no-fault PBAC-variation branch.
- `--randomness=True` and one branch flag set -> use that branch and ignore the others.

Set at most one of these flags when you want a specific branch:

- `--broker-enabled` -> broker fault branch
- `--mcp-enabled` -> MCP fault branch
- `--vector-enabled` -> vector fault branch

If none of those are set and `--randomness=True`, the test randomly chooses between:

- no-fault PBAC-variation branch
- broker fault branch
- MCP fault branch
- vector fault branch
- passthrough branch

## Workload flow diagram

```mermaid
flowchart TD
    classDef ok fill:#d9f7e8,stroke:#2e7d32,stroke-width:2px,color:#1b3b2f;
    classDef fail fill:#fde7e9,stroke:#c62828,stroke-width:2px,color:#4b1d1d;
    classDef neutral fill:#eef3ff,stroke:#4863a0,stroke-width:2px,color:#21314d;

    A[Start workload test] --> B{randomness enabled?}

    B -- No --> N[Deterministic path
full flow must succeed]:::ok
    B -- Yes --> C{Explicit fault flag set?}

    C -- Yes --> D{Which flag?}
    D -- broker --> B1[Broker fault]:::fail
    D -- mcp --> M1[MCP fault]:::fail
    D -- vector --> V1[Vector fault]:::fail

    C -- No --> R[Random branch selection
no-fault / broker / mcp / vector / passthrough]:::neutral

    B1 --> B2[Wrong broker purpose
message blocked before agent 1]:::fail
    M1 --> M2[Wrong MCP purpose
send_email is denied]:::fail
    V1 --> V3[Wrong vector purpose
ACCESS_DENIED_PURPOSE_ISSUE]:::fail

    R --> N2[No-fault]:::ok
    R --> B3[Broker fault]:::fail
    R --> M3[MCP fault]:::fail
    R --> V3b[Vector fault]:::fail
    R --> P[Passthrough]:::ok

    N2 --> N3[Full PBAC flow succeeds]:::ok
    B3 --> B4[Message never reaches Agent 1]:::fail
    M3 --> M4[Agent 1 receives msg, but no email call]:::fail
    V3b --> V4[Issue topic receives denial]:::fail
    P --> P2[All PBAC layers off
full flow succeeds]:::ok
```

### Branch summary

- No-fault: everything is allowed; full flow should succeed.
- Broker fault: agent subscribes with a wrong purpose so the message is blocked before reaching it.
- MCP fault: agent is allowed to receive the message but uses a forbidden purpose for the tool call, so `send_email` must not be invoked.
- Vector fault: vector search is denied due to a mismatched state/purpose and raises an issue on the issue topic.
- Passthrough: all PBAC layers are disabled; the full workload runs as a plain success path.

## TODOs
The no-fault path now randomizes PBAC activation/deactivation once per run when `--randomness=True` and no explicit fault branch is selected.

## Commands

No-fault path, repeated 1 time:

```sh
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
  --broker-enabled --mcp-enabled --vector-enabled \
  --amount-messages=1 --randomness=False
```

Broker fault branch, repeated 1 time:

```sh
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
  --broker-enabled \
  --amount-messages=1 --randomness=True
```

MCP fault branch, repeated 1 time:

```sh
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
  --mcp-enabled \
  --amount-messages=1 --randomness=True
```

Vector fault branch, repeated 1 time:

```sh
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
  --vector-enabled \
  --amount-messages=1 --randomness=True
```

Random branch selection, repeated 1 time:

```sh
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s \
  --amount-messages=1 --randomness=True
```

