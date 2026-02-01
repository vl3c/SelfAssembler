"""Tests for error classes."""

import pytest

from selfassembler.errors import (
    AgentExecutionError,
    BudgetExceededError,
    ClaudeExecutionError,
    GitOperationError,
    PhaseFailedError,
    PreflightFailedError,
    SelfAssemblerError,
)


class TestSelfAssemblerError:
    """Tests for base SelfAssemblerError."""

    def test_is_base_exception(self):
        """Test SelfAssemblerError is base for all errors."""
        error = SelfAssemblerError("test error")
        assert isinstance(error, Exception)

    def test_message(self):
        """Test error message."""
        error = SelfAssemblerError("test message")
        assert str(error) == "test message"


class TestAgentExecutionError:
    """Tests for AgentExecutionError."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = AgentExecutionError("Execution failed")

        assert str(error) == "Execution failed"
        assert error.output == ""
        assert error.returncode == 1
        assert error.agent_type == "unknown"

    def test_with_all_fields(self):
        """Test error with all fields."""
        error = AgentExecutionError(
            message="Command failed",
            output="stderr output",
            returncode=127,
            agent_type="claude",
        )

        assert str(error) == "Command failed"
        assert error.output == "stderr output"
        assert error.returncode == 127
        assert error.agent_type == "claude"

    def test_inherits_from_base(self):
        """Test it inherits from SelfAssemblerError."""
        error = AgentExecutionError("test")
        assert isinstance(error, SelfAssemblerError)

    def test_can_be_caught_as_selfassembler_error(self):
        """Test can be caught as SelfAssemblerError."""
        with pytest.raises(SelfAssemblerError):
            raise AgentExecutionError("test")


class TestClaudeExecutionErrorAlias:
    """Tests for ClaudeExecutionError backward compatibility alias."""

    def test_is_same_as_agent_execution_error(self):
        """Test ClaudeExecutionError is AgentExecutionError."""
        assert ClaudeExecutionError is AgentExecutionError

    def test_can_create_claude_execution_error(self):
        """Test can create ClaudeExecutionError."""
        error = ClaudeExecutionError("test error")
        assert isinstance(error, AgentExecutionError)
        assert isinstance(error, SelfAssemblerError)

    def test_can_catch_as_claude_execution_error(self):
        """Test can catch AgentExecutionError as ClaudeExecutionError."""
        with pytest.raises(ClaudeExecutionError):
            raise AgentExecutionError("test")

    def test_fields_work_on_alias(self):
        """Test fields work on the alias."""
        error = ClaudeExecutionError(
            message="test",
            output="output",
            returncode=2,
            agent_type="claude",
        )

        assert error.output == "output"
        assert error.returncode == 2
        assert error.agent_type == "claude"


class TestBudgetExceededError:
    """Tests for BudgetExceededError."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = BudgetExceededError("Budget exceeded")

        assert "Budget exceeded" in str(error)
        assert error.current_cost == 0.0
        assert error.budget_limit == 0.0

    def test_with_cost_info(self):
        """Test error with cost information."""
        error = BudgetExceededError(
            message="Budget exceeded",
            current_cost=15.5,
            budget_limit=15.0,
        )

        assert error.current_cost == 15.5
        assert error.budget_limit == 15.0


class TestPreflightFailedError:
    """Tests for PreflightFailedError."""

    def test_single_failure(self):
        """Test with single failed check."""
        failed_checks = [{"name": "git_clean", "message": "Uncommitted changes"}]
        error = PreflightFailedError(failed_checks)

        assert "Preflight checks failed" in str(error)
        assert "Uncommitted changes" in str(error)
        assert error.failed_checks == failed_checks

    def test_multiple_failures(self):
        """Test with multiple failed checks."""
        failed_checks = [
            {"name": "git_clean", "message": "Uncommitted changes"},
            {"name": "cli", "message": "CLI not found"},
        ]
        error = PreflightFailedError(failed_checks)

        assert "Uncommitted changes" in str(error)
        assert "CLI not found" in str(error)


class TestPhaseFailedError:
    """Tests for PhaseFailedError."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = PhaseFailedError("planning")

        assert "planning" in str(error)
        assert error.phase == "planning"
        assert error.error is None
        assert error.artifacts == {}

    def test_with_error_message(self):
        """Test with error message."""
        error = PhaseFailedError("implementation", error="Timeout")

        assert "implementation" in str(error)
        assert "Timeout" in str(error)
        assert error.error == "Timeout"

    def test_with_artifacts(self):
        """Test with artifacts."""
        artifacts = {"session_id": "abc123"}
        error = PhaseFailedError("test", artifacts=artifacts)

        assert error.artifacts == artifacts


class TestGitOperationError:
    """Tests for GitOperationError."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = GitOperationError("checkout", "branch not found")

        assert "checkout" in str(error)
        assert "branch not found" in str(error)
        assert error.operation == "checkout"
        assert error.error == "branch not found"
        assert error.returncode == 1

    def test_with_returncode(self):
        """Test with custom return code."""
        error = GitOperationError("push", "permission denied", returncode=128)

        assert error.returncode == 128
