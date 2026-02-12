"""Tests for command detection."""

import tempfile
from pathlib import Path

from selfassembler.commands import (
    detect_all_project_types,
    detect_project_type,
    diff_test_failures,
    extract_failure_ids,
    get_command,
    load_known_failures,
    parse_test_output,
)


class TestProjectDetection:
    """Tests for project type detection."""

    def test_detect_python_project(self):
        """Test detecting Python project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "pyproject.toml").touch()

            assert detect_project_type(path) == "pyproject.toml"

    def test_detect_node_project(self):
        """Test detecting Node.js project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "package.json").write_text("{}")

            assert detect_project_type(path) == "package.json"

    def test_detect_rust_project(self):
        """Test detecting Rust project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "Cargo.toml").touch()

            assert detect_project_type(path) == "Cargo.toml"

    def test_detect_go_project(self):
        """Test detecting Go project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "go.mod").touch()

            assert detect_project_type(path) == "go.mod"

    def test_detect_multiple_project_types(self):
        """Test detecting multiple project types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "pyproject.toml").touch()
            (path / "package.json").write_text("{}")

            types = detect_all_project_types(path)
            assert "pyproject.toml" in types
            assert "package.json" in types

    def test_no_project_detected(self):
        """Test when no project type is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            assert detect_project_type(path) is None


class TestGetCommand:
    """Tests for getting commands."""

    def test_get_command_with_override(self):
        """Test command override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            result = get_command(path, "test", override="custom test command")
            assert result == "custom test command"

    def test_get_command_no_project(self):
        """Test getting command when no project detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            result = get_command(path, "test")
            assert result is None


class TestParseTestOutput:
    """Tests for parsing test output."""

    def test_parse_pytest_output(self):
        """Test parsing pytest output."""
        output = """
============================= test session starts ==============================
collected 10 items

test_example.py ..F.....                                                  [80%]
test_other.py ..                                                         [100%]

=================================== FAILURES ===================================
FAILED test_example.py::test_something - AssertionError: assert False
=========================== short test summary info ============================
FAILED test_example.py::test_something
====================== 1 failed, 9 passed in 0.12s ========================
"""
        result = parse_test_output(output)
        assert result["passed"] == 9
        assert result["failed"] == 1
        assert result["all_passed"] is False
        assert len(result["failures"]) > 0

    def test_parse_jest_output(self):
        """Test parsing Jest output."""
        output = """
 PASS  src/components/Button.test.js
 FAIL  src/utils/helpers.test.js
  ● Test suite failed to run

Tests:  1 failed, 5 passed, 6 total
"""
        result = parse_test_output(output)
        assert result["passed"] == 5
        assert result["failed"] == 1
        assert result["all_passed"] is False

    def test_parse_all_passed(self):
        """Test parsing when all tests pass."""
        output = """
============================= test session starts ==============================
collected 5 items

test_example.py .....                                                    [100%]

============================== 5 passed in 0.05s ===============================
"""
        result = parse_test_output(output)
        assert result["passed"] == 5
        assert result["failed"] == 0
        assert result["all_passed"] is True

    def test_parse_test_output_includes_failure_ids(self):
        """Test that parse_test_output populates failure_ids."""
        output = """
FAILED tests/test_foo.py::TestBar::test_baz - AssertionError
FAILED tests/test_foo.py::test_quux
1 failed, 9 passed in 0.12s
"""
        result = parse_test_output(output)
        assert "failure_ids" in result
        assert "tests/test_foo.py::TestBar::test_baz" in result["failure_ids"]
        assert "tests/test_foo.py::test_quux" in result["failure_ids"]


class TestExtractFailureIds:
    """Tests for extract_failure_ids."""

    def test_pytest_format(self):
        """Test extracting pytest-style failure IDs."""
        lines = [
            "FAILED tests/test_a.py::TestClass::test_method - AssertionError",
            "FAILED tests/test_b.py::test_func",
        ]
        ids = extract_failure_ids(lines)
        assert ids == [
            "tests/test_a.py::TestClass::test_method",
            "tests/test_b.py::test_func",
        ]

    def test_go_format(self):
        """Test extracting Go-style failure IDs."""
        lines = [
            "--- FAIL: TestName/SubTest (0.01s)",
            "--- FAIL: TestOther (0.05s)",
        ]
        ids = extract_failure_ids(lines)
        assert ids == ["TestName/SubTest", "TestOther"]

    def test_cargo_format(self):
        """Test extracting Cargo-style failure IDs."""
        lines = [
            "test mod::path::test_name ... FAILED",
            "test other::test_two ... FAILED",
        ]
        ids = extract_failure_ids(lines)
        assert ids == ["mod::path::test_name", "other::test_two"]

    def test_jest_format(self):
        """Test extracting Jest-style failure IDs."""
        lines = [
            "FAIL src/file.test.js > Suite > test name",
        ]
        ids = extract_failure_ids(lines)
        assert ids == ["src/file.test.js > Suite > test name"]

    def test_unrecognized_lines_kept_verbatim(self):
        """Test that lines matching no pattern are kept as-is."""
        lines = [
            "some random error line",
            "Error: something broke",
        ]
        ids = extract_failure_ids(lines)
        assert "some random error line" in ids
        assert "Error: something broke" in ids

    def test_dedup(self):
        """Test that duplicate lines are deduplicated."""
        lines = [
            "FAILED tests/test_a.py::test_x - reason1",
            "FAILED tests/test_a.py::test_x - reason2",
        ]
        ids = extract_failure_ids(lines)
        assert ids == ["tests/test_a.py::test_x"]

    def test_empty_input(self):
        """Test with empty input."""
        assert extract_failure_ids([]) == []

    def test_blank_lines_skipped(self):
        """Test that blank lines are skipped."""
        ids = extract_failure_ids(["", "  ", "FAILED tests/test_a.py::test_x"])
        assert ids == ["tests/test_a.py::test_x"]


class TestDiffTestFailures:
    """Tests for diff_test_failures."""

    def test_all_baseline(self):
        """Test when all failures are in baseline."""
        current = ["a", "b"]
        baseline = ["a", "b", "c"]
        net_new, present = diff_test_failures(current, baseline, None, exit_code_failed=True)
        assert net_new == []
        assert set(present) == {"a", "b"}

    def test_all_new(self):
        """Test when all failures are new."""
        current = ["x", "y"]
        baseline = ["a", "b"]
        net_new, present = diff_test_failures(current, baseline, None, exit_code_failed=True)
        assert net_new == ["x", "y"]
        assert present == []

    def test_mixed(self):
        """Test mixed baseline and new failures."""
        current = ["a", "x"]
        baseline = ["a", "b"]
        net_new, present = diff_test_failures(current, baseline, None, exit_code_failed=True)
        assert net_new == ["x"]
        assert present == ["a"]

    def test_known_failures_overlay(self):
        """Test that known failures are treated like baseline."""
        current = ["a", "x"]
        baseline = []
        known = ["a"]
        net_new, present = diff_test_failures(current, baseline, known, exit_code_failed=True)
        assert net_new == ["x"]
        assert present == ["a"]

    def test_strict_fallback_no_ids(self):
        """Test strict fallback when exit code failed but no IDs."""
        net_new, present = diff_test_failures([], [], None, exit_code_failed=True)
        assert len(net_new) == 1
        assert "unparseable" in net_new[0]
        assert present == []

    def test_no_strict_fallback_when_exit_ok(self):
        """Test no strict fallback when exit code is ok."""
        net_new, present = diff_test_failures([], [], None, exit_code_failed=False)
        assert net_new == []
        assert present == []

    def test_empty_baseline_and_current(self):
        """Test with empty baseline and no current failures (exit ok)."""
        net_new, present = diff_test_failures([], [], None, exit_code_failed=False)
        assert net_new == []
        assert present == []


class TestLoadKnownFailures:
    """Tests for load_known_failures."""

    def test_file_exists_with_comments_and_blanks(self):
        """Test loading known failures with comments and blank lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".sa-known-failures").write_text(
                "# Known failures in Docker\n"
                "tests/test_a.py::test_perm\n"
                "\n"
                "# Another one\n"
                "tests/test_b.py::test_chown\n"
                "  \n"
            )
            ids = load_known_failures(path)
            assert ids == [
                "tests/test_a.py::test_perm",
                "tests/test_b.py::test_chown",
            ]

    def test_file_missing(self):
        """Test loading when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            ids = load_known_failures(path)
            assert ids == []
