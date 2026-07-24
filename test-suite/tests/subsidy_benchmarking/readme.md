# Subsidy_tests

Automated test suite for the subsidy demo scenario and the PBAC (Purpose-Based
Access Control) mechanisms behind it — broker-level purpose filtering,
RAG purpose isolation, MCP tool-call purpose isolation, and agent-level
purpose routing.
---

## Folder structure

```
Subsidy_tests/
├── conftest.py              # shared fixtures for ALL tests in this suite
├── shared/
│   ├── prompts.py           # reusable agent instruction-text builders
│   ├── matrix.py            # the V/B/M PBAC combination matrix
│   ├── parsing.py           # shared agent-response parsing/validation
│   └── instrumentation.py   # operation counters (messages, tool calls)
├── purpose_isolation/       # mechanism tests: does PBAC enforce correctly?
│   ├── conftest.py          # matrix-cell selection via --run-config
│   └── test_matrix.py
├── purpose_routing/         # agent tests: subscribe → receive → act correctly?
│   ├── test_reduced.py
│   └── test_n_agent.py
├── logic/                   # business-logic tests: is the agent's reasoning correct?
│   ├── data.py              # all test datasets in one place
│   ├── test_customer_subsidy_matching.py   # clean 2x2 match
│   ├── test_no_match.py                    # agent must not force a match
│   ├── test_distractor.py                  # keyword-similar but wrong recipient
│   ├── test_multi_message.py               # accumulates data across 2 messages
│   └── test_scale.py                       # correctness at N=15 pairs
├── workload/                # sustained usage simulation, for energy measurement
│   ├── data.py               # fixed, versioned customer/subsidy dataset
│   └── test_week_simulation.py
└── legacy/                  # original demo tests, kept as-is
    ├── test_subsidy_demo.py
    ├── test_subsidy_demo_with_business_purposes.py
    ├── test_subsidy_demo_with_wrong_purpose.py
    └── test_subsidy_seperate.py
```

Every subfolder automatically inherits the fixtures in the top-level
`conftest.py` and `test/helper` — you don't need to import or re-declare anything to get
`topic_factory`, `purpose_factory`, or automatic agent cleanup.

---
## File descriptions

### `conftest.py`
Shared fixtures for all tests in this suite.

**Always use `topic_factory` / `purpose_factory` instead of hardcoding
topic or purpose strings.** This is what makes tests safe to run
concurrently or repeatedly without leftover-message interference.

### `shared/prompts.py`
Builds agent instruction text.

- `build_routing_task(operation_desc, result_topic)` — for
  purpose-routing tests (simple, checkable task + explicit output topic).
- `build_instruction(base_task, vector_purpose, mcp_purpose)` — for
  purpose-isolation tests (adds RAG/MCP purpose instructions and an
  `ACCESS_DENIED` convention for rejected access).

If an agent's output format turns out unreliable in practice, fix the
wording here rather than adjusting assertions per test file.

### `shared/matrix.py`
The 8-cell Vector-DB / Broker / MCP (`V/B/M`) PBAC combination matrix,
as a reusable `pytest.mark.parametrize` list. Used by
`purpose_isolation/test_matrix.py` so all 8 combinations are covered by
one parametrized test instead of 8 near-duplicate functions.

### `shared/parsing.py`

parse_match_response(raw) and matches_to_dict(matches) — shared JSON parsing/validation for all logic/ tests, including stripping markdown code fences if the agent wraps its output. Fix agent-output edge cases here once, rather than in every logic test file.

### `shared/instrumentation.py`

RunCounters — a small thread-safe counter for messages sent/received and tool calls during a test run. Used by workload/ to report operation counts alongside energy measurements, since raw energy numbers aren't comparable across runs unless normalized by (or checked against) how much actual work happened.

---

## Test folders

### `purpose_isolation/` — mechanism tests
**Question answered:** does PBAC actually get enforced at the
broker/RAG/MCP layer, in every combination of which layers are "on"?

`test_matrix.py` runs the same isolation check across all 8 `V/B/M`
combinations. If this fails, the platform's PBAC enforcement is broken.

### `purpose_routing/` — agent routing tests
**Question answered:** can a agent correctly subscribe to a topic
with a given purpose, receive a message, and act on it — and does an
agent with the *wrong* purpose correctly receive nothing?

- `test_reduced.py` — smallest case: 2 agents, one allowed, one blocked.
- `test_n_agent.py` — same check scaled to N agents with randomized
  allowed/blocked assignment, to catch issues that only appear with
  multiple concurrent subscriptions.

### `logic/` — business logic tests
**Question answered:** given correct data access, does the agent
perform the actual task correctly?

`test_customer_subsidy_matching.py` seeds known customers/subsidies
into RAG and checks the agent's matching output against a known-correct
answer, by ID — not by fuzzy/LLM-judged comparison

### `workload/` — sustained usage simulation

Question answered: what happens under realistic, prolonged usage, and how much actual work (messages, tool calls) did that take? Primarily for energy measurement.

- **Structural parameters are explicit**, via run_config YAML (n_events, event_interval_seconds, subagent count) 
- **The LLM's semantic output is NOT pinned** — only workload shape is controlled. Actual operation counts are measured via shared/instrumentation.py and printed as WORKLOAD_COUNTERS::{...json...} for the external caller to pick up.
- **When comparing energy across runs/configs, normalize by operation count** (energy per tool call, not just total energy) rather than assuming equal work happened just because the scenario description was the same.
---
## Focus (isolate) tests via markers

Registered in pyproject.toml (or pytest.ini):

``` toml
[tool.pytest.ini_options]
markers = [
    "model_quality: agent reasoning/logic correctness",
    "access_control: PBAC enforcement and its overhead",
    "workload: sustained-usage energy simulation",
]
```

Tests are tagged with `@pytest.mark.<name>`, e.g. `logic/` tests get `@pytest.mark.model_quality`, purpose_isolation/ tests get `@pytest.mark.access_control`. Run a focused subset with:

``` bash
pytest -m access_control
pytest -m model_quality
pytest -m workload
```
---

## Adding a new test scenario

1. **Does it test a mechanism (broker/RAG/MCP in isolation)?** →
   add to `purpose_isolation/`, or a new sibling folder if it's a
   different mechanism entirely.
2. **Does it test whether agents subscribe/receive/act correctly?** →
   add to `purpose_routing/`.
3. **Does it test whether an agent's reasoning/output is correct?** →
   add to `logic/`.
4. **None of the above — genuinely new category?** → create a new
   top-level folder with its own `__init__.py`. It automatically
   inherits `conftest.py`'s fixtures; add a folder-local `conftest.py`
   only if the new category needs fixtures nothing else uses.

Rules of thumb for any new test:

- Always use `topic_factory` / `purpose_factory` — never hardcode
  topics or purposes.
- Never call MQTT/HTTP APIs directly — add a `helper.py` function if
  one doesn't exist yet.
- Prefer deterministic assertions (IDs, exact numbers, fixed markers)
  over `fuzzy_assert`. Fuzzy/LLM-judged assertions make it hard to tell
  a real bug from an LLM having an off day.
- If your test needs a new prompt pattern, add a builder to
  `shared/prompts.py` rather than writing raw prompt strings inline.
- Don't rely on `delete_all_agents()` yourself — it runs automatically
  after every test via the autouse `cleanup_agents` fixture.

---

## Running tests

```bash
# everything
pytest Subsidy_tests

# one category
pytest Subsidy_tests/purpose_routing

# one file
pytest Subsidy_tests/purpose_routing/test_reduced.py -v -s

# with an external run-config (e.g. from the sma service)
pytest Subsidy_tests/purpose_routing --run-config=configs/example.yaml --junitxml=results/run.xml
```

`-s` is useful when debugging agent output, since it shows print/log
output that pytest normally captures.

### Run-config YAML

Some values can be
supplied externally instead of hardcoded

```yaml
run_id: "example-run-001"
n_agents: 20                          # purpose_routing/test_n_agent.py
timeout_seconds: 45
matrix_cells: ["VBM-FFF", "VBM-TTT"]  # purpose_isolation/
n_events: 50                          # workload/test_week_simulation.py
event_interval_seconds: 2             # workload/test_week_simulation.py
```

If no `--run-config` is passed, tests fall back to their local-dev
defaults, so the suite still runs standalone without any YAML file.

---

## Known open items

- RAG kann nichts von den tests aus verändert werden. Momentan nicht schlimm aber evtl. nützlich 
