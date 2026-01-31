"""Tests for workflow phases."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.config import WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.executor import ExecutionResult, MockClaudeExecutor
from selfassembler.phases import (
    PHASE_CLASSES,
    PHASE_NAMES,
    CodeReviewPhase,
    ImplementationPhase,
    PlanningPhase,
    PreflightPhase,
    ResearchPhase,
    SetupPhase,
)


class TestPhaseRegistry:
    """Tests for phase registry."""

    def test_all_phases_registered(self):
        """Test that all phases are registered."""
        assert len(PHASE_CLASSES) == 16
        assert len(PHASE_NAMES) == 16

    def test_phase_names_match(self):
        """Test that phase names match class names."""
        for phase_class in PHASE_CLASSES:
            assert phase_class.name in PHASE_NAMES

    def test_phase_order(self):
        """Test that phases are in expected order."""
        expected_order = [
            "preflight",
            "setup",
            "research",
            "planning",
            "implementation",
            "test_writing",
            "test_execution",
            "code_review",
            "fix_review_issues",
            "lint_check",
            "documentation",
            "final_verification",
            "commit_prep",
            "conflict_check",
            "pr_creation",
            "pr_self_review",
        ]
        assert PHASE_NAMES == expected_order


class TestPreflightPhase:
    """Tests for PreflightPhase."""

    @pytest.fixture
    def phase(self) -> PreflightPhase:
        """Create a preflight phase for testing."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        return PreflightPhase(context, executor, config)

    @patch("subprocess.run")
    def test_check_claude_cli_success(self, mock_run, phase: PreflightPhase):
        """Test Claude CLI check when installed."""
        mock_run.return_value = MagicMock(returncode=0, stdout="claude v1.0.0")
        result = phase._check_claude_cli()
        assert result["passed"] is True

    @patch("subprocess.run")
    def test_check_claude_cli_failure(self, mock_run, phase: PreflightPhase):
        """Test Claude CLI check when not installed."""
        mock_run.side_effect = FileNotFoundError()
        result = phase._check_claude_cli()
        assert result["passed"] is False
        assert "not installed" in result["message"].lower()


class TestResearchPhase:
    """Tests for ResearchPhase."""

    def test_phase_config(self):
        """Test research phase configuration."""
        assert ResearchPhase.claude_mode == "plan"
        assert "Read" in ResearchPhase.allowed_tools
        assert "Grep" in ResearchPhase.allowed_tools


class TestPlanningPhase:
    """Tests for PlanningPhase."""

    def test_has_approval_gate(self):
        """Test planning has approval gate by default."""
        assert PlanningPhase.approval_gate is True

    def test_phase_config(self):
        """Test planning phase configuration."""
        assert PlanningPhase.claude_mode == "plan"
        assert "Write" in PlanningPhase.allowed_tools


class TestImplementationPhase:
    """Tests for ImplementationPhase."""

    def test_has_edit_tools(self):
        """Test implementation has edit tools."""
        assert "Edit" in ImplementationPhase.allowed_tools
        assert "Write" in ImplementationPhase.allowed_tools
        assert "Bash" in ImplementationPhase.allowed_tools


class TestCodeReviewPhase:
    """Tests for CodeReviewPhase."""

    def test_fresh_context(self):
        """Test code review uses fresh context."""
        assert CodeReviewPhase.fresh_context is True
        assert CodeReviewPhase.claude_mode == "plan"
