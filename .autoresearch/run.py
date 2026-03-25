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
    change_type: str,
    lint_before: int,
    lint_after: int,
    type_before: int,
    type_after: int,
    cov_before: float,
    cov_after: float,
    status: str,
    description: str = "",
) -> None:
    """
    Append measurement results to TSV file.

    Args:
        module: Path to the measured module
        change_type: Type of change (lint_fix, type_fix, test_add, refactor)
        lint_before: Lint error count before change
        lint_after: Lint error count after change
        type_before: Type error count before change
        type_after: Type error count after change
        cov_before: Test coverage before change
        cov_after: Test coverage after change
        status: Status of the change (keep/discard/crash)
        description: Description of the change
    """
    timestamp = datetime.now().isoformat()

    # Create file with header if it doesn't exist
    if not RESULTS_FILE.exists():
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            f.write("timestamp\tmodule\tchange_type\tlint_before\tlint_after\ttype_before\ttype_after\tcov_before\tcov_after\tstatus\tdescription\n")

    # Append the result
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp}\t{module}\t{change_type}\t{lint_before}\t{lint_after}\t{type_before}\t{type_after}\t{cov_before}\t{cov_after}\t{status}\t{description}\n")


def measure_module(module: str) -> dict[str, Any]:
    """
    Get all metrics for a module.

    Args:
        module: Path to the module (relative to project root)

    Returns:
        Dictionary with lint_errors, type_errors, and test_coverage
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

    lint_errors = count_ruff_errors(module_path)
    print(f"  Lint errors: {lint_errors}")

    type_errors = count_ty_errors(module_path)
    print(f"  Type errors: {type_errors}")

    test_coverage = get_test_coverage(module_path)
    if test_coverage >= 0:
        print(f"  Test coverage: {test_coverage}%")
    else:
        print("  Test coverage: N/A")

    return {
        "lint_errors": lint_errors,
        "type_errors": type_errors,
        "test_coverage": test_coverage,
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
    record_result(
        module=module,
        change_type="baseline",
        lint_before=metrics["lint_errors"],
        lint_after=metrics["lint_errors"],
        type_before=metrics["type_errors"],
        type_after=metrics["type_errors"],
        cov_before=metrics["test_coverage"],
        cov_after=metrics["test_coverage"],
        status="keep",
        description="Initial baseline measurement",
    )


def cmd_measure(module: str) -> None:
    """Measure current metrics for a module."""
    metrics = measure_module(module)
    record_result(
        module=module,
        change_type="measure",
        lint_before=metrics["lint_errors"],
        lint_after=metrics["lint_errors"],
        type_before=metrics["type_errors"],
        type_after=metrics["type_errors"],
        cov_before=metrics["test_coverage"],
        cov_after=metrics["test_coverage"],
        status="keep",
        description="Current measurement",
    )

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

    lint_diff = current["lint_errors"] - base["lint_errors"]
    print(f"{'Lint errors':<20} {base['lint_errors']:<12} {current['lint_errors']:<12} {lint_diff:+d}")

    type_diff = current["type_errors"] - base["type_errors"]
    print(f"{'Type errors':<20} {base['type_errors']:<12} {current['type_errors']:<12} {type_diff:+d}")

    if current["test_coverage"] >= 0 and base["test_coverage"] >= 0:
        cov_diff = current["test_coverage"] - base["test_coverage"]
        print(f"{'Coverage %':<20} {base['test_coverage']:<12.1f} {current['test_coverage']:<12.1f} {cov_diff:+.1f}")
    else:
        print(f"{'Coverage %':<20} {'N/A':<12} {'N/A':<12} {'N/A':<12}")

    print("-" * 50)

    record_result(
        module=module,
        change_type="compare",
        lint_before=base["lint_errors"],
        lint_after=current["lint_errors"],
        type_before=base["type_errors"],
        type_after=current["type_errors"],
        cov_before=base["test_coverage"],
        cov_after=current["test_coverage"],
        status="keep",
        description=f"Comparison: lint {lint_diff:+d}, type {type_diff:+d}",
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