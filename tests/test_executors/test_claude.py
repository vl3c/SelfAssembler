"""Tests for ClaudeExecutor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.errors import AgentExecutionError
from selfassembler.executors.base import ExecutionResult
from selfassembler.executors.claude import ClaudeExecutor, MockClaudeExecutor


class TestClaudeExecutorAttributes:
    """Tests for ClaudeExecutor class attributes."""

    def test_agent_type(self):
        """Test AGENT_TYPE is claude."""
        assert ClaudeExecutor.AGENT_TYPE == "claude"

    def test_cli_command(self):
        """Test CLI_COMMAND is claude."""
        assert ClaudeExecutor.CLI_COMMAND == "claude"

    def test_install_instructions(self):
        """Test INSTALL_INSTRUCTIONS is set."""
        assert "npm install" in ClaudeExecutor.INSTALL_INSTRUCTIONS
        assert "@anthropic-ai/claude-code" in ClaudeExecutor.INSTALL_INSTRUCTIONS


class TestClaudeExecutorInit:
    """Tests for ClaudeExecutor initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        executor = ClaudeExecutor(working_dir=Path("/test"))

        assert executor.working_dir == Path("/test")
        assert executor.default_timeout == 600
        assert executor.model is None
        assert executor.stream is True
        assert executor.verbose is True
        assert executor.debug is None

    def test_custom_init(self):
        """Test initialization with custom values."""
        callback = MagicMock()

        executor = ClaudeExecutor(
            working_dir=Path("/custom"),
            default_timeout=300,
            model="opus",
            stream=False,
            stream_callback=callback,
            verbose=False,
            debug="api,mcp",
        )

        assert executor.default_timeout == 300
        assert executor.model == "opus"
        assert executor.stream is False
        assert executor.stream_callback is callback
        assert executor.verbose is False
        assert executor.debug == "api,mcp"


class TestClaudeExecutorBuildCommand:
    """Tests for _build_command method."""

    @pytest.fixture
    def executor(self) -> ClaudeExecutor:
        """Create a ClaudeExecutor for testing."""
        return ClaudeExecutor(working_dir=Path("."))

    def test_basic_command(self, executor: ClaudeExecutor):
        """Test basic command building."""
        cmd = executor._build_command(
            prompt="test prompt",
            streaming=False,
        )

        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_streaming_command(self, executor: ClaudeExecutor):
        """Test streaming command building."""
        cmd = executor._build_command(
            prompt="test",
            streaming=True,
        )

        assert "stream-json" in cmd
        assert "--verbose" in cmd

    def test_permission_mode(self, executor: ClaudeExecutor):
        """Test permission mode argument."""
        cmd = executor._build_command(
            prompt="test",
            permission_mode="plan",
            streaming=False,
        )

        assert "--permission-mode" in cmd
        assert "plan" in cmd

    def test_dangerous_mode_overrides_permission(self, executor: ClaudeExecutor):
        """Test dangerous mode overrides permission mode."""
        cmd = executor._build_command(
            prompt="test",
            permission_mode="plan",
            dangerous_mode=True,
            streaming=False,
        )

        assert "--dangerously-skip-permissions" in cmd
        assert "--permission-mode" not in cmd

    def test_allowed_tools(self, executor: ClaudeExecutor):
        """Test allowed tools argument."""
        cmd = executor._build_command(
            prompt="test",
            allowed_tools=["Read", "Write", "Edit"],
            streaming=False,
        )

        assert "--allowedTools" in cmd
        assert "Read,Write,Edit" in cmd

    def test_resume_session(self, executor: ClaudeExecutor):
        """Test resume session argument."""
        cmd = executor._build_command(
            prompt="test",
            resume_session="session-123",
            streaming=False,
        )

        assert "--resume" in cmd
        assert "session-123" in cmd

    def test_max_turns(self, executor: ClaudeExecutor):
        """Test max turns argument."""
        cmd = executor._build_command(
            prompt="test",
            max_turns=100,
            streaming=False,
        )

        assert "--max-turns" in cmd
        assert "100" in cmd

    def test_model_option(self):
        """Test model option is included."""
        executor = ClaudeExecutor(working_dir=Path("."), model="opus")
        cmd = executor._build_command(prompt="test", streaming=False)

        assert "--model" in cmd
        assert "opus" in cmd

    def test_debug_option(self):
        """Test debug option is included in streaming."""
        executor = ClaudeExecutor(working_dir=Path("."), debug="api")
        cmd = executor._build_command(prompt="test", streaming=True)

        assert "--debug" in cmd
        assert "api" in cmd


class TestClaudeExecutorCheckAvailable:
    """Tests for check_available method."""

    @patch("subprocess.run")
    def test_available_success(self, mock_run):
        """Test check when CLI is available."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="claude v1.0.56",
        )

        executor = ClaudeExecutor(working_dir=Path("."))
        available, version = executor.check_available()

        assert available is True
        assert "v1.0.56" in version

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["claude", "--version"]

    @patch("subprocess.run")
    def test_available_failure(self, mock_run):
        """Test check when CLI returns error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="command not found",
        )

        executor = ClaudeExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "command not found" in error

    @patch("subprocess.run")
    def test_not_found(self, mock_run):
        """Test check when CLI not installed."""
        mock_run.side_effect = FileNotFoundError()

        executor = ClaudeExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "not found" in error.lower()

    @patch("subprocess.run")
    def test_exception_handling(self, mock_run):
        """Test exception handling."""
        mock_run.side_effect = Exception("unexpected error")

        executor = ClaudeExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "unexpected error" in error


class TestClaudeExecutorParseResult:
    """Tests for _parse_result method."""

    @pytest.fixture
    def executor(self) -> ClaudeExecutor:
        """Create a ClaudeExecutor for testing."""
        return ClaudeExecutor(working_dir=Path("."))

    def test_parse_valid_json(self, executor: ClaudeExecutor):
        """Test parsing valid JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{
            "session_id": "abc123",
            "result": "Success",
            "cost_usd": 0.05,
            "duration_ms": 1500,
            "num_turns": 3,
            "is_error": false
        }"""

        result = executor._parse_result(mock_result, 1500)

        assert result.session_id == "abc123"
        assert result.output == "Success"
        assert result.cost_usd == 0.05
        assert result.duration_ms == 1500
        assert result.num_turns == 3
        assert result.is_error is False
        assert result.agent_type == "claude"

    def test_parse_invalid_json(self, executor: ClaudeExecutor):
        """Test parsing invalid JSON falls back to plain text."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Plain text output"

        result = executor._parse_result(mock_result, 1000)

        assert result.output == "Plain text output"
        assert result.is_error is False
        assert result.agent_type == "claude"

    def test_parse_error_returncode(self, executor: ClaudeExecutor):
        """Test parsing with non-zero return code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = '{"result": "Failed", "is_error": false}'

        result = executor._parse_result(mock_result, 1000)

        assert result.is_error is True

    def test_parse_cost_dict(self, executor: ClaudeExecutor):
        """Test parsing cost as dictionary."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{
            "result": "ok",
            "cost": {"total_usd": 0.10}
        }"""

        result = executor._parse_result(mock_result, 1000)

        assert result.cost_usd == 0.10

    def test_parse_subagent_results(self, executor: ClaudeExecutor):
        """Test parsing subagent results."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{
            "result": "ok",
            "subagent_results": [{"id": "sub1", "output": "done"}]
        }"""

        result = executor._parse_result(mock_result, 1000)

        assert len(result.subagent_results) == 1
        assert result.subagent_results[0]["id"] == "sub1"


class TestClaudeExecutorParseStreamEvent:
    """Tests for _parse_stream_event method."""

    @pytest.fixture
    def executor(self) -> ClaudeExecutor:
        """Create a ClaudeExecutor for testing."""
        return ClaudeExecutor(working_dir=Path("."))

    def test_valid_json_event(self, executor: ClaudeExecutor):
        """Test parsing valid JSON event."""
        line = '{"type": "assistant", "content": "Hello"}'
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "assistant"
        assert event.data["content"] == "Hello"
        assert event.source == "claude"

    def test_invalid_json(self, executor: ClaudeExecutor):
        """Test parsing invalid JSON returns None."""
        line = "not json"
        event = executor._parse_stream_event(line)

        assert event is None

    def test_event_with_whitespace(self, executor: ClaudeExecutor):
        """Test parsing event with whitespace."""
        line = '  {"type": "tool_use", "name": "Read"}  \n'
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "tool_use"

    def test_unknown_type(self, executor: ClaudeExecutor):
        """Test parsing event without type field."""
        line = '{"content": "test"}'
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "unknown"


class TestClaudeExecutorExecute:
    """Tests for execute method."""

    @patch("subprocess.run")
    def test_execute_non_streaming(self, mock_run):
        """Test non-streaming execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"session_id": "test", "result": "done", "cost_usd": 0.01}',
        )

        executor = ClaudeExecutor(working_dir=Path("/test"), stream=False)
        result = executor.execute("test prompt")

        assert result.session_id == "test"
        assert result.output == "done"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Test execution timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["claude"], timeout=600)

        executor = ClaudeExecutor(working_dir=Path("."), stream=False)
        result = executor.execute("test", timeout=600)

        assert result.is_error is True
        assert "Timeout" in result.output

    @patch("subprocess.run")
    def test_execute_file_not_found(self, mock_run):
        """Test execution when CLI not found."""
        mock_run.side_effect = FileNotFoundError()

        executor = ClaudeExecutor(working_dir=Path("."), stream=False)

        with pytest.raises(AgentExecutionError) as exc_info:
            executor.execute("test")

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.agent_type == "claude"

    @patch("subprocess.run")
    def test_execute_with_all_options(self, mock_run):
        """Test execution with all options."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"result": "ok"}',
        )

        executor = ClaudeExecutor(working_dir=Path("."), stream=False)
        executor.execute(
            prompt="test",
            permission_mode="plan",
            allowed_tools=["Read"],
            max_turns=10,
            timeout=300,
            resume_session="prev-session",
            dangerous_mode=False,
            working_dir=Path("/override"),
        )

        call_args = mock_run.call_args
        assert call_args.kwargs["cwd"] == Path("/override")
        assert call_args.kwargs["timeout"] == 300


class TestMockClaudeExecutor:
    """Tests for MockClaudeExecutor."""

    def test_default_response(self):
        """Test default mock response."""
        executor = MockClaudeExecutor()
        result = executor.execute("test prompt")

        assert result.session_id == "mock-session-123"
        assert not result.is_error
        assert result.cost_usd == 0.01
        assert result.agent_type == "claude"

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
            agent_type="claude",
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

    def test_multiple_custom_responses(self):
        """Test matching multiple custom responses."""
        response1 = ExecutionResult(
            session_id="s1",
            output="Response 1",
            cost_usd=0.0,
            duration_ms=100,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )
        response2 = ExecutionResult(
            session_id="s2",
            output="Response 2",
            cost_usd=0.0,
            duration_ms=100,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        executor = MockClaudeExecutor(
            responses={
                "keyword1": response1,
                "keyword2": response2,
            }
        )

        result1 = executor.execute("contains keyword1")
        result2 = executor.execute("contains keyword2")

        assert result1.session_id == "s1"
        assert result2.session_id == "s2"

    def test_default_when_no_match(self):
        """Test default response when no keyword matches."""
        custom = ExecutionResult(
            session_id="custom",
            output="custom",
            cost_usd=0.0,
            duration_ms=100,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        executor = MockClaudeExecutor(responses={"nomatch": custom})
        result = executor.execute("different prompt")

        assert result.session_id == "mock-session-123"
