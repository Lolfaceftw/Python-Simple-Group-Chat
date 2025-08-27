#!/usr/bin/env python3
"""
Test runner script for the chat application.

This script provides convenient commands for running different types of tests.
"""

import sys
import subprocess
from pathlib import Path


def run_command(cmd: list[str]) -> int:
    """Run a command and return the exit code."""
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


def main():
    """Main test runner function."""
    if len(sys.argv) < 2:
        print("Usage: python run_tests.py <command>")
        print("Commands:")
        print("  unit           - Run unit tests")
        print("  integration    - Run integration tests")
        print("  fuzzing        - Run fuzzing tests")
        print("  all            - Run all tests")
        print("  coverage       - Run tests with coverage report")
        print("  shared         - Run shared module tests only")
        print("  server         - Run server module tests only")
        print("  client         - Run client module tests only")
        print("  discovery      - Run discovery module tests only")
        return 1
    
    command = sys.argv[1].lower()
    
    base_cmd = ["python", "-m", "pytest"]
    
    if command == "unit":
        cmd = base_cmd + ["tests/unit/", "-v"]
    elif command == "integration":
        cmd = base_cmd + ["tests/integration/", "-v"]
    elif command == "fuzzing":
        cmd = base_cmd + ["tests/fuzzing/", "-v"]
    elif command == "all":
        cmd = base_cmd + ["tests/", "-v"]
    elif command == "coverage":
        cmd = base_cmd + [
            "tests/unit/",
            "--cov=chat_app",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=90",
            "-v"
        ]
    elif command == "shared":
        cmd = base_cmd + ["tests/unit/test_shared/", "-v"]
    elif command == "server":
        cmd = base_cmd + ["tests/unit/test_server/", "-v"]
    elif command == "client":
        cmd = base_cmd + ["tests/unit/test_client/", "-v"]
    elif command == "discovery":
        cmd = base_cmd + ["tests/unit/test_discovery/", "-v"]
    else:
        print(f"Unknown command: {command}")
        return 1
    
    return run_command(cmd)


if __name__ == "__main__":
    sys.exit(main())