"""Tests for Claude executor."""

from pathlib import Path

import pytest

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
    """Tests for StreamEvent."""

    def test_from_line_valid_json(self):
        """Test parsing valid JSON line."""
        line = '{"type": "tool_use", "name": "Read", "input": {}}'
        event = StreamEvent.from_line(line)

        assert event is not None
        assert event.event_type == "tool_use"
        assert event.data["name"] == "Read"

    def test_from_line_with_whitespace(self):
        """Test parsing line with whitespace."""
        line = '  {"type": "assistant", "content": "Hello"}  \n'
        event = StreamEvent.from_line(line)

        assert event is not None
        assert event.event_type == "assistant"

    def test_from_line_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        line = "not valid json"
        event = StreamEvent.from_line(line)

        assert event is None

    def test_from_line_empty_line(self):
        """Test parsing empty line returns None."""
        line = "   "
        event = StreamEvent.from_line(line)

        assert event is None

    def test_from_line_unknown_type(self):
        """Test parsing event without type field."""
        line = '{"content": "test"}'
        event = StreamEvent.from_line(line)

        assert event is not None
        assert event.event_type == "unknown"

    def test_timestamp_auto_set(self):
        """Test that timestamp is automatically set."""
        line = '{"type": "test"}'
        event = StreamEvent.from_line(line)

        assert event is not None
        assert event.timestamp > 0
