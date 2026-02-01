"""Tests for AgentExecutor abstract base class."""

from pathlib import Path

import pytest

from selfassembler.executors.base import AgentExecutor, ExecutionResult, StreamEvent


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_basic_creation(self):
        """Test creating an ExecutionResult with required fields."""
        result = ExecutionResult(
            session_id="test-session",
            output="test output",
            cost_usd=0.5,
            duration_ms=5000,
            num_turns=3,
            is_error=False,
            raw_output='{"result": "test"}',
        )

        assert result.session_id == "test-session"
        assert result.output == "test output"
        assert result.cost_usd == 0.5
        assert result.duration_ms == 5000
        assert result.num_turns == 3
        assert result.is_error is False
        assert result.raw_output == '{"result": "test"}'

    def test_default_values(self):
        """Test default values for optional fields."""
        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.0,
            duration_ms=1000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        assert result.subagent_results == []
        assert result.agent_type == "unknown"

    def test_agent_type_field(self):
        """Test that agent_type can be set."""
        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.0,
            duration_ms=1000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
            agent_type="claude",
        )

        assert result.agent_type == "claude"

    def test_duration_seconds(self):
        """Test duration conversion from ms to seconds."""
        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.0,
            duration_ms=5000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        assert result.duration_seconds == 5.0

    def test_duration_seconds_fractional(self):
        """Test fractional duration conversion."""
        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.0,
            duration_ms=1500,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        assert result.duration_seconds == 1.5

    def test_error_result(self):
        """Test creating an error result."""
        result = ExecutionResult(
            session_id="",
            output="Timeout after 600s",
            cost_usd=0.0,
            duration_ms=600000,
            num_turns=0,
            is_error=True,
            raw_output="",
        )

        assert result.is_error is True
        assert "Timeout" in result.output

    def test_subagent_results(self):
        """Test subagent_results field."""
        subagent_data = [
            {"agent": "subagent1", "result": "ok"},
            {"agent": "subagent2", "result": "ok"},
        ]

        result = ExecutionResult(
            session_id="test",
            output="output",
            cost_usd=0.0,
            duration_ms=1000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
            subagent_results=subagent_data,
        )

        assert len(result.subagent_results) == 2
        assert result.subagent_results[0]["agent"] == "subagent1"


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
        """Test StreamEvent with source specified."""
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

    def test_different_event_types(self):
        """Test various event types."""
        event_types = ["assistant", "tool_use", "result", "system", "unknown"]

        for event_type in event_types:
            event = StreamEvent(event_type=event_type, data={})
            assert event.event_type == event_type


class TestAgentExecutorInterface:
    """Tests for AgentExecutor interface requirements."""

    def test_class_attributes_defined(self):
        """Test that class attributes are defined in base class."""
        assert hasattr(AgentExecutor, "AGENT_TYPE")
        assert hasattr(AgentExecutor, "CLI_COMMAND")
        assert hasattr(AgentExecutor, "INSTALL_INSTRUCTIONS")

    def test_is_abstract_class(self):
        """Test that AgentExecutor cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AgentExecutor(working_dir=Path("."))

    def test_abstract_methods_defined(self):
        """Test that abstract methods are defined."""
        # Check that the methods exist on the class
        assert hasattr(AgentExecutor, "execute")
        assert hasattr(AgentExecutor, "check_available")
        assert hasattr(AgentExecutor, "_build_command")

    def test_execute_simple_method_exists(self):
        """Test that execute_simple convenience method exists."""
        assert hasattr(AgentExecutor, "execute_simple")


class ConcreteExecutor(AgentExecutor):
    """Concrete implementation for testing."""

    AGENT_TYPE = "test"
    CLI_COMMAND = "test-cli"
    INSTALL_INSTRUCTIONS = "Install test CLI"

    def execute(self, prompt, **kwargs):
        return ExecutionResult(
            session_id="test-session",
            output=f"Executed: {prompt}",
            cost_usd=0.01,
            duration_ms=100,
            num_turns=1,
            is_error=False,
            raw_output="{}",
            agent_type=self.AGENT_TYPE,
        )

    def check_available(self):
        return True, "test-cli v1.0.0"

    def _build_command(self, prompt, **kwargs):
        return [self.CLI_COMMAND, "-p", prompt]


class TestConcreteAgentExecutor:
    """Tests using a concrete implementation."""

    def test_init_with_working_dir(self):
        """Test initialization with working directory."""
        executor = ConcreteExecutor(working_dir=Path("/test/dir"))

        assert executor.working_dir == Path("/test/dir")
        assert executor.default_timeout == 600
        assert executor.model is None
        assert executor.stream is True

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        def callback(event): return None

        executor = ConcreteExecutor(
            working_dir=Path("/test"),
            default_timeout=300,
            model="test-model",
            stream=False,
            stream_callback=callback,
            verbose=False,
            debug="api",
        )

        assert executor.default_timeout == 300
        assert executor.model == "test-model"
        assert executor.stream is False
        assert executor.stream_callback is callback
        assert executor.verbose is False
        assert executor.debug == "api"

    def test_execute_returns_result(self):
        """Test that execute returns ExecutionResult."""
        executor = ConcreteExecutor(working_dir=Path("."))
        result = executor.execute("test prompt")

        assert isinstance(result, ExecutionResult)
        assert "test prompt" in result.output
        assert result.agent_type == "test"

    def test_check_available(self):
        """Test check_available method."""
        executor = ConcreteExecutor(working_dir=Path("."))
        available, version = executor.check_available()

        assert available is True
        assert "v1.0.0" in version

    def test_build_command(self):
        """Test _build_command method."""
        executor = ConcreteExecutor(working_dir=Path("."))
        cmd = executor._build_command("test prompt")

        assert cmd == ["test-cli", "-p", "test prompt"]

    def test_execute_simple(self):
        """Test execute_simple convenience method."""
        executor = ConcreteExecutor(working_dir=Path("."))
        output = executor.execute_simple("simple test")

        assert "simple test" in output

    def test_class_attributes(self):
        """Test class attribute values."""
        assert ConcreteExecutor.AGENT_TYPE == "test"
        assert ConcreteExecutor.CLI_COMMAND == "test-cli"
        assert "Install" in ConcreteExecutor.INSTALL_INSTRUCTIONS
