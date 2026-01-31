"""Tests for command detection."""

import tempfile
from pathlib import Path

from selfassembler.commands import (
    detect_all_project_types,
    detect_project_type,
    get_command,
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
