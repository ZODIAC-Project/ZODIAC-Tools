## Test Notes

Jeder Testlauf wählt **einmal** einen Branch (per `--branch` )
und wiederholt ihn `--amount-messages`-mal mit derselben PBAC-Konfiguration.
Für unterschiedliche Branches/Konfigurationen den Test mehrfach mit
`--amount-messages=1` starten.

## Branch Selection

- `--branch=<name>` gesetzt -> genau dieser Branch läuft, `--randomness` wird ignoriert.
- Kein `--branch`, `--randomness=True` -> zufällige Wahl aus allen 8 Branches.
- Kein `--branch`, `--randomness=False` (Default) -> `passthrough`.

Verfügbare Branches: `no-fault`, `passthrough`, `broker`, `broker-success`,
`mcp`, `mcp-success`, `vector`, `vector-success`.

### Branch summary

- **no-fault**: alle PBAC-Layer aktiv und korrekt konfiguriert; voller Flow muss durchlaufen.
- **passthrough**: alle PBAC-Layer aus ; voller Flow muss trotzdem durchlaufen.
- **broker / broker-success**: Agent 1 subscribt mit falschem / korrektem Purpose -> Nachricht wird blockiert / kommt an.
- **mcp / mcp-success**: Agent ruft Tool mit unzulässigem / zulässigem Purpose auf -> Tool-Call wird verweigert / ausgeführt.
- **vector / vector-success**: `search_knowledge_base` mit falschem / korrektem `vector_purpose` -> `ACCESS_DENIED_PURPOSE_ISSUE` auf dem Issue-Topic / erfolgreicher RAG-Treffer.

## Commands

```bash
# PASSTHROUGH (alle Layer aus, muss durchlaufen)
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=passthrough --amount-messages=1

# NO-FAULT (alle Layer aktiv, korrekt konfiguriert, muss durchlaufen)
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=no-fault --amount-messages=1

# BROKER-FAULT / BROKER-SUCCESS
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=broker --amount-messages=1
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=broker-success --amount-messages=1

# MCP-FAULT / MCP-SUCCESS
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=mcp --amount-messages=1
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=mcp-success --amount-messages=1

# VECTOR-FAULT / VECTOR-SUCCESS
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=vector --amount-messages=1
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --branch=vector-success --amount-messages=1

# Zufällige Branch-Wahl über mehrere Nachrichten
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --randomness=True --amount-messages=5
```