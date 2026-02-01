"""Tests for Claude executor (legacy compatibility tests).

This file maintains backward compatibility tests for the old import path.
New tests should be added to tests/test_executors/ directory.
"""

from selfassembler.executor import ExecutionResult, MockClaudeExecutor, StreamEvent


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


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""

    def test_basic_creation(self):
        """Test creating a StreamEvent."""
        event = StreamEvent(
            event_type="assistant",
            data={"content": "Hello"},
        )

        assert event.event_type == "assistant"
        assert event.data["content"] == "Hello"
        assert event.source == "unknown"

    def test_with_source(self):
        """Test StreamEvent with source."""
        event = StreamEvent(
            event_type="tool_use",
            data={"name": "Read"},
            source="claude",
        )

        assert event.source == "claude"

    def test_timestamp_auto_set(self):
        """Test that timestamp is automatically set."""
        event = StreamEvent(
            event_type="test",
            data={},
        )

        assert event.timestamp > 0

    def test_various_event_types(self):
        """Test various event types."""
        for event_type in ["assistant", "tool_use", "result", "unknown"]:
            event = StreamEvent(event_type=event_type, data={})
            assert event.event_type == event_type


class TestBackwardCompatibility:
    """Tests for backward compatibility with old import paths."""

    def test_imports_from_executor_module(self):
        """Test that classes can be imported from selfassembler.executor."""
        from selfassembler.executor import (
            ClaudeExecutor,
            ExecutionResult,
            MockClaudeExecutor,
            StreamEvent,
        )

        assert ClaudeExecutor is not None
        assert MockClaudeExecutor is not None
        assert ExecutionResult is not None
        assert StreamEvent is not None

    def test_same_classes_as_executors_package(self):
        """Test that executor module exports same classes as executors package."""
        from selfassembler.executor import ClaudeExecutor as OldClaudeExecutor
        from selfassembler.executor import ExecutionResult as OldExecutionResult
        from selfassembler.executors import ClaudeExecutor as NewClaudeExecutor
        from selfassembler.executors import ExecutionResult as NewExecutionResult

        assert OldClaudeExecutor is NewClaudeExecutor
        assert OldExecutionResult is NewExecutionResult
