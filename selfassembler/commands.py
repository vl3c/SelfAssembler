"""Language-agnostic command detection for project tooling."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

# Project type markers and their associated commands
PROJECT_COMMANDS: dict[str, dict[str, list[str]]] = {
    "package.json": {
        "lint": ["npm run lint", "yarn lint", "pnpm lint"],
        "typecheck": ["npm run typecheck", "npx tsc --noEmit", "yarn typecheck"],
        "test": ["npm test", "yarn test", "pnpm test"],
        "build": ["npm run build", "yarn build", "pnpm build"],
        "format": ["npm run format", "npx prettier --write .", "yarn format"],
    },
    "pyproject.toml": {
        "lint": ["ruff check --fix .", "flake8 .", "pylint ."],
        "typecheck": ["mypy .", "pyright .", "pytype ."],
        "test": ["pytest", "python -m pytest", "python -m unittest discover"],
        "build": ["python -m build", "pip install -e ."],
        "format": ["ruff format .", "black .", "autopep8 --in-place -r ."],
    },
    "setup.py": {
        "lint": ["flake8 .", "pylint ."],
        "typecheck": ["mypy ."],
        "test": ["pytest", "python -m pytest"],
        "build": ["python setup.py build"],
        "format": ["black ."],
    },
    "Cargo.toml": {
        "lint": ["cargo clippy -- -D warnings"],
        "typecheck": [],  # Rust compiler handles this
        "test": ["cargo test"],
        "build": ["cargo build"],
        "format": ["cargo fmt"],
    },
    "go.mod": {
        "lint": ["golangci-lint run", "go vet ./..."],
        "typecheck": [],  # Go compiler handles this
        "test": ["go test ./..."],
        "build": ["go build ./..."],
        "format": ["go fmt ./..."],
    },
    "Makefile": {
        "lint": ["make lint"],
        "typecheck": ["make typecheck", "make check-types"],
        "test": ["make test"],
        "build": ["make build", "make"],
        "format": ["make format", "make fmt"],
    },
    "pom.xml": {
        "lint": ["mvn checkstyle:check"],
        "typecheck": [],  # Java compiler handles this
        "test": ["mvn test"],
        "build": ["mvn package"],
        "format": [],
    },
    "build.gradle": {
        "lint": ["./gradlew check"],
        "typecheck": [],
        "test": ["./gradlew test"],
        "build": ["./gradlew build"],
        "format": [],
    },
    "Gemfile": {
        "lint": ["bundle exec rubocop"],
        "typecheck": ["bundle exec srb tc", "bundle exec steep check"],
        "test": ["bundle exec rspec", "bundle exec rake test"],
        "build": ["bundle install"],
        "format": ["bundle exec rubocop -a"],
    },
}


# Tools that accept file arguments for diff-scoped linting.
# Each entry maps a tool prefix to the file extensions it handles.
_SCOPABLE_TOOLS: dict[str, set[str]] = {
    "mypy": {".py"},
    "pyright": {".py"},
    "ruff check": {".py"},
    "flake8": {".py"},
    "eslint": {".js", ".jsx", ".ts", ".tsx"},
}


def scope_command_to_files(cmd: str, changed_files: list[str], workdir: Path) -> str | None:
    """Scope a lint/typecheck command to only changed files, if supported.

    Preserves all original flags/options and only replaces the trailing
    path target (typically ``"."``) with the list of changed files.

    Returns the scoped command, or None to fall back to full-project run.
    """
    if not changed_files:
        return None

    for prefix, exts in _SCOPABLE_TOOLS.items():
        if not cmd.startswith(prefix):
            continue
        # Filter to relevant extensions and existing files
        relevant = [
            f for f in changed_files
            if any(f.endswith(ext) for ext in exts) and (workdir / f).exists()
        ]
        if not relevant:
            return None  # No relevant changed files
        quoted = " ".join(shlex.quote(f) for f in relevant)
        # Replace trailing "." target with file list, preserving all flags
        if cmd.rstrip().endswith(" ."):
            return cmd.rstrip()[:-1] + quoted
        # No trailing "." — append files to the original command as-is
        return cmd.rstrip() + " " + quoted

    return None  # Tool not scopable


def detect_project_type(workdir: Path) -> str | None:
    """
    Detect the project type based on marker files.

    Args:
        workdir: The directory to check

    Returns:
        The marker file name if found, None otherwise
    """
    # Check in priority order (more specific first)
    priority_order = [
        "Cargo.toml",
        "go.mod",
        "pyproject.toml",
        "setup.py",
        "package.json",
        "pom.xml",
        "build.gradle",
        "Gemfile",
        "Makefile",
    ]

    for marker in priority_order:
        if (workdir / marker).exists():
            return marker

    return None


def detect_all_project_types(workdir: Path) -> list[str]:
    """
    Detect all project types present in the directory.

    Useful for monorepos or projects with multiple languages.
    """
    found = []
    for marker in PROJECT_COMMANDS:
        if (workdir / marker).exists():
            found.append(marker)
    return found


def _check_npm_script_exists(workdir: Path, script: str) -> bool:
    """Check if an npm script exists in package.json."""
    import json

    package_json = workdir / "package.json"
    if not package_json.exists():
        return False

    try:
        with open(package_json) as f:
            data = json.load(f)
        return script in data.get("scripts", {})
    except (json.JSONDecodeError, OSError):
        return False


def _check_command_available(workdir: Path, cmd: str, project_type: str) -> bool:
    """
    Check if a command is available/configured for the project.

    Args:
        workdir: Working directory
        cmd: The command to check (first word is the executable)
        project_type: The detected project type marker

    Returns:
        True if the command should work
    """
    parts = cmd.split()
    if not parts:
        return False

    executable = parts[0]

    # Special handling for npm/yarn/pnpm run commands
    if executable in ("npm", "yarn", "pnpm") and len(parts) >= 3 and parts[1] == "run":
        script_name = parts[2]
        return _check_npm_script_exists(workdir, script_name)

    if executable in ("npm", "yarn", "pnpm") and len(parts) >= 2:
        # npm test, npm lint, etc. are aliases for npm run test
        script_name = parts[1]
        if script_name not in ("install", "ci", "init", "publish"):
            return _check_npm_script_exists(workdir, script_name)

    # Check if executable exists
    try:
        result = subprocess.run(
            ["which" if os.name != "nt" else "where", executable],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_command(
    workdir: Path,
    command_type: str,
    override: str | None = None,
) -> str | None:
    """
    Get the appropriate command for a project.

    Args:
        workdir: Working directory
        command_type: Type of command ("lint", "test", "build", etc.)
        override: Optional override command from config

    Returns:
        The command to run, or None if not available
    """
    if override:
        return override

    project_type = detect_project_type(workdir)
    if not project_type:
        return None

    candidates = PROJECT_COMMANDS.get(project_type, {}).get(command_type, [])

    for cmd in candidates:
        if _check_command_available(workdir, cmd, project_type):
            return cmd

    return None


def get_all_commands(workdir: Path) -> dict[str, str | None]:
    """
    Get all available commands for the project.

    Returns:
        Dictionary mapping command types to their commands
    """
    command_types = ["lint", "typecheck", "test", "build", "format"]
    return {cmd_type: get_command(workdir, cmd_type) for cmd_type in command_types}


def run_command(
    workdir: Path,
    command: str,
    timeout: int = 300,
    capture: bool = True,
) -> tuple[bool, str, str]:
    """
    Run a shell command in the working directory.

    Args:
        workdir: Directory to run in
        command: Command to execute
        timeout: Timeout in seconds
        capture: Whether to capture output

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        # Use shell=True only for commands with pipes or complex syntax
        # This is necessary for shell operators but comes with security considerations
        use_shell = any(c in command for c in ["|", "&&", "||", ";", ">", "<"])

        if use_shell:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                capture_output=capture,
                text=True,
                timeout=timeout,
            )
        else:
            # Use shlex.split for safer argument parsing
            result = subprocess.run(
                shlex.split(command),
                cwd=workdir,
                capture_output=capture,
                text=True,
                timeout=timeout,
            )

        return (
            result.returncode == 0,
            result.stdout if capture else "",
            result.stderr if capture else "",
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return False, "", f"Command not found: {e}"
    except Exception as e:
        return False, "", f"Command failed: {e}"


def extract_failure_ids(failure_lines: list[str]) -> list[str]:
    """Extract structured test IDs from failure lines.

    Parses framework-specific patterns to extract fully-qualified test IDs.
    Lines that don't match any pattern are included verbatim as IDs so they
    still participate in baseline diffing.

    Supported formats:
    - pytest: ``FAILED path/test.py::Class::test_name - reason``
    - go: ``--- FAIL: TestName/SubTest (0.01s)``
    - cargo: ``test mod::path::test_name ... FAILED``
    - jest: ``FAIL src/file.test.js > Suite > test name``
    """
    import re

    ids: list[str] = []
    seen: set[str] = set()

    for line in failure_lines:
        stripped = line.strip()
        if not stripped:
            continue

        fid: str | None = None

        # pytest: "FAILED path/test.py::Class::test_name - reason"
        # Also matches short summary lines like "FAILED path/test.py::test_name"
        m = re.match(r"FAILED\s+([\w/\\.:]+(?:::\w+)+)", stripped)
        if m:
            fid = m.group(1)

        # go: "--- FAIL: TestName/SubTest (0.01s)"
        if fid is None:
            m = re.match(r"---\s+FAIL:\s+(\S+)", stripped)
            if m:
                fid = m.group(1)

        # cargo: "test mod::path::test_name ... FAILED"
        if fid is None:
            m = re.match(r"test\s+([\w:]+)\s+\.\.\.\s+FAILED", stripped)
            if m:
                fid = m.group(1)

        # jest: "FAIL src/file.test.js > Suite > test name"
        if fid is None:
            m = re.match(r"FAIL\s+(.+)", stripped)
            if m:
                fid = m.group(1).strip()

        # Fallback: use the raw line verbatim as the ID
        if fid is None:
            fid = stripped

        if fid not in seen:
            seen.add(fid)
            ids.append(fid)

    return ids


def load_known_failures(workdir: Path) -> list[str]:
    """Load known test failure IDs from ``.sa-known-failures`` in *workdir*.

    The file contains one test ID per line. Lines starting with ``#`` and
    blank lines are ignored.
    """
    known_file = workdir / ".sa-known-failures"
    if not known_file.exists():
        return []

    ids: list[str] = []
    for raw in known_file.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def diff_test_failures(
    current_ids: list[str],
    baseline_ids: list[str],
    known_ids: list[str] | None,
    exit_code_failed: bool,
) -> tuple[list[str], list[str]]:
    """Diff current test failures against baseline and known-failures lists.

    Returns ``(net_new, baseline_present)`` where *net_new* are failures not
    present in either the baseline or the known-failures file, and
    *baseline_present* are failures that were already expected.

    **Strict fallback**: if the exit code was non-zero but no parseable IDs
    were extracted at all (e.g. import errors, collection crashes), a single
    sentinel entry is returned in *net_new* to force a hard failure.
    """
    allowed = set(baseline_ids) | set(known_ids or [])
    net_new = [fid for fid in current_ids if fid not in allowed]
    baseline_present = [fid for fid in current_ids if fid in allowed]

    # STRICT FALLBACK: non-zero exit + no parseable IDs at all → hard fail
    if exit_code_failed and not current_ids:
        net_new = ["<unparseable test failure — non-zero exit with no structured IDs>"]

    return net_new, baseline_present


def parse_test_output(output: str) -> dict[str, Any]:
    """
    Parse test output to extract pass/fail information.

    This is a basic implementation that can be extended for
    more sophisticated parsing based on test framework.
    """
    result: dict[str, Any] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "failures": [],
        "failure_ids": [],
        "all_passed": False,
    }

    import re

    lines = output.split("\n")

    # Common patterns across test frameworks
    for line in lines:
        lower = line.lower()

        # pytest style: "5 passed" or "5 passed, 2 failed" or "5 passed in 0.05s"
        if "passed" in lower:
            passed = re.search(r"(\d+)\s*passed", lower)
            failed = re.search(r"(\d+)\s*failed", lower)
            errors = re.search(r"(\d+)\s*error", lower)
            skipped = re.search(r"(\d+)\s*skipped", lower)

            if passed:
                result["passed"] = int(passed.group(1))
            if failed:
                result["failed"] = int(failed.group(1))
            if errors:
                result["failed"] += int(errors.group(1))
            if skipped:
                result["skipped"] = int(skipped.group(1))

        # Jest/mocha style: "Tests: 5 passed, 2 failed"
        elif "tests:" in lower:
            passed = re.search(r"(\d+)\s*passed", lower)
            failed = re.search(r"(\d+)\s*failed", lower)

            if passed:
                result["passed"] = int(passed.group(1))
            if failed:
                result["failed"] = int(failed.group(1))

        # Capture failure messages
        if "FAILED" in line or "FAIL " in line or "FAIL:" in line or "Error:" in line:
            result["failures"].append(line.strip())

    result["total"] = result["passed"] + result["failed"] + result["skipped"]
    result["all_passed"] = result["failed"] == 0 and result["total"] > 0
    result["failure_ids"] = extract_failure_ids(result["failures"])

    return result
