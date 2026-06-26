# ZODIAC Test Suite

Testing connectivity, MCP tooling, MQTT usage, agent tasks and tracking model regression.  
1. Go to the test-suite directory: `cd test-suite`
2. Run all tests: `uv run pytest --tb=no -vv`

Benchmark scenarios for sustainability and performance measurements live in [benchmark/README.md](/Users/sonak/arbeit/zodiak/ZODIAC-Tools/test-suite/benchmark/README.md).

**Optional:**
- Run a specific test: `uv run pytest tests/test_mcp.py::test_tool_recognition --tb=no -vv`
