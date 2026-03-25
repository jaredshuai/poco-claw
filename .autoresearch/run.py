#!/usr/bin/env python3
"""
Autoresearch experiment runner script.

Usage:
    python run.py baseline <module>   - Measure and save baseline for a module
    python run.py measure <module>    - Measure current metrics for a module
    python run.py compare <module>    - Compare current vs baseline
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Project root is parent of .autoresearch directory
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
BASELINE_FILE = SCRIPT_DIR / "baseline.json"
RESULTS_FILE = SCRIPT_DIR / "results.tsv"


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """
    Run a shell command and capture output.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def count_ruff_errors(path: Path) -> int:
    """
    Count lint errors using ruff check.

    Args:
        path: Path to file or directory to check

    Returns:
        Number of lint errors found
    """
    # Find the backend directory if path is within it
    cwd = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT

    cmd = ["uv", "run", "ruff", "check", str(path), "--output-format=json"]
    returncode, stdout, stderr = run_command(cmd, cwd=cwd)

    if returncode == 0 or not stdout.strip():
        return 0

    try:
        errors = json.loads(stdout)
        return len(errors) if isinstance(errors, list) else 0
    except json.JSONDecodeError:
        # If not JSON, count lines
        return len(stdout.strip().split("\n")) if stdout.strip() else 0


def count_ty_errors(path: Path) -> int:
    """
    Count type errors using ty check.

    Args:
        path: Path to file or directory to check

    Returns:
        Number of type errors found
    """
    # Find the backend directory if path is within it
    cwd = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT

    cmd = ["uv", "run", "ty", "check", str(path)]
    returncode, stdout, stderr = run_command(cmd, cwd=cwd)

    # ty outputs errors in stderr or stdout
    output = stdout + stderr

    # Count lines that look like errors (contain ": error:" or similar patterns)
    error_count = 0
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # ty outputs errors in format: file:line:col: error: message
        if "error:" in line.lower():
            error_count += 1

    return error_count


def get_test_coverage(module_path: Path) -> float:
    """
    Get test coverage using pytest --cov.

    Args:
        module_path: Path to the module to measure coverage for

    Returns:
        Coverage percentage (0-100)
    """
    cwd = PROJECT_ROOT / "backend" if (PROJECT_ROOT / "backend").exists() else PROJECT_ROOT

    # Try to run pytest with coverage
    cmd = [
        "uv",
        "run",
        "pytest",
        "--cov", str(module_path),
        "--cov-report=term-missing",
        "-q",
    ]

    returncode, stdout, stderr = run_command(cmd, cwd=cwd)
    output = stdout + stderr

    # Parse coverage percentage from output
    # Look for patterns like "TOTAL    100%" or coverage percentage
    for line in output.split("\n"):
        if "TOTAL" in line:
            parts = line.split()
            for part in parts:
                if "%" in part:
                    try:
                        return float(part.replace("%", ""))
                    except ValueError:
                        continue

    # Return -1 if coverage couldn't be determined
    return -1.0


def load_baseline() -> dict[str, Any]:
    """
    Load baseline metrics from JSON file.

    Returns:
        Dictionary of baseline metrics by module path
    """
    if not BASELINE_FILE.exists():
        return {}

    with open(BASELINE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_baseline(baseline: dict[str, Any]) -> None:
    """
    Save baseline metrics to JSON file.

    Args:
        baseline: Dictionary of baseline metrics by module path
    """
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)


def record_result(
    module: str,
    ruff_errors: int,
    ty_errors: int,
    coverage: float,
    notes: str = "",
) -> None:
    """
    Append measurement results to TSV file.

    Args:
        module: Path to the measured module
        ruff_errors: Number of lint errors
        ty_errors: Number of type errors
        coverage: Test coverage percentage
        notes: Optional notes about this measurement
    """
    timestamp = datetime.now().isoformat()

    # Create file with header if it doesn't exist
    if not RESULTS_FILE.exists():
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            f.write("timestamp\tmodule\truff_errors\tty_errors\tcoverage\tnotes\n")

    # Append the result
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{module}\t{ruff_errors}\t{ty_errors}\t{coverage}\t{notes}\n")


def measure_module(module: str) -> dict[str, Any]:
    """
    Get all metrics for a module.

    Args:
        module: Path to the module (relative to project root)

    Returns:
        Dictionary with ruff_errors, ty_errors, and coverage
    """
    # Resolve the path
    if module.startswith("backend/"):
        module_path = PROJECT_ROOT / module
    else:
        # Try backend first, then root
        module_path = PROJECT_ROOT / "backend" / module
        if not module_path.exists():
            module_path = PROJECT_ROOT / module

    if not module_path.exists():
        print(f"Error: Module not found: {module_path}")
        sys.exit(1)

    print(f"Measuring: {module_path}")

    ruff_errors = count_ruff_errors(module_path)
    print(f"  Ruff errors: {ruff_errors}")

    ty_errors = count_ty_errors(module_path)
    print(f"  Type errors: {ty_errors}")

    coverage = get_test_coverage(module_path)
    if coverage >= 0:
        print(f"  Test coverage: {coverage}%")
    else:
        print("  Test coverage: N/A")

    return {
        "ruff_errors": ruff_errors,
        "ty_errors": ty_errors,
        "coverage": coverage,
    }


def cmd_baseline(module: str) -> None:
    """Measure and save baseline for a module."""
    metrics = measure_module(module)

    baseline = load_baseline()
    baseline[module] = {
        **metrics,
        "timestamp": datetime.now().isoformat(),
    }
    save_baseline(baseline)

    print(f"\nBaseline saved for {module}")
    record_result(module, metrics["ruff_errors"], metrics["ty_errors"], metrics["coverage"], "baseline")


def cmd_measure(module: str) -> None:
    """Measure current metrics for a module."""
    metrics = measure_module(module)
    record_result(module, metrics["ruff_errors"], metrics["ty_errors"], metrics["coverage"], "measure")

    print(f"\nResults recorded for {module}")


def cmd_compare(module: str) -> None:
    """Compare current vs baseline for a module."""
    baseline = load_baseline()

    if module not in baseline:
        print(f"Error: No baseline found for {module}")
        print("Run 'python run.py baseline <module>' first.")
        sys.exit(1)

    current = measure_module(module)
    base = baseline[module]

    print(f"\nComparison for {module}:")
    print("-" * 50)
    print(f"{'Metric':<20} {'Baseline':<12} {'Current':<12} {'Change':<12}")
    print("-" * 50)

    ruff_diff = current["ruff_errors"] - base["ruff_errors"]
    print(f"{'Ruff errors':<20} {base['ruff_errors']:<12} {current['ruff_errors']:<12} {ruff_diff:+d}")

    ty_diff = current["ty_errors"] - base["ty_errors"]
    print(f"{'Type errors':<20} {base['ty_errors']:<12} {current['ty_errors']:<12} {ty_diff:+d}")

    if current["coverage"] >= 0 and base["coverage"] >= 0:
        cov_diff = current["coverage"] - base["coverage"]
        print(f"{'Coverage %':<20} {base['coverage']:<12.1f} {current['coverage']:<12.1f} {cov_diff:+.1f}")
    else:
        print(f"{'Coverage %':<20} {'N/A':<12} {'N/A':<12} {'N/A':<12}")

    print("-" * 50)

    record_result(
        module,
        current["ruff_errors"],
        current["ty_errors"],
        current["coverage"],
        f"compare (baseline: ruff={base['ruff_errors']}, ty={base['ty_errors']})",
    )


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 3:
        print(__doc__)
        print("Error: Missing command or module")
        sys.exit(1)

    command = sys.argv[1].lower()
    module = sys.argv[2]

    if command == "baseline":
        cmd_baseline(module)
    elif command == "measure":
        cmd_measure(module)
    elif command == "compare":
        cmd_compare(module)
    else:
        print(f"Unknown command: {command}")
        print("Valid commands: baseline, measure, compare")
        sys.exit(1)


if __name__ == "__main__":
    main()