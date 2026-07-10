#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUSTAINABILITY_DIR = REPO_ROOT / "ZODIAC-Tools" / "sustainability"
TEST_SUITE_DIR = REPO_ROOT / "ZODIAC-Tools" / "test-suite"
DEFAULT_TEST = "tests/test_subsidy_demo.py"
NAMESPACE = "zodiac"
JOB_NAME = "sma-benchmark-run"
JOB_LABEL = "app.kubernetes.io/name=sma-benchmark-run"
READER_DEPLOYMENT = "sma-report-reader"
READER_LABEL = "app.kubernetes.io/name=sma-report-reader"
LOCAL_REPORTS_DIR = SUSTAINABILITY_DIR / "downloaded-reports"
NOTEBOOK_TEMPLATE = SUSTAINABILITY_DIR / "sma_report_analysis.ipynb"

# Toggle tests on/off here with '#'.
AVAILABLE_TESTS = {
    "demo": "tests/test_subsidy_demo.py",
    "business_purposes": "tests/test_subsidy_demo_with_business_purposes.py",
    "extended_rag": "tests/test_subsidy_demo_with_extended_rag_collections.py",
    "wrong_purpose": "tests/test_subsidy_demo_with_wrong_purpose.py",
    "separate": "tests/test_subsidy_seperate.py",
}

ACTIVE_TESTS = [
    AVAILABLE_TESTS["demo"],
    # AVAILABLE_TESTS["business_purposes"],
    # AVAILABLE_TESTS["extended_rag"],
    # AVAILABLE_TESTS["wrong_purpose"],
    # AVAILABLE_TESTS["separate"],
]

SPINNER_FRAMES = ["|", "/", "-", "\\"]


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
    check: bool = True,
    show_command: bool = True,
) -> subprocess.CompletedProcess[str]:
    if show_command:
        print(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def render_spinner(message: str, step: int) -> None:
    frame = SPINNER_FRAMES[step % len(SPINNER_FRAMES)]
    sys.stdout.write(f"\r{frame} {message}")
    sys.stdout.flush()


def clear_spinner(message: str) -> None:
    sys.stdout.write(f"\r{message}\n")
    sys.stdout.flush()


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required binary not found in PATH: {name}")


def get_pytest_command() -> list[str]:
    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "run", "pytest"]

    local_pytest = REPO_ROOT / ".venv" / "bin" / "pytest"
    if local_pytest.exists():
        return [str(local_pytest)]

    raise SystemExit("Neither 'uv' nor './.venv/bin/pytest' is available for running the local tests.")


def get_jupyter_command() -> list[str]:
    jupyter_path = shutil.which("jupyter")
    if jupyter_path:
        return [jupyter_path]

    local_jupyter = REPO_ROOT / ".venv" / "bin" / "jupyter"
    if local_jupyter.exists():
        return [str(local_jupyter)]

    raise SystemExit("Jupyter is not available in PATH or './.venv/bin/jupyter'.")


def delete_old_job() -> None:
    run_cmd(
        [
            "kubectl",
            "delete",
            "job",
            JOB_NAME,
            "-n",
            NAMESPACE,
            "--ignore-not-found",
        ]
    )


def apply_job_manifest() -> None:
    run_cmd(
        [
            "kubectl",
            "apply",
            "-f",
            str(SUSTAINABILITY_DIR / "sma-job.yaml"),
            "-n",
            NAMESPACE,
        ]
    )


def get_job_pod_name() -> str | None:
    result = run_cmd(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            NAMESPACE,
            "-l",
            JOB_LABEL,
            "-o",
            "json",
        ],
        capture_output=True,
        show_command=False,
    )
    data = json.loads(result.stdout)
    items = data.get("items", [])
    if not items:
        return None
    items.sort(key=lambda item: item["metadata"]["creationTimestamp"], reverse=True)
    return items[0]["metadata"]["name"]


def wait_for_running_pod(timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    step = 0
    while time.time() < deadline:
        render_spinner("Waiting for SMA pod to reach Running...", step)
        pod_name = get_job_pod_name()
        if pod_name:
            result = run_cmd(
                [
                    "kubectl",
                    "get",
                    "pod",
                    pod_name,
                    "-n",
                    NAMESPACE,
                    "-o",
                    "json",
                ],
                capture_output=True,
                show_command=False,
            )
            pod = json.loads(result.stdout)
            phase = pod.get("status", {}).get("phase")
            if phase == "Running":
                clear_spinner(f"SMA pod is running: {pod_name}")
                return pod_name
            if phase in {"Failed", "Succeeded"}:
                clear_spinner("")
                raise SystemExit(f"SMA pod {pod_name} reached unexpected phase {phase!r} before running.")
        step += 1
        time.sleep(2)
    clear_spinner("")
    raise SystemExit(f"Timed out waiting {timeout_seconds}s for SMA pod to reach Running.")


def run_local_pytest(test_path: str, extra_pytest_args: list[str]) -> int:
    cmd = [*get_pytest_command(), test_path, "--tb=no", "-vv", *extra_pytest_args]
    result = run_cmd(cmd, cwd=TEST_SUITE_DIR, check=False)
    return result.returncode


def wait_for_job_completion(timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    step = 0
    while time.time() < deadline:
        render_spinner("Waiting for SMA job to finish...", step)
        result = run_cmd(
            ["kubectl", "get", "job", JOB_NAME, "-n", NAMESPACE, "-o", "json"],
            capture_output=True,
            check=False,
            show_command=False,
        )
        if result.returncode != 0:
            step += 1
            time.sleep(2)
            continue
        job = json.loads(result.stdout)
        status = job.get("status", {})
        if status.get("succeeded", 0) >= 1:
            clear_spinner("SMA job finished successfully.")
            return True
        if status.get("failed", 0) >= 1:
            clear_spinner("SMA job failed.")
            return False
        step += 1
        time.sleep(5)
    clear_spinner("")
    raise SystemExit(f"Timed out waiting {timeout_seconds}s for SMA job completion.")


def print_recent_logs(pod_name: str) -> None:
    run_cmd(
        ["kubectl", "logs", "-n", NAMESPACE, pod_name, "--tail=80"],
        check=False,
    )


def get_recent_logs(pod_name: str) -> str:
    result = run_cmd(
        ["kubectl", "logs", "-n", NAMESPACE, pod_name, "--tail=120"],
        capture_output=True,
        check=False,
    )
    return result.stdout


def extract_report_dir_name(log_text: str) -> str | None:
    matches = re.findall(r"reports/([0-9_]+_[a-f0-9]+)", log_text)
    if not matches:
        return None
    return matches[-1]


def ensure_reader_ready() -> None:
    run_cmd(
        [
            "kubectl",
            "apply",
            "-f",
            str(SUSTAINABILITY_DIR / "sma-report-reader.yaml"),
            "-n",
            NAMESPACE,
        ]
    )
    run_cmd(
        [
            "kubectl",
            "rollout",
            "status",
            f"deployment/{READER_DEPLOYMENT}",
            "-n",
            NAMESPACE,
        ]
    )


def get_reader_pod_name() -> str:
    result = run_cmd(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            NAMESPACE,
            "-l",
            READER_LABEL,
            "-o",
            "json",
        ],
        capture_output=True,
        show_command=False,
    )
    data = json.loads(result.stdout)
    items = data.get("items", [])
    if not items:
        raise SystemExit("No sma-report-reader pod found.")
    items.sort(key=lambda item: item["metadata"]["creationTimestamp"], reverse=True)
    return items[0]["metadata"]["name"]


def download_report(report_dir_name: str) -> Path:
    ensure_reader_ready()
    reader_pod = get_reader_pod_name()
    LOCAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    destination = LOCAL_REPORTS_DIR / report_dir_name
    if destination.exists():
        shutil.rmtree(destination)
    run_cmd(
        [
            "kubectl",
            "cp",
            f"{NAMESPACE}/{reader_pod}:/output/reports/{report_dir_name}",
            str(destination),
        ]
    )
    return destination


def prepare_notebook(report_path: Path) -> Path:
    notebook_destination = report_path / NOTEBOOK_TEMPLATE.name
    shutil.copy2(NOTEBOOK_TEMPLATE, notebook_destination)
    return notebook_destination


def launch_jupyter(notebook_path: Path) -> None:
    command = [*get_jupyter_command(), "lab", str(notebook_path)]
    print(f"$ {' '.join(command)}")
    subprocess.Popen(command, cwd=str(notebook_path.parent), start_new_session=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start an SMA job in the cluster and run the subsidy demo test locally."
    )
    parser.add_argument(
        "--test",
        default=None,
        help="Run exactly one pytest path relative to the test-suite directory.",
    )
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="Print the predefined test aliases and exit.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=int,
        default=180,
        help="Seconds to wait for the SMA pod to reach Running.",
    )
    parser.add_argument(
        "--job-timeout",
        type=int,
        default=900,
        help="Seconds to wait for SMA job completion after starting the test.",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=15,
        help="Seconds to wait after the SMA pod is Running before starting the local test.",
    )
    parser.add_argument(
        "--with-jupyter",
        action="store_true",
        help="After the run, download the latest SMA report locally and start Jupyter Lab with the bundled notebook.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to pytest. Prefix with --, e.g. -- -k subsidy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    require_binary("kubectl")

    if args.list_tests:
        for alias, path in AVAILABLE_TESTS.items():
            print(f"{alias}: {path}")
        return 0

    if args.test:
        selected_tests = [args.test]
    else:
        selected_tests = list(ACTIVE_TESTS)

    if not selected_tests:
        raise SystemExit(
            "No tests selected. Either uncomment at least one entry in ACTIVE_TESTS or use --test."
        )

    for test_path in selected_tests:
        if not (TEST_SUITE_DIR / test_path).exists():
            raise SystemExit(f"Test path does not exist: {TEST_SUITE_DIR / test_path}")

    extra_pytest_args = args.pytest_args
    if extra_pytest_args and extra_pytest_args[0] == "--":
        extra_pytest_args = extra_pytest_args[1:]

    delete_old_job()
    apply_job_manifest()

    pod_name = wait_for_running_pod(args.startup_timeout)
    print(f"SMA pod is running: {pod_name}")

    if args.settle_seconds > 0:
        print(f"Waiting {args.settle_seconds}s so SMA can enter the observation window...")
        time.sleep(args.settle_seconds)

    pytest_exit_code = 0
    for test_path in selected_tests:
        print(f"Running local pytest for {test_path}")
        pytest_exit_code = run_local_pytest(test_path, extra_pytest_args)
        print(f"Local pytest finished with exit code {pytest_exit_code}: {test_path}")
        if pytest_exit_code != 0:
            break

    job_succeeded = wait_for_job_completion(args.job_timeout)
    print_recent_logs(pod_name)
    log_text = get_recent_logs(pod_name)

    if not job_succeeded:
        print("SMA job failed.", file=sys.stderr)
        return 1

    if pytest_exit_code != 0:
        print("SMA job finished, but the local pytest run failed.", file=sys.stderr)
        return pytest_exit_code

    report_dir_name = extract_report_dir_name(log_text)
    if report_dir_name:
        print(f"Latest SMA report directory: reports/{report_dir_name}")
    else:
        print("Could not determine the latest SMA report directory from logs.")

    if args.with_jupyter:
        if not report_dir_name:
            print("Skipping Jupyter launch because no report directory could be extracted.", file=sys.stderr)
            return 1
        report_path = download_report(report_dir_name)
        notebook_path = prepare_notebook(report_path)
        print(f"Downloaded SMA report to: {report_path}")
        launch_jupyter(notebook_path)
        print(f"Started Jupyter for: {notebook_path}")

    print("SMA job and local pytest run both completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
