"""Tests for workflow phases."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.config import WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.executors import MockClaudeExecutor, MockCodexExecutor
from selfassembler.phases import (
    PHASE_CLASSES,
    PHASE_NAMES,
    CodeReviewPhase,
    ImplementationPhase,
    PlanningPhase,
    PlanReviewPhase,
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
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )

    @pytest.fixture
    def phase(self, context: WorkflowContext) -> PreflightPhase:
        """Create a preflight phase for testing."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        return PreflightPhase(context, executor, config)

    def test_check_agent_cli_success(self, context: WorkflowContext):
        """Test agent CLI check when installed (using mock)."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        # Mock check_available returns (True, version) for MockClaudeExecutor
        with patch.object(executor, "check_available", return_value=(True, "v1.0.0")):
            result = phase._check_agent_cli()

        assert result["passed"] is True
        assert result["name"] == "claude_cli"

    def test_check_agent_cli_failure(self, context: WorkflowContext):
        """Test agent CLI check when not available."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        with patch.object(executor, "check_available", return_value=(False, "not found")):
            result = phase._check_agent_cli()

        assert result["passed"] is False
        assert "not working" in result["message"].lower()

    def test_check_agent_cli_codex(self, context: WorkflowContext):
        """Test agent CLI check uses codex when configured."""
        executor = MockCodexExecutor()
        config = WorkflowConfig()
        config.agent.type = "codex"
        phase = PreflightPhase(context, executor, config)

        with patch.object(executor, "check_available", return_value=(True, "v0.1.0")):
            result = phase._check_agent_cli()

        assert result["passed"] is True
        assert result["name"] == "codex_cli"

    def test_check_agent_cli_includes_agent_type_in_name(self, context: WorkflowContext):
        """Test check name includes agent type."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        with patch.object(executor, "check_available", return_value=(True, "v1.0")):
            result = phase._check_agent_cli()

        # Name should include agent type
        assert "claude" in result["name"]


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


class TestPhasePermissionModeHelper:
    """Tests for _get_permission_mode helper method."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )

    @pytest.fixture
    def config(self) -> WorkflowConfig:
        """Create a config for testing."""
        return WorkflowConfig()

    def test_read_only_phase_returns_claude_mode(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that phases with claude_mode='plan' return 'plan'."""
        executor = MockClaudeExecutor()
        phase = ResearchPhase(context, executor, config)

        # ResearchPhase has claude_mode = "plan"
        assert phase._get_permission_mode() == "plan"

    def test_write_phase_returns_accept_edits(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that write phases without claude_mode return 'acceptEdits'."""
        executor = MockClaudeExecutor()
        phase = ImplementationPhase(context, executor, config)

        # ImplementationPhase has Write, Edit, Bash in allowed_tools
        # but no claude_mode set
        assert phase._get_permission_mode() == "acceptEdits"

    def test_planning_phase_returns_accept_edits_for_write_tool(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that planning phase returns 'acceptEdits' because it has Write tool."""
        executor = MockClaudeExecutor()
        phase = PlanningPhase(context, executor, config)

        # PlanningPhase has Write in allowed_tools
        # Write tools take priority over claude_mode for Codex compatibility
        assert phase._get_permission_mode() == "acceptEdits"

    def test_code_review_returns_plan_despite_bash_tool(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that code review phase returns 'plan' - Bash is not a write tool."""
        executor = MockClaudeExecutor()
        phase = CodeReviewPhase(context, executor, config)

        # CodeReviewPhase has Bash in allowed_tools but Bash is NOT a write tool
        # (it's used for read-only ops like git diff), so claude_mode takes precedence
        assert phase._get_permission_mode() == "plan"

    def test_requires_write_returns_accept_edits(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that phases with requires_write=True return 'acceptEdits'."""
        from selfassembler.phases import CommitPrepPhase, PRCreationPhase

        executor = MockClaudeExecutor()

        # These phases only have Bash/Read but set requires_write=True
        # for git operations that need write access
        for phase_class in [CommitPrepPhase, PRCreationPhase]:
            phase = phase_class(context, executor, config)
            assert phase.requires_write is True
            assert phase._get_permission_mode() == "acceptEdits", (
                f"{phase_class.__name__} should return 'acceptEdits' due to requires_write"
            )

    def test_all_write_phases_return_accept_edits(self, context: WorkflowContext, config: WorkflowConfig):
        """Test that all phases with write tools but no claude_mode return acceptEdits."""
        from selfassembler.phases import (
            TestWritingPhase,
            TestExecutionPhase,
            FixReviewIssuesPhase,
            LintCheckPhase,
            DocumentationPhase,
            CommitPrepPhase,
            ConflictCheckPhase,
            PRCreationPhase,
        )

        executor = MockClaudeExecutor()

        # These phases need write access via:
        # - Write/Edit in allowed_tools, or
        # - requires_write = True (for Bash-based git operations)
        write_phases = [
            ImplementationPhase,
            TestWritingPhase,
            TestExecutionPhase,  # has Edit
            FixReviewIssuesPhase,
            LintCheckPhase,  # has Edit
            DocumentationPhase,
            ConflictCheckPhase,  # has Edit
            CommitPrepPhase,  # requires_write for git commit
            PRCreationPhase,  # requires_write for git push/gh pr
        ]

        for phase_class in write_phases:
            phase = phase_class(context, executor, config)
            # If claude_mode is set, it should use that
            if phase.claude_mode is not None:
                assert phase._get_permission_mode() == phase.claude_mode
            else:
                # Otherwise should return acceptEdits for write phases
                assert phase._get_permission_mode() == "acceptEdits", (
                    f"{phase_class.__name__} should return 'acceptEdits'"
                )


class TestDangerousModeConfig:
    """Tests for _dangerous_mode using agent config."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path.cwd(),
            plans_dir=Path.cwd() / "plans",
        )

    def test_dangerous_mode_uses_agent_config(self, context: WorkflowContext):
        """Test that _dangerous_mode reads from agent config."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()

        # Enable autonomous mode and agent.dangerous_mode
        config.autonomous_mode = True
        config.agent.dangerous_mode = True

        phase = ImplementationPhase(context, executor, config)

        assert phase._dangerous_mode() is True

    def test_dangerous_mode_false_when_not_autonomous(self, context: WorkflowContext):
        """Test that _dangerous_mode is False when not in autonomous mode."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()

        config.autonomous_mode = False
        config.agent.dangerous_mode = True

        phase = ImplementationPhase(context, executor, config)

        assert phase._dangerous_mode() is False

    def test_dangerous_mode_false_when_agent_dangerous_disabled(self, context: WorkflowContext):
        """Test that _dangerous_mode is False when agent.dangerous_mode is False."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()

        config.autonomous_mode = True
        config.agent.dangerous_mode = False

        phase = ImplementationPhase(context, executor, config)

        assert phase._dangerous_mode() is False

    def test_dangerous_mode_inherits_from_legacy_claude_config(self, context: WorkflowContext):
        """Test that _dangerous_mode can inherit from legacy claude config."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()

        # Only set legacy config, agent config defaults to False
        config.autonomous_mode = True
        config.claude.dangerous_mode = True
        config.agent.dangerous_mode = False  # Not set

        phase = ImplementationPhase(context, executor, config)

        # get_effective_agent_config should merge legacy config
        effective = config.get_effective_agent_config()
        # When agent.dangerous_mode is False but claude.dangerous_mode is True,
        # effective should be True (for claude agent)
        assert effective.dangerous_mode is True

        # Therefore _dangerous_mode should return True
        assert phase._dangerous_mode() is True


class TestPreflightGitAutoUpdate:
    """Tests for preflight auto-update git behavior."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/test/repo"),
            plans_dir=Path("/test/repo/plans"),
        )

    @pytest.fixture
    def executor(self) -> MockClaudeExecutor:
        """Create a mock executor."""
        return MockClaudeExecutor()

    def test_git_updated_check_up_to_date(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated check when already up to date."""
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        mock_git.commits_behind.return_value = 0

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is True
        assert result["name"] == "git_updated"
        # Should not have called checkout or pull
        mock_git.checkout.assert_not_called()
        mock_git.pull.assert_not_called()

    def test_git_updated_auto_pulls_when_behind(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated check auto-pulls when behind."""
        config = WorkflowConfig()
        config.git.auto_update = True
        config.git.base_branch = "main"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        # First call returns 5 behind, second call (after pull) returns 0
        mock_git.commits_behind.side_effect = [5, 0]

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is True
        mock_git.pull.assert_called_once()

    def test_git_updated_checkouts_base_branch(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated check checkouts base branch if not on it."""
        config = WorkflowConfig()
        config.git.auto_update = True
        config.git.base_branch = "main"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature/old-branch"
        mock_git.commits_behind.return_value = 0

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is True
        mock_git.checkout.assert_called_once_with("main")

    def test_git_updated_no_checkout_when_auto_update_disabled(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated doesn't checkout when auto_update is disabled."""
        config = WorkflowConfig()
        config.git.auto_update = False
        config.git.base_branch = "main"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature/other"
        mock_git.commits_behind.return_value = 0

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            phase._check_git_updated()

        mock_git.checkout.assert_not_called()

    def test_git_updated_no_pull_when_auto_update_disabled(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated doesn't pull when auto_update is disabled."""
        config = WorkflowConfig()
        config.git.auto_update = False
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        mock_git.commits_behind.return_value = 5

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is False
        assert "5 commits behind" in result["message"]
        mock_git.pull.assert_not_called()

    def test_git_updated_checkout_failure(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated handles checkout failure."""
        config = WorkflowConfig()
        config.git.auto_update = True
        config.git.base_branch = "main"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature/old"
        mock_git.checkout.side_effect = Exception("checkout failed")

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is False
        assert "Failed to checkout" in result["message"]

    def test_git_updated_pull_failure(self, context: WorkflowContext, executor: MockClaudeExecutor):
        """Test git updated handles pull failure."""
        config = WorkflowConfig()
        config.git.auto_update = True
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        mock_git.commits_behind.return_value = 5
        mock_git.pull.side_effect = Exception("merge conflict")

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is False
        assert "Auto-pull failed" in result["message"]

    def test_git_updated_still_behind_after_pull(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated fails when still behind after pull."""
        config = WorkflowConfig()
        config.git.auto_update = True
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        # Still behind after pull
        mock_git.commits_behind.side_effect = [5, 3]

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is False
        assert "3 commits behind" in result["message"]

    def test_git_updated_uses_configured_base_branch(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated uses configured base branch."""
        config = WorkflowConfig()
        config.git.auto_update = True
        config.git.base_branch = "develop"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature/test"
        mock_git.commits_behind.return_value = 0

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            phase._check_git_updated()

        mock_git.checkout.assert_called_once_with("develop")
        mock_git.commits_behind.assert_called_with("develop")

    def test_git_updated_master_branch(
        self, context: WorkflowContext, executor: MockClaudeExecutor
    ):
        """Test git updated works with master as base branch."""
        config = WorkflowConfig()
        config.git.auto_update = True
        config.git.base_branch = "master"
        phase = PreflightPhase(context, executor, config)

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "master"
        mock_git.commits_behind.return_value = 0

        with patch("selfassembler.phases.GitManager", return_value=mock_git):
            result = phase._check_git_updated()

        assert result["passed"] is True
        mock_git.checkout.assert_not_called()  # Already on master


class TestPreflightRun:
    """Tests for PreflightPhase.run() method."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a workflow context for testing."""
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/test/repo"),
            plans_dir=Path("/test/repo/plans"),
        )

    def test_run_all_checks_pass(self, context: WorkflowContext):
        """Test run succeeds when all checks pass."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        with patch.object(
            phase, "_check_agent_cli", return_value={"name": "agent_cli", "passed": True}
        ), patch.object(
            phase, "_check_gh_cli", return_value={"name": "gh_cli", "passed": True}
        ), patch.object(
            phase, "_check_git_clean", return_value={"name": "git_clean", "passed": True}
        ), patch.object(
            phase,
            "_check_git_updated",
            return_value={"name": "git_updated", "passed": True},
        ):
            result = phase.run()

        assert result.success is True
        assert "checks" in result.artifacts

    def test_run_fails_on_agent_cli_failure(self, context: WorkflowContext):
        """Test run fails when agent CLI check fails."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        with patch.object(
            phase,
            "_check_agent_cli",
            return_value={"name": "agent_cli", "passed": False, "message": "CLI not found"},
        ), patch.object(
            phase, "_check_gh_cli", return_value={"name": "gh_cli", "passed": True}
        ), patch.object(
            phase, "_check_git_clean", return_value={"name": "git_clean", "passed": True}
        ), patch.object(
            phase,
            "_check_git_updated",
            return_value={"name": "git_updated", "passed": True},
        ):
            result = phase.run()

        assert result.success is False
        assert "CLI not found" in result.error

    def test_run_fails_on_git_updated_failure(self, context: WorkflowContext):
        """Test run fails when git updated check fails."""
        executor = MockClaudeExecutor()
        config = WorkflowConfig()
        phase = PreflightPhase(context, executor, config)

        with patch.object(
            phase, "_check_agent_cli", return_value={"name": "agent_cli", "passed": True}
        ), patch.object(
            phase, "_check_gh_cli", return_value={"name": "gh_cli", "passed": True}
        ), patch.object(
            phase, "_check_git_clean", return_value={"name": "git_clean", "passed": True}
        ), patch.object(
            phase,
            "_check_git_updated",
            return_value={
                "name": "git_updated",
                "passed": False,
                "message": "5 commits behind",
            },
        ):
            result = phase.run()

        assert result.success is False
        assert "5 commits behind" in result.error
