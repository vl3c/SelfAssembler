"""Tests for Claude executor."""

from pathlib import Path

import pytest

from claudonomous.executor import ExecutionResult, MockClaudeExecutor


class TestExecutionResult:
    """Tests for ExecutionResult."""

    def test_duration_seconds(self):
        """Test duration conversion."""
        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.5,
            duration_ms=5000,
            num_turns=3,
            is_error=False,
            raw_output="{}",
        )
        assert result.duration_seconds == 5.0


class TestMockClaudeExecutor:
    """Tests for MockClaudeExecutor."""

    def test_default_response(self):
        """Test default mock response."""
        executor = MockClaudeExecutor()
        result = executor.execute("test prompt")

        assert result.session_id == "mock-session-123"
        assert not result.is_error
        assert result.cost_usd == 0.01

    def test_custom_response(self):
        """Test custom mock response."""
        custom_result = ExecutionResult(
            session_id="custom-session",
            output="Custom output",
            cost_usd=1.5,
            duration_ms=2000,
            num_turns=5,
            is_error=False,
            raw_output="{}",
        )

        executor = MockClaudeExecutor(responses={"keyword": custom_result})
        result = executor.execute("prompt with keyword in it")

        assert result.session_id == "custom-session"
        assert result.cost_usd == 1.5

    def test_call_history(self):
        """Test that calls are recorded."""
        executor = MockClaudeExecutor()

        executor.execute("prompt 1", permission_mode="plan")
        executor.execute("prompt 2", allowed_tools=["Read", "Write"])

        assert len(executor.call_history) == 2
        assert executor.call_history[0]["prompt"] == "prompt 1"
        assert executor.call_history[0]["permission_mode"] == "plan"
        assert executor.call_history[1]["allowed_tools"] == ["Read", "Write"]
