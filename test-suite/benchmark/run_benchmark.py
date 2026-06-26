#!/usr/bin/env python3

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_scenarios(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Scenario file must contain a JSON array.")
    return data


def post_json(url: str, payload: dict, timeout: float) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "zodiac-benchmark/1.0"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
        return response.status, json.loads(response_body)


def run_once(base_url: str, payload: dict, timeout: float) -> dict:
    started_at = time.time()
    status_code = None
    error = None
    response_json = None

    try:
        status_code, response_json = post_json(f"{base_url.rstrip('/')}/chat", payload, timeout)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        error = str(exc)

    finished_at = time.time()
    duration = round(finished_at - started_at, 3)

    return {
        "started_at_epoch": started_at,
        "duration_sec": duration,
        "status_code": status_code,
        "ok": error is None and status_code == 200,
        "payload": payload,
        "response": response_json,
        "error": error,
    }


def summarize(results: list[dict]) -> dict:
    durations = [entry["duration_sec"] for entry in results if entry["ok"]]
    success_count = sum(1 for entry in results if entry["ok"])
    failure_count = len(results) - success_count

    summary = {
        "runs": len(results),
        "successes": success_count,
        "failures": failure_count,
    }

    if durations:
        summary.update(
            {
                "min_duration_sec": round(min(durations), 3),
                "max_duration_sec": round(max(durations), 3),
                "mean_duration_sec": round(statistics.mean(durations), 3),
                "median_duration_sec": round(statistics.median(durations), 3),
            }
        )

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reproducible benchmark requests against the MCP client /chat endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL of the mcp-client service.")
    parser.add_argument(
        "--scenarios",
        default=str(Path(__file__).with_name("scenarios.json")),
        help="Path to the JSON scenario file.",
    )
    parser.add_argument("--scenario", action="append", help="Scenario name to run. Can be passed multiple times.")
    parser.add_argument("--repeats", type=int, default=3, help="Number of measured runs per scenario.")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per scenario.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("benchmark-results.json")),
        help="Output path for the JSON benchmark report.",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenarios)
    output_path = Path(args.output)
    scenarios = load_scenarios(scenario_path)

    if args.scenario:
        selected_names = set(args.scenario)
        scenarios = [scenario for scenario in scenarios if scenario.get("name") in selected_names]

    if not scenarios:
        print("No scenarios selected.", file=sys.stderr)
        return 1

    report = {
        "base_url": args.base_url,
        "scenario_file": str(scenario_path),
        "generated_at_epoch": time.time(),
        "warmup_runs": args.warmup,
        "measured_repeats": args.repeats,
        "results": [],
    }

    for scenario in scenarios:
        scenario_name = scenario["name"]
        payload = scenario["payload"]
        print(f"Running scenario: {scenario_name}")

        for _ in range(args.warmup):
            _ = run_once(args.base_url, payload, args.timeout)

        runs = []
        for iteration in range(1, args.repeats + 1):
            result = run_once(args.base_url, payload, args.timeout)
            result["iteration"] = iteration
            runs.append(result)
            status = "ok" if result["ok"] else "failed"
            print(f"  run {iteration}: {status} in {result['duration_sec']}s")

        report["results"].append(
            {
                "name": scenario_name,
                "description": scenario.get("description", ""),
                "summary": summarize(runs),
                "runs": runs,
            }
        )

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=True)

    print(f"\nSaved report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
