"""Tests for orchestrator agent fallback logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.config import FallbackConfig, WorkflowConfig
from selfassembler.errors import AgentExecutionError, FailureCategory
from selfassembler.executors.base import AgentExecutor, ExecutionResult
from selfassembler.phases import (
    DebatePhase,
    ImplementationPhase,
    LintCheckPhase,
    Phase,
    PhaseResult,
    TestExecutionPhase,
)


def _make_context(**overrides):
    """Create a minimal mock WorkflowContext."""
    ctx = MagicMock()
    ctx.task_name = "test-task"
    ctx.task_description = "Test task"
    ctx.repo_path = Path("/tmp/test-repo")
    ctx.plans_dir = Path("/tmp/test-repo/plans")
    ctx.worktree_path = None
    ctx.budget_limit_usd = 100.0
    ctx.total_cost_usd = 0.0
    ctx.completed_phases = set()
    ctx.current_phase = None
    ctx.branch_name = None
    ctx.branch_pushed = False
    ctx.pr_url = None
    ctx.pr_number = None
    ctx.phase_costs = {}

    def budget_remaining():
        return ctx.budget_limit_usd - ctx.total_cost_usd

    ctx.budget_remaining = budget_remaining
    ctx.get_working_dir.return_value = ctx.repo_path
    ctx.get_artifact.return_value = []

    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _make_executor(agent_type="claude", success=True, output="done", cost=0.5, is_error=False):
    """Create a mock executor."""
    executor = MagicMock(spec=AgentExecutor)
    executor.AGENT_TYPE = agent_type
    executor.working_dir = Path("/tmp/test-repo")
    result = ExecutionResult(
        session_id="sess-1",
        output=output,
        cost_usd=cost,
        duration_ms=1000,
        num_turns=5,
        is_error=is_error or not success,
        raw_output=output,
        agent_type=agent_type,
    )
    executor.execute.return_value = result
    executor.check_available.return_value = (True, "v1.0")
    return executor


def _make_config(**fallback_overrides):
    """Create a WorkflowConfig with fallback settings."""
    config = WorkflowConfig()
    fb_kwargs = {"max_fallback_attempts": 1, "trigger": "agent_errors"}
    fb_kwargs.update(fallback_overrides)
    config.fallback = FallbackConfig(**fb_kwargs)
    return config


class TestShouldAttemptFallback:
    """Tests for Orchestrator._should_attempt_fallback."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        """Create an Orchestrator with mocked dependencies."""
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_oscillating_allows_fallback_for_non_multiagent_phases(self):
        """Oscillating failures from phases without built-in agent alternation
        should be eligible for fallback (no longer categorically blocked)."""
        config = _make_config(trigger="all_errors")
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = _make_executor("claude")
        result = PhaseResult(
            success=False,
            error="oscillation detected",
            failure_category=FailureCategory.OSCILLATING,
        )
        assert orch._should_attempt_fallback(result, phase) is True

    def test_excluded_phase_commit_prep(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "commit_prep"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_excluded_phase_pr_creation(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "pr_creation"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_excluded_phase_pr_self_review(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "pr_self_review"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_excluded_phase_preflight(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "preflight"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_excluded_phase_setup(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "setup"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_debate_phase_excluded(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=DebatePhase)
        phase.name = "research"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_lint_check_phase_excluded(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=LintCheckPhase)
        phase.name = "lint_check"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_test_execution_phase_excluded(self):
        """TestExecutionPhase has built-in agent alternation, so it's excluded
        from fallback (like LintCheckPhase and DebatePhase)."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=TestExecutionPhase)
        phase.name = "test_execution"
        result = PhaseResult(success=False, error="test fix oscillation")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_agent_error_triggers_in_agent_errors_mode(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        result = PhaseResult(success=False, error="rate limit exceeded on API call")
        assert orch._should_attempt_fallback(result, phase) is True

    def test_task_error_does_not_trigger_in_agent_errors_mode(self):
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        result = PhaseResult(success=False, error="TypeError: undefined is not a function")
        assert orch._should_attempt_fallback(result, phase) is False

    def test_task_error_triggers_in_all_errors_mode(self):
        config = _make_config(trigger="all_errors")
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        result = PhaseResult(success=False, error="TypeError: undefined is not a function")
        assert orch._should_attempt_fallback(result, phase) is True

    def test_agent_error_triggers_in_all_errors_mode(self):
        config = _make_config(trigger="all_errors")
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is True


class TestAttemptFallback:
    """Tests for Orchestrator._attempt_fallback."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_successful_fallback_returns_result_with_warning(self):
        """Successful fallback returns PhaseResult with warning about fallback."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(success=True, cost_usd=1.0)

        primary_result = PhaseResult(success=False, error="rate limit exceeded")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is not None
        assert result.success is True
        assert result.executed_by == "codex"
        assert any("fallback" in w for w in result.warnings)

    def test_executor_swap_and_restore(self):
        """Phase executor is swapped during fallback and restored in finally block."""
        orch = self._make_orchestrator()
        original_executor = MagicMock(spec=AgentExecutor)
        original_executor.AGENT_TYPE = "claude"
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = original_executor
        phase.run.return_value = PhaseResult(success=True)

        primary_result = PhaseResult(success=False, error="rate limit")
        orch._attempt_fallback(phase, primary_result)

        # Executor should be restored to original after fallback
        assert phase.executor is original_executor

    def test_executor_restored_on_exception(self):
        """Phase executor is restored even when fallback raises an exception."""
        orch = self._make_orchestrator()
        original_executor = MagicMock(spec=AgentExecutor)
        original_executor.AGENT_TYPE = "claude"
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = original_executor
        phase.run.side_effect = RuntimeError("unexpected")

        primary_result = PhaseResult(success=False, error="rate limit")
        with pytest.raises(RuntimeError):
            orch._attempt_fallback(phase, primary_result)

        assert phase.executor is original_executor

    def test_failed_fallback_returns_none(self):
        """When fallback fails with a task error, returns None."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(success=False, error="still broken")

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is None

    def test_early_stop_on_fallback_agent_error(self):
        """Stop fallback attempts early if fallback agent also hits agent-specific error."""
        config = _make_config(max_fallback_attempts=3)
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        # Fallback agent also hits rate limit
        phase.run.return_value = PhaseResult(
            success=False, error="rate limit on fallback agent too"
        )

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is None
        # Should have stopped after first attempt, not exhausted all 3
        assert phase.run.call_count == 1

    def test_respects_max_fallback_attempts(self):
        """Fallback respects max_fallback_attempts setting."""
        config = _make_config(max_fallback_attempts=3)
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        # Fail with non-agent error each time (won't trigger early stop)
        phase.run.return_value = PhaseResult(
            success=False, error="implementation still broken"
        )

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is None
        assert phase.run.call_count == 3

    def test_no_fallback_executor_returns_none(self):
        """Returns None when fallback_executor is None."""
        orch = self._make_orchestrator()
        orch.fallback_executor = None
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor

        result = orch._attempt_fallback(
            phase, PhaseResult(success=False, error="rate limit")
        )
        assert result is None

    def test_agent_execution_error_caught(self):
        """AgentExecutionError from fallback executor is caught and handled."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.side_effect = AgentExecutionError(
            "Fallback agent crashed", agent_type="codex"
        )

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        # AgentExecutionError should be caught (classified as agent error => early stop)
        assert result is None
        # Executor should be restored
        assert phase.executor is orch.executor


class TestRunPhaseIntegration:
    """Integration tests for _run_phase with fallback logic."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_normal_success_no_fallback(self):
        """Successful primary execution doesn't trigger fallback."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(success=True, cost_usd=1.0)
        phase.validate_preconditions.return_value = (True, "")
        phase.approval_gate = False

        result = orch._run_phase(phase)

        assert result.success is True
        # Fallback should not be called
        assert orch.fallback_executor.execute.call_count == 0

    def test_agent_error_triggers_fallback(self):
        """Agent error on primary triggers fallback which succeeds."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor

        # Primary fails with agent error, fallback succeeds
        call_count = [0]
        def run_side_effect():
            call_count[0] += 1
            if phase.executor is orch.fallback_executor:
                return PhaseResult(success=True, cost_usd=0.5)
            return PhaseResult(success=False, error="rate limit exceeded on API")

        phase.run.side_effect = run_side_effect
        phase.validate_preconditions.return_value = (True, "")
        phase.approval_gate = False

        result = orch._run_phase(phase)

        assert result.success is True
        assert result.executed_by == "codex"

    def test_task_error_no_fallback_in_agent_errors_mode(self):
        """Task error doesn't trigger fallback in agent_errors mode."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(
            success=False, error="TypeError: cannot read property"
        )
        phase.validate_preconditions.return_value = (True, "")

        with pytest.raises(Exception):  # PhaseFailedError
            orch._run_phase(phase)

    def test_both_primary_and_fallback_fail(self):
        """When both primary and fallback fail, raises PhaseFailedError."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        # Both fail with different errors
        phase.run.return_value = PhaseResult(
            success=False, error="rate limit exceeded"
        )
        phase.validate_preconditions.return_value = (True, "")

        with pytest.raises(Exception):  # PhaseFailedError
            orch._run_phase(phase)

    def test_no_fallback_executor_no_fallback(self):
        """No fallback when no fallback executor is available."""
        orch = self._make_orchestrator()
        orch.fallback_executor = None
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(
            success=False, error="rate limit exceeded"
        )
        phase.validate_preconditions.return_value = (True, "")

        with pytest.raises(Exception):  # PhaseFailedError
            orch._run_phase(phase)

    def test_agent_execution_error_caught_in_run_phase(self):
        """AgentExecutionError from phase.run() is caught and converted to PhaseResult."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor

        call_count = [0]
        def run_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise AgentExecutionError("CLI crashed", agent_type="claude")
            # Fallback succeeds
            return PhaseResult(success=True, cost_usd=0.5)

        phase.run.side_effect = run_side_effect
        phase.validate_preconditions.return_value = (True, "")
        phase.approval_gate = False

        result = orch._run_phase(phase)

        assert result.success is True

    def test_no_spurious_failure_notification_before_successful_fallback(self):
        """No 'phase failed (will not retry)' notification when fallback succeeds."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor

        call_count = [0]
        def run_side_effect():
            call_count[0] += 1
            if phase.executor is orch.fallback_executor:
                return PhaseResult(success=True, cost_usd=0.5)
            return PhaseResult(success=False, error="rate limit exceeded")

        phase.run.side_effect = run_side_effect
        phase.validate_preconditions.return_value = (True, "")
        phase.approval_gate = False

        result = orch._run_phase(phase)

        assert result.success is True

        # Verify on_phase_failed was never called with will_retry=False
        for call in orch.notifier.on_phase_failed.call_args_list:
            args, kwargs = call
            # args: (phase_name, result, will_retry) or kwargs
            will_retry = kwargs.get("will_retry", args[2] if len(args) > 2 else None)
            assert will_retry is not False, (
                "on_phase_failed called with will_retry=False before successful fallback"
            )


class TestFallbackConfig:
    """Tests for FallbackConfig model."""

    def test_default_values(self):
        config = FallbackConfig()
        assert config.fallback_agent is None
        assert config.max_fallback_attempts == 1
        assert config.trigger == "agent_errors"

    def test_custom_values(self):
        config = FallbackConfig(
            fallback_agent="codex",
            max_fallback_attempts=3,
            trigger="all_errors",
        )
        assert config.fallback_agent == "codex"
        assert config.max_fallback_attempts == 3
        assert config.trigger == "all_errors"

    def test_trigger_validation(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FallbackConfig(trigger="invalid")

    def test_max_attempts_validation(self):
        from pydantic import ValidationError

        FallbackConfig(max_fallback_attempts=0)  # Valid
        FallbackConfig(max_fallback_attempts=5)  # Valid

        with pytest.raises(ValidationError):
            FallbackConfig(max_fallback_attempts=-1)
        with pytest.raises(ValidationError):
            FallbackConfig(max_fallback_attempts=6)

    def test_in_workflow_config(self):
        config = WorkflowConfig()
        assert hasattr(config, "fallback")
        assert isinstance(config.fallback, FallbackConfig)

    def test_in_to_dict(self):
        config = WorkflowConfig()
        data = config.to_dict()
        assert "fallback" in data
        assert data["fallback"]["trigger"] == "agent_errors"


class TestFallbackConfigYAML:
    """Tests for loading FallbackConfig from YAML."""

    def test_load_fallback_from_yaml(self, tmp_path):
        config_path = tmp_path / "selfassembler.yaml"
        config_path.write_text(
            "fallback:\n"
            "  fallback_agent: codex\n"
            "  max_fallback_attempts: 2\n"
            "  trigger: all_errors\n"
        )
        config = WorkflowConfig.load(config_path)
        assert config.fallback.fallback_agent == "codex"
        assert config.fallback.max_fallback_attempts == 2
        assert config.fallback.trigger == "all_errors"

    def test_load_fallback_defaults_when_absent(self, tmp_path):
        config_path = tmp_path / "selfassembler.yaml"
        config_path.write_text("budget_limit_usd: 20.0\n")
        config = WorkflowConfig.load(config_path)
        assert config.fallback.fallback_agent is None

    def test_save_and_load_roundtrip(self, tmp_path):
        config_path = tmp_path / "selfassembler.yaml"
        config = WorkflowConfig()
        config.fallback.fallback_agent = "codex"
        config.save(config_path)

        loaded = WorkflowConfig.load(config_path)
        assert loaded.fallback.fallback_agent == "codex"


class TestCreateFallbackExecutor:
    """Tests for Orchestrator._create_fallback_executor."""

    def _make_orchestrator(self, config=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = None
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
            orch._stream_callback = None
        return orch

    @patch("selfassembler.executors.detect_installed_agents")
    @patch("selfassembler.orchestrator.create_executor")
    def test_auto_detect_different_agent(self, mock_create, mock_detect):
        """Auto-detect picks a different installed agent."""
        mock_detect.return_value = {"claude": True, "codex": True}
        mock_create.return_value = _make_executor("codex")

        orch = self._make_orchestrator()
        result = orch._create_fallback_executor(Path("/tmp/test"))

        assert result is not None
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[1]["agent_type"] == "codex" or call_kwargs[0][0] == "codex"

    @patch("selfassembler.executors.detect_installed_agents")
    def test_auto_detect_no_alternative(self, mock_detect):
        """Auto-detect returns None when no alternative agent is installed."""
        mock_detect.return_value = {"claude": True, "codex": False}

        orch = self._make_orchestrator()
        result = orch._create_fallback_executor(Path("/tmp/test"))

        assert result is None

    @patch("selfassembler.orchestrator.create_executor")
    def test_explicit_fallback_agent(self, mock_create):
        """Explicit fallback_agent config is used directly."""
        mock_create.return_value = _make_executor("codex")

        config = _make_config(fallback_agent="codex")
        orch = self._make_orchestrator(config=config)
        result = orch._create_fallback_executor(Path("/tmp/test"))

        assert result is not None
        mock_create.assert_called_once()

    @patch("selfassembler.orchestrator.create_executor")
    def test_explicit_same_agent_type(self, mock_create):
        """Explicit fallback_agent can be same as primary (fresh session)."""
        mock_create.return_value = _make_executor("claude")

        config = _make_config(fallback_agent="claude")
        orch = self._make_orchestrator(config=config)
        result = orch._create_fallback_executor(Path("/tmp/test"))

        assert result is not None
        mock_create.assert_called_once()


class TestAdditionalShouldAttemptFallback:
    """Additional tests for _should_attempt_fallback from review feedback."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_conflict_check_excluded(self):
        """conflict_check is excluded — git rebase/stash not safely re-entrant."""
        orch = self._make_orchestrator()
        phase = MagicMock(spec=Phase)
        phase.name = "conflict_check"
        result = PhaseResult(success=False, error="rate limit exceeded")
        assert orch._should_attempt_fallback(result, phase) is False


class TestAdditionalAttemptFallback:
    """Additional tests for _attempt_fallback from review feedback."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_max_fallback_attempts_zero(self):
        """max_fallback_attempts=0 means zero attempts, returns None."""
        config = _make_config(max_fallback_attempts=0)
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(success=True)

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is None
        assert phase.run.call_count == 0

    def test_early_stop_on_failure_category_agent_specific(self):
        """Early stop triggers when PhaseResult has AGENT_SPECIFIC category,
        even if error text doesn't match classifier patterns."""
        config = _make_config(max_fallback_attempts=3)
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        # Error text doesn't match any classifier pattern, but category is set
        phase.run.return_value = PhaseResult(
            success=False,
            error="some opaque CLI crash",
            failure_category=FailureCategory.AGENT_SPECIFIC,
        )

        primary_result = PhaseResult(success=False, error="rate limit")
        result = orch._attempt_fallback(phase, primary_result)

        assert result is None
        # Should stop after 1 attempt (not exhaust all 3)
        assert phase.run.call_count == 1


class TestAdditionalRunPhaseIntegration:
    """Additional integration tests from review feedback."""

    def _make_orchestrator(self, config=None, fallback_executor=None):
        from selfassembler.orchestrator import Orchestrator

        ctx = _make_context()
        config = config or _make_config()
        executor = _make_executor()

        with patch.object(Orchestrator, "__init__", lambda self, *a, **kw: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.context = ctx
            orch.config = config
            orch.executor = executor
            orch.fallback_executor = fallback_executor or _make_executor("codex")
            orch.secondary_executor = None
            orch.notifier = MagicMock()
            orch.logger = MagicMock()
            orch.checkpoint_manager = MagicMock()
            orch.approval_store = MagicMock()
        return orch

    def test_all_errors_mode_task_error_triggers_successful_fallback(self):
        """In all_errors mode, a task error triggers fallback which succeeds."""
        config = _make_config(trigger="all_errors")
        orch = self._make_orchestrator(config=config)
        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor

        def run_side_effect():
            if phase.executor is orch.fallback_executor:
                return PhaseResult(success=True, cost_usd=0.5)
            return PhaseResult(success=False, error="TypeError: cannot read property")

        phase.run.side_effect = run_side_effect
        phase.validate_preconditions.return_value = (True, "")
        phase.approval_gate = False

        result = orch._run_phase(phase)

        assert result.success is True
        assert result.executed_by == "codex"

    def test_no_fallback_when_budget_exhausted(self):
        """Fallback is skipped when budget is exhausted."""
        orch = self._make_orchestrator()
        # Exhaust the budget
        orch.context.total_cost_usd = orch.context.budget_limit_usd

        phase = MagicMock(spec=ImplementationPhase)
        phase.name = "implementation"
        phase.executor = orch.executor
        phase.run.return_value = PhaseResult(
            success=False, error="rate limit exceeded"
        )
        phase.validate_preconditions.return_value = (True, "")

        with pytest.raises(Exception):  # PhaseFailedError
            orch._run_phase(phase)
