"""Tests for workflow phases."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.config import WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.executor import MockClaudeExecutor
from selfassembler.phases import (
    PHASE_CLASSES,
    PHASE_NAMES,
    CodeReviewPhase,
    ConflictCheckPhase,
    ImplementationPhase,
    PlanningPhase,
    PlanReviewPhase,
    PRCreationPhase,
    PreflightPhase,
    ResearchPhase,
)


class TestPhaseRegistry:
    """Tests for phase registry."""

    def test_all_phases_registered(self):
        """Test that all phases are registered."""
        assert len(PHASE_CLASSES) == 17
        assert len(PHASE_NAMES) == 17

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
            "plan_review",
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
        assert expected_order == PHASE_NAMES


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


class TestPlanReviewPhase:
    """Tests for PlanReviewPhase."""

    def test_fresh_context(self):
        """Test plan review uses fresh context."""
        assert PlanReviewPhase.fresh_context is True
        assert PlanReviewPhase.claude_mode == "plan"

    def test_no_approval_gate_by_default(self):
        """Test plan review has no approval gate by default."""
        assert PlanReviewPhase.approval_gate is False

    def test_has_write_tool(self):
        """Test plan review can write files."""
        assert "Write" in PlanReviewPhase.allowed_tools
        assert "Read" in PlanReviewPhase.allowed_tools


class TestCodeReviewPhase:
    """Tests for CodeReviewPhase."""

    def test_fresh_context(self):
        """Test code review uses fresh context."""
        assert CodeReviewPhase.fresh_context is True
        assert CodeReviewPhase.claude_mode == "plan"


class TestConflictCheckPhase:
    """Tests for ConflictCheckPhase."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )

    def test_stash_restored_on_rebase_error(self, context: WorkflowContext):
        """Ensure stash is restored when rebase raises an error."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = ConflictCheckPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.has_remote.return_value = True
        mock_git.stash.return_value = True
        mock_git.rebase.side_effect = Exception("rebase failed")

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase.run()

        assert result.success is False
        assert "rebase failed" in result.error
        mock_git.stash_pop.assert_called_once_with(cwd=phase.context.get_working_dir())

    def test_stash_popped_after_abort_on_conflicts(self, context: WorkflowContext):
        """Ensure stash is restored after aborting a conflicted rebase."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = ConflictCheckPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.has_remote.return_value = True
        mock_git.stash.return_value = True
        mock_git.rebase.return_value = (False, ["file.txt"])

        with patch("selfassembler.phases.GitManager", return_value=mock_git), patch.object(
            ConflictCheckPhase, "_resolve_conflicts_with_claude", return_value=False
        ):
            phase.run()

        calls = [call[0] for call in mock_git.method_calls]
        assert "abort_rebase" in calls
        assert "stash_pop" in calls
        assert calls.index("abort_rebase") < calls.index("stash_pop")

    def test_conflict_prompt_uses_rebase_target(self, context: WorkflowContext):
        """Ensure conflict prompt references the actual rebase target."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = ConflictCheckPhase(context, executor, config)

        executor.execute = MagicMock(
            return_value=MagicMock(is_error=False, cost_usd=0.0)
        )

        phase._resolve_conflicts_with_claude(["file.txt"], "origin/main")

        prompt = executor.execute.call_args.kwargs["prompt"]
        assert "origin/main" in prompt


class TestPRCreationPhase:
    """Tests for PRCreationPhase."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )

    def test_skips_when_no_remote(self, context: WorkflowContext):
        """PR creation should be skipped for local-only repos."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PRCreationPhase(context, executor, config)

        context.branch_name = "feature/test"

        mock_git = MagicMock()
        mock_git.has_remote.return_value = False

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase.run()

        assert result.success is True
        assert result.artifacts["skipped"].startswith("No remote configured")
        mock_git.push.assert_not_called()
