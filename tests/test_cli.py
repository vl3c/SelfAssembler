"""Tests for CLI module."""

import pytest

from selfassembler.cli import create_parser, generate_task_name


class TestCreateParser:
    """Tests for argument parser."""

    def test_parser_created(self):
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None

    def test_task_argument(self):
        """Test task argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["Test task"])
        assert args.task == "Test task"

    def test_name_flag(self):
        """Test --name flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--name", "my-task"])
        assert args.task_name == "my-task"

    def test_autonomous_flag(self):
        """Test --autonomous flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--autonomous"])
        assert args.autonomous is True

    def test_no_approvals_flag(self):
        """Test --no-approvals flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--no-approvals"])
        assert args.no_approvals is True

    def test_resume_flag(self):
        """Test --resume flag."""
        parser = create_parser()
        args = parser.parse_args(["--resume", "checkpoint_abc123"])
        assert args.resume == "checkpoint_abc123"

    def test_skip_to_flag(self):
        """Test --skip-to flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--skip-to", "implementation"])
        assert args.skip_to == "implementation"

    def test_budget_flag(self):
        """Test --budget flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--budget", "25.0"])
        assert args.budget == 25.0

    def test_list_checkpoints_flag(self):
        """Test --list-checkpoints flag."""
        parser = create_parser()
        args = parser.parse_args(["--list-checkpoints"])
        assert args.list_checkpoints is True

    def test_list_phases_flag(self):
        """Test --list-phases flag."""
        parser = create_parser()
        args = parser.parse_args(["--list-phases"])
        assert args.list_phases is True


class TestGenerateTaskName:
    """Tests for task name generation."""

    def test_simple_name(self):
        """Test simple task name generation."""
        name = generate_task_name("Add user authentication")
        assert "add" in name.lower()
        assert "user" in name.lower()
        assert "-" in name

    def test_special_characters_removed(self):
        """Test special characters are removed."""
        name = generate_task_name("Fix bug #123: user can't login!")
        assert "#" not in name
        assert "!" not in name
        assert ":" not in name

    def test_truncation(self):
        """Test long names are truncated."""
        long_task = "This is a very long task description that should be truncated"
        name = generate_task_name(long_task)
        assert len(name) <= 40

    def test_empty_fallback(self):
        """Test fallback for empty/special-only input."""
        name = generate_task_name("!@#$%")
        assert name == "task"
