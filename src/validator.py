"""Run the official IHTC 2024 validator (validator/IHTP_Validator.cc) on solutions."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VALIDATOR_DIR = Path(__file__).resolve().parent.parent / "validator"
SOURCE = VALIDATOR_DIR / "IHTP_Validator.cc"
BINARY = VALIDATOR_DIR / ("IHTP_Validator.exe" if sys.platform == "win32" else "IHTP_Validator")

# Lines like "RoomAgeMix....15 (  5 X   3)" and "RoomGenderMix....0"
_COST_LINE = re.compile(r"^(\w+)\.+\s*(-?\d+)\s*\(\s*(\d+)\s*X\s*(-?\d+)\s*\)$")
_VIOLATION_LINE = re.compile(r"^(\w+)\.+\s*(-?\d+)$")


def _compile_command(compiler):
    """Command line to build the validator with `compiler`."""
    if Path(compiler).stem.lower() == "cl":  # MSVC
        return [compiler, "/nologo", "/O2", "/EHsc", "/std:c++17", f"/Fe:{BINARY}", str(SOURCE)]
    return [compiler, "-O2", "-std=c++17", "-o", str(BINARY), str(SOURCE)]


def _find_compiler():
    """First C++ compiler found: $CXX if set, else g++, clang++ or cl on the PATH."""
    candidates = [os.environ["CXX"]] if os.environ.get("CXX") else ["g++", "clang++", "cl"]
    for candidate in candidates:
        if path := shutil.which(candidate):
            return path
    raise RuntimeError(
        f"No C++ compiler found (looked for {', '.join(candidates)}) to build {SOURCE.name}.\n"
        "Either install one and open a new terminal, e.g. on Windows:\n"
        "    winget install BrechtSanders.WinLibs.POSIX.UCRT\n"
        "or set CXX to a compiler's path, or compile the validator yourself to\n"
        f"    {BINARY}"
    )


def compile_validator():
    """Compile the validator if the binary is missing or older than the source."""
    if BINARY.exists() and BINARY.stat().st_mtime >= SOURCE.stat().st_mtime:
        return BINARY
    compiler = _find_compiler()
    print(f"Compiling {SOURCE.name} with {compiler} ...")
    subprocess.run(
        _compile_command(compiler),
        cwd=VALIDATOR_DIR,  # so the validator finds json.hpp
        check=True,
    )
    return BINARY


def _parse_report(report):
    """Parse the validator's printed report into a dict."""
    result = {"violations": {}, "costs": {}, "total_violations": None, "total_cost": None}
    section = None
    for line in report.splitlines():
        line = line.strip()
        if line.startswith("VIOLATIONS"):
            section = "violations"
        elif line.startswith("COSTS"):
            section = "costs"
        elif line.startswith("Total violations"):
            result["total_violations"] = int(line.split("=")[1])
        elif line.startswith("Total cost"):
            result["total_cost"] = int(line.split("=")[1])
        elif section == "costs" and (m := _COST_LINE.match(line)):
            name, weighted, weight, count = m.groups()
            result["costs"][name] = {"weighted": int(weighted), "weight": int(weight), "count": int(count)}
        elif section == "violations" and (m := _VIOLATION_LINE.match(line)):
            result["violations"][m.group(1)] = int(m.group(2))
    if result["total_cost"] is None or result["total_violations"] is None:
        raise RuntimeError(f"Could not parse validator output:\n{report}")
    return result


def validate(instance_path, solution):
    """Run the validator on one solution and return its violations and costs.

    `solution` is either the solution dict (JSON form) or a path to a solution file.
    Returns a dict with keys "violations", "costs", "total_violations",
    "total_cost" and "report" (the validator's raw output).
    """
    binary = compile_validator()
    if isinstance(solution, dict):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(solution, f)
        solution_path = Path(f.name)
    else:
        solution_path = Path(solution)

    try:
        completed = subprocess.run(
            [str(binary), str(instance_path), str(solution_path)],
            capture_output=True, text=True, check=True,
        )
    finally:
        if isinstance(solution, dict):
            solution_path.unlink(missing_ok=True)

    result = _parse_report(completed.stdout)
    result["report"] = completed.stdout
    return result


def print_summary(results):
    """Print a table of total violations and cost per instance."""
    print(f"\n{'Instance':<12}{'Violations':>12}{'Cost':>14}")
    for name, result in results.items():
        if result is None:
            print(f"{name:<12}{'no solution':>26}")
        else:
            print(f"{name:<12}{result['total_violations']:>12}{result['total_cost']:>14}")
