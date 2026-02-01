"""Tests for CodexExecutor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.errors import AgentExecutionError
from selfassembler.executors.base import ExecutionResult
from selfassembler.executors.codex import CodexExecutor, MockCodexExecutor


class TestCodexExecutorAttributes:
    """Tests for CodexExecutor class attributes."""

    def test_agent_type(self):
        """Test AGENT_TYPE is codex."""
        assert CodexExecutor.AGENT_TYPE == "codex"

    def test_cli_command(self):
        """Test CLI_COMMAND is codex."""
        assert CodexExecutor.CLI_COMMAND == "codex"

    def test_install_instructions(self):
        """Test INSTALL_INSTRUCTIONS is set."""
        assert "github.com/openai/codex" in CodexExecutor.INSTALL_INSTRUCTIONS

    def test_permission_mode_map(self):
        """Test permission mode mapping is defined."""
        assert "plan" in CodexExecutor.PERMISSION_MODE_MAP
        assert "acceptEdits" in CodexExecutor.PERMISSION_MODE_MAP
        assert "default" in CodexExecutor.PERMISSION_MODE_MAP


class TestCodexExecutorInit:
    """Tests for CodexExecutor initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        executor = CodexExecutor(working_dir=Path("/test"))

        assert executor.working_dir == Path("/test")
        assert executor.default_timeout == 600
        assert executor.model is None
        assert executor.stream is True
        assert executor.verbose is True
        assert executor.debug is None

    def test_custom_init(self):
        """Test initialization with custom values."""
        callback = MagicMock()

        executor = CodexExecutor(
            working_dir=Path("/custom"),
            default_timeout=300,
            model="gpt-4",
            stream=False,
            stream_callback=callback,
            verbose=False,
            debug="api",
        )

        assert executor.default_timeout == 300
        assert executor.model == "gpt-4"
        assert executor.stream is False
        assert executor.stream_callback is callback
        assert executor.verbose is False
        assert executor.debug == "api"


class TestCodexExecutorPermissionModeMapping:
    """Tests for permission mode mapping.

    Returns tuple of (sandbox_mode, use_full_auto, use_dangerous_flag).
    codex exec only supports: -s (sandbox), --full-auto, and --dangerously-bypass-approvals-and-sandbox
    """

    @pytest.fixture
    def executor(self) -> CodexExecutor:
        """Create a CodexExecutor for testing."""
        return CodexExecutor(working_dir=Path("."))

    def test_plan_maps_to_read_only(self, executor: CodexExecutor):
        """Test 'plan' mode maps to read-only sandbox."""
        sandbox, full_auto, dangerous = executor._map_permission_mode("plan", False)
        assert sandbox == "read-only"
        assert full_auto is False
        assert dangerous is False

    def test_accept_edits_maps_to_full_auto(self, executor: CodexExecutor):
        """Test 'acceptEdits' mode uses --full-auto flag."""
        sandbox, full_auto, dangerous = executor._map_permission_mode("acceptEdits", False)
        assert sandbox is None  # full-auto implies workspace-write
        assert full_auto is True
        assert dangerous is False

    def test_dangerous_mode_uses_bypass_flag(self, executor: CodexExecutor):
        """Test dangerous mode returns use_dangerous_flag=True."""
        sandbox, full_auto, dangerous = executor._map_permission_mode("plan", True)
        assert sandbox is None
        assert full_auto is False
        assert dangerous is True

    def test_dangerous_mode_overrides_permission_mode(self, executor: CodexExecutor):
        """Test dangerous mode overrides any permission mode."""
        sandbox, full_auto, dangerous = executor._map_permission_mode("acceptEdits", True)
        assert dangerous is True

        sandbox, full_auto, dangerous = executor._map_permission_mode(None, True)
        assert dangerous is True

    def test_none_permission_uses_default(self, executor: CodexExecutor):
        """Test None permission mode uses default (read-only)."""
        sandbox, full_auto, dangerous = executor._map_permission_mode(None, False)
        assert sandbox == "read-only"
        assert full_auto is False
        assert dangerous is False

    def test_unknown_permission_uses_default(self, executor: CodexExecutor):
        """Test unknown permission mode uses default."""
        sandbox, full_auto, dangerous = executor._map_permission_mode("unknown_mode", False)
        assert sandbox == "read-only"
        assert full_auto is False
        assert dangerous is False


class TestCodexExecutorBuildCommand:
    """Tests for _build_command method.

    Codex CLI uses `codex exec` for headless operation with:
    - -a, --ask-for-approval: untrusted|on-failure|on-request|never
    - -s, --sandbox: read-only|workspace-write|danger-full-access
    - -m, --model: Model to use
    - -C, --cd: Working directory
    - --json: JSONL output
    """

    @pytest.fixture
    def executor(self) -> CodexExecutor:
        """Create a CodexExecutor for testing."""
        return CodexExecutor(working_dir=Path("."))

    def test_basic_command_uses_exec_subcommand(self, executor: CodexExecutor):
        """Test basic command uses 'codex exec' for headless mode."""
        cmd = executor._build_command(
            prompt="test prompt",
            streaming=False,
        )

        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "test prompt" in cmd
        assert "--json" in cmd

    def test_sandbox_flag_for_plan_mode(self, executor: CodexExecutor):
        """Test -s sandbox flag is included for plan mode."""
        cmd = executor._build_command(
            prompt="test",
            permission_mode="plan",
            streaming=False,
        )

        assert "-s" in cmd
        idx = cmd.index("-s")
        assert cmd[idx + 1] == "read-only"

    def test_full_auto_flag_for_accept_edits(self, executor: CodexExecutor):
        """Test --full-auto flag is used for acceptEdits mode."""
        cmd = executor._build_command(
            prompt="test",
            permission_mode="acceptEdits",
            streaming=False,
        )

        assert "--full-auto" in cmd
        assert "-s" not in cmd  # full-auto replaces sandbox flag

    def test_dangerous_mode_uses_bypass_flag(self, executor: CodexExecutor):
        """Test dangerous mode uses --dangerously-bypass-approvals-and-sandbox."""
        cmd = executor._build_command(
            prompt="test",
            dangerous_mode=True,
            streaming=False,
        )

        assert "--dangerously-bypass-approvals-and-sandbox" in cmd
        # Should not have -a or -s flags when using dangerous bypass
        assert "-a" not in cmd
        assert "-s" not in cmd

    def test_model_option(self):
        """Test model option uses -m flag."""
        executor = CodexExecutor(working_dir=Path("."), model="gpt-4")
        cmd = executor._build_command(prompt="test", streaming=False)

        assert "-m" in cmd
        idx = cmd.index("-m")
        assert cmd[idx + 1] == "gpt-4"

    def test_working_dir_uses_c_flag(self, executor: CodexExecutor):
        """Test working directory uses -C flag."""
        cmd = executor._build_command(
            prompt="test",
            streaming=False,
            working_dir=Path("/my/project"),
        )

        assert "-C" in cmd
        idx = cmd.index("-C")
        assert cmd[idx + 1] == "/my/project"

    def test_json_always_included(self, executor: CodexExecutor):
        """Test --json is always included for machine-readable output."""
        cmd = executor._build_command(prompt="test", streaming=True)
        assert "--json" in cmd

        cmd = executor._build_command(prompt="test", streaming=False)
        assert "--json" in cmd

    def test_resume_session_uses_exec_resume(self, executor: CodexExecutor):
        """Test resume_session uses 'codex exec resume <id>'."""
        cmd = executor._build_command(
            prompt="test",
            resume_session="session-123",
            streaming=False,
        )

        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert cmd[2] == "resume"
        assert cmd[3] == "session-123"

    def test_allowed_tools_ignored(self, executor: CodexExecutor):
        """Test that allowed_tools doesn't cause errors (not supported)."""
        cmd = executor._build_command(
            prompt="test",
            allowed_tools=["Read", "Write"],
            streaming=False,
        )

        # Should not include --allowedTools since Codex doesn't support it
        assert "--allowedTools" not in cmd


class TestCodexExecutorCheckAvailable:
    """Tests for check_available method."""

    @patch("subprocess.run")
    def test_available_success(self, mock_run):
        """Test check when CLI is available."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="codex 0.1.0",
        )

        executor = CodexExecutor(working_dir=Path("."))
        available, version = executor.check_available()

        assert available is True
        assert "0.1.0" in version

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["codex", "--version"]

    @patch("subprocess.run")
    def test_available_failure(self, mock_run):
        """Test check when CLI returns error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="command not found",
        )

        executor = CodexExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "command not found" in error

    @patch("subprocess.run")
    def test_not_found(self, mock_run):
        """Test check when CLI not installed."""
        mock_run.side_effect = FileNotFoundError()

        executor = CodexExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "not found" in error.lower()

    @patch("subprocess.run")
    def test_exception_handling(self, mock_run):
        """Test exception handling."""
        mock_run.side_effect = Exception("unexpected error")

        executor = CodexExecutor(working_dir=Path("."))
        available, error = executor.check_available()

        assert available is False
        assert "unexpected error" in error


class TestCodexExecutorParseResult:
    """Tests for _parse_result method."""

    @pytest.fixture
    def executor(self) -> CodexExecutor:
        """Create a CodexExecutor for testing."""
        return CodexExecutor(working_dir=Path("."))

    def test_parse_valid_json(self, executor: CodexExecutor):
        """Test parsing valid JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{
            "session_id": "abc123",
            "result": "Success",
            "duration_ms": 1500,
            "num_turns": 3
        }"""

        result = executor._parse_result(mock_result, 1500)

        assert result.session_id == "abc123"
        assert result.output == "Success"
        assert result.duration_ms == 1500
        assert result.num_turns == 3
        assert result.is_error is False
        assert result.agent_type == "codex"
        # Codex doesn't report cost
        assert result.cost_usd == 0.0

    def test_parse_plain_text(self, executor: CodexExecutor):
        """Test parsing plain text output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Plain text output from codex"

        result = executor._parse_result(mock_result, 1000)

        assert result.output == "Plain text output from codex"
        assert result.is_error is False
        assert result.agent_type == "codex"

    def test_parse_error_returncode(self, executor: CodexExecutor):
        """Test parsing with non-zero return code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = '{"result": "Failed", "is_error": false}'

        result = executor._parse_result(mock_result, 1000)

        assert result.is_error is True

    def test_parse_output_field(self, executor: CodexExecutor):
        """Test parsing with 'output' field instead of 'result'."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"output": "Output value"}'

        result = executor._parse_result(mock_result, 1000)

        assert result.output == "Output value"

    def test_parse_jsonl_with_result_event(self, executor: CodexExecutor):
        """Test parsing JSONL output with a result event."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{"type": "assistant", "content": "Working on it..."}
{"type": "tool_use", "name": "Read", "file": "test.py"}
{"type": "result", "result": "Task completed successfully", "session_id": "sess-123", "num_turns": 3}"""

        result = executor._parse_result(mock_result, 2000)

        assert result.session_id == "sess-123"
        assert result.output == "Task completed successfully"
        assert result.num_turns == 3
        assert result.is_error is False
        assert result.agent_type == "codex"

    def test_parse_jsonl_prefers_last_result_event(self, executor: CodexExecutor):
        """Test that JSONL parsing prefers the last result event."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{"type": "result", "result": "First result"}
{"type": "assistant", "content": "More work"}
{"type": "result", "result": "Final result", "num_turns": 5}"""

        result = executor._parse_result(mock_result, 1500)

        # Should use the last result event
        assert result.output == "Final result"
        assert result.num_turns == 5

    def test_parse_jsonl_without_result_event(self, executor: CodexExecutor):
        """Test parsing JSONL output without explicit result event."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{"type": "assistant", "content": "Hello"}
{"type": "assistant", "text": "World"}
{"type": "tool_result", "output": "Done"}"""

        result = executor._parse_result(mock_result, 1000)

        # Should extract content from events
        assert "Hello" in result.output
        assert "World" in result.output
        assert "Done" in result.output
        assert result.num_turns == 3

    def test_parse_mixed_json_and_text(self, executor: CodexExecutor):
        """Test parsing mixed JSON and plain text output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """Some debug output
{"type": "result", "result": "Success"}
More text"""

        result = executor._parse_result(mock_result, 1000)

        # Should still find the JSON result event
        assert result.output == "Success"

    def test_parse_jsonl_with_error_returncode(self, executor: CodexExecutor):
        """Test JSONL parsing with non-zero return code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = """{"type": "result", "result": "Partial work", "is_error": false}"""

        result = executor._parse_result(mock_result, 1000)

        # is_error should be True because returncode != 0
        assert result.is_error is True
        assert result.output == "Partial work"

    def test_parse_empty_jsonl_events(self, executor: CodexExecutor):
        """Test parsing when events have no useful content."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{"type": "start"}
{"type": "end"}"""

        result = executor._parse_result(mock_result, 1000)

        # Should fall back to raw output since no content fields found
        assert result.num_turns == 2
        # Output may be empty or contain the raw JSON

    def test_parse_jsonl_duration_from_result_event(self, executor: CodexExecutor):
        """Test that duration_ms is extracted from result event."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """{"type": "result", "result": "Done", "duration_ms": 5000}"""

        result = executor._parse_result(mock_result, 1000)  # Default would be 1000

        assert result.duration_ms == 5000


class TestCodexExecutorParseStreamEvent:
    """Tests for _parse_stream_event method."""

    @pytest.fixture
    def executor(self) -> CodexExecutor:
        """Create a CodexExecutor for testing."""
        return CodexExecutor(working_dir=Path("."))

    def test_valid_json_event(self, executor: CodexExecutor):
        """Test parsing valid JSON event."""
        line = '{"type": "assistant", "content": "Hello"}'
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "assistant"
        assert event.data["content"] == "Hello"
        assert event.source == "codex"

    def test_plain_text_event(self, executor: CodexExecutor):
        """Test parsing plain text creates text event."""
        line = "Plain text output"
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "text"
        assert event.data["content"] == "Plain text output"
        assert event.source == "codex"

    def test_empty_line(self, executor: CodexExecutor):
        """Test parsing empty line returns None."""
        event = executor._parse_stream_event("   ")
        assert event is None

    def test_event_with_whitespace(self, executor: CodexExecutor):
        """Test parsing event with whitespace."""
        line = '  {"type": "tool_use", "name": "Read"}  \n'
        event = executor._parse_stream_event(line)

        assert event is not None
        assert event.event_type == "tool_use"


class TestCodexExecutorExecute:
    """Tests for execute method."""

    @patch("subprocess.run")
    def test_execute_non_streaming(self, mock_run):
        """Test non-streaming execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="done",
        )

        executor = CodexExecutor(working_dir=Path("/test"), stream=False)
        result = executor.execute("test prompt")

        assert result.output == "done"
        assert result.agent_type == "codex"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Test execution timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["codex"], timeout=600)

        executor = CodexExecutor(working_dir=Path("."), stream=False)
        result = executor.execute("test", timeout=600)

        assert result.is_error is True
        assert "Timeout" in result.output
        assert result.agent_type == "codex"

    @patch("subprocess.run")
    def test_execute_file_not_found(self, mock_run):
        """Test execution when CLI not found."""
        mock_run.side_effect = FileNotFoundError()

        executor = CodexExecutor(working_dir=Path("."), stream=False)

        with pytest.raises(AgentExecutionError) as exc_info:
            executor.execute("test")

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.agent_type == "codex"

    @patch("subprocess.run")
    def test_execute_with_options(self, mock_run):
        """Test execution with various options."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ok",
        )

        executor = CodexExecutor(working_dir=Path("."), stream=False)
        executor.execute(
            prompt="test",
            permission_mode="plan",
            max_turns=10,
            timeout=300,
            dangerous_mode=False,
            working_dir=Path("/override"),
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0]  # First positional arg is the command list
        # Working dir is passed via -C flag, not cwd
        assert "-C" in cmd
        idx = cmd.index("-C")
        assert cmd[idx + 1] == "/override"
        assert call_args.kwargs["timeout"] == 300


class TestMockCodexExecutor:
    """Tests for MockCodexExecutor."""

    def test_default_response(self):
        """Test default mock response."""
        executor = MockCodexExecutor()
        result = executor.execute("test prompt")

        assert result.session_id == ""  # Codex doesn't provide session IDs
        assert not result.is_error
        assert result.cost_usd == 0.0  # Codex doesn't report cost
        assert result.agent_type == "codex"
        assert "Mock Codex" in result.output

    def test_custom_response(self):
        """Test custom mock response."""
        custom_result = ExecutionResult(
            session_id="",
            output="Custom Codex output",
            cost_usd=0.0,
            duration_ms=2000,
            num_turns=5,
            is_error=False,
            raw_output="{}",
            agent_type="codex",
        )

        executor = MockCodexExecutor(responses={"keyword": custom_result})
        result = executor.execute("prompt with keyword in it")

        assert result.output == "Custom Codex output"
        assert result.num_turns == 5

    def test_call_history(self):
        """Test that calls are recorded."""
        executor = MockCodexExecutor()

        executor.execute("prompt 1", permission_mode="plan")
        executor.execute("prompt 2", dangerous_mode=True)

        assert len(executor.call_history) == 2
        assert executor.call_history[0]["prompt"] == "prompt 1"
        assert executor.call_history[0]["permission_mode"] == "plan"
        assert executor.call_history[1]["dangerous_mode"] is True

    def test_default_when_no_match(self):
        """Test default response when no keyword matches."""
        custom = ExecutionResult(
            session_id="",
            output="custom",
            cost_usd=0.0,
            duration_ms=100,
            num_turns=1,
            is_error=False,
            raw_output="{}",
        )

        executor = MockCodexExecutor(responses={"nomatch": custom})
        result = executor.execute("different prompt")

        assert "Mock Codex" in result.output


class TestCodexVsClaudeComparison:
    """Tests comparing Codex and Claude executor behavior."""

    def test_different_agent_types(self):
        """Test that agent types are different."""
        from selfassembler.executors.claude import ClaudeExecutor

        assert CodexExecutor.AGENT_TYPE != ClaudeExecutor.AGENT_TYPE
        assert CodexExecutor.AGENT_TYPE == "codex"
        assert ClaudeExecutor.AGENT_TYPE == "claude"

    def test_different_cli_commands(self):
        """Test that CLI commands are different."""
        from selfassembler.executors.claude import ClaudeExecutor

        assert CodexExecutor.CLI_COMMAND != ClaudeExecutor.CLI_COMMAND
        assert CodexExecutor.CLI_COMMAND == "codex"
        assert ClaudeExecutor.CLI_COMMAND == "claude"

    def test_both_inherit_from_agent_executor(self):
        """Test both inherit from AgentExecutor."""
        from selfassembler.executors.base import AgentExecutor
        from selfassembler.executors.claude import ClaudeExecutor

        assert issubclass(CodexExecutor, AgentExecutor)
        assert issubclass(ClaudeExecutor, AgentExecutor)

    def test_result_includes_agent_type(self):
        """Test that results include correct agent type."""
        claude_executor = MockCodexExecutor()
        result = claude_executor.execute("test")
        assert result.agent_type == "codex"
