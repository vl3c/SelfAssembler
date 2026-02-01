"""Claude Code CLI executor implementation."""

from __future__ import annotations

import contextlib
import json
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from selfassembler.errors import AgentExecutionError
from selfassembler.executors.base import AgentExecutor, ExecutionResult, StreamEvent


class ClaudeExecutor(AgentExecutor):
    """
    Wrapper for the Claude Code CLI.

    Handles command construction, execution, and output parsing.
    """

    AGENT_TYPE = "claude"
    CLI_COMMAND = "claude"
    INSTALL_INSTRUCTIONS = "Install with: npm install -g @anthropic-ai/claude-code"

    def __init__(
        self,
        working_dir: Path,
        default_timeout: int = 600,
        model: str | None = None,
        stream: bool = True,
        stream_callback: Callable[[StreamEvent], None] | None = None,
        verbose: bool = True,
        debug: str | None = None,
    ):
        super().__init__(
            working_dir=working_dir,
            default_timeout=default_timeout,
            model=model,
            stream=stream,
            stream_callback=stream_callback,
            verbose=verbose,
            debug=debug,
        )

    def execute(
        self,
        prompt: str,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 50,
        timeout: int | None = None,
        resume_session: str | None = None,
        dangerous_mode: bool = False,
        working_dir: Path | None = None,
        stream: bool | None = None,
    ) -> ExecutionResult:
        """
        Execute a prompt with Claude CLI.

        Args:
            prompt: The prompt to send to Claude
            permission_mode: Permission mode ("plan", "acceptEdits", etc.)
            allowed_tools: List of allowed tools (e.g., ["Read", "Grep", "Edit"])
            max_turns: Maximum number of agentic turns
            timeout: Timeout in seconds (uses default if not specified)
            resume_session: Session ID to resume
            dangerous_mode: Use --dangerously-skip-permissions
            working_dir: Override working directory
            stream: Override streaming mode (uses instance default if None)

        Returns:
            ExecutionResult with parsed output

        Raises:
            AgentExecutionError: If execution fails
        """
        use_stream = stream if stream is not None else self.stream
        effective_timeout = timeout or self.default_timeout
        effective_working_dir = working_dir or self.working_dir

        if use_stream:
            return self._execute_streaming(
                prompt=prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=max_turns,
                timeout=effective_timeout,
                resume_session=resume_session,
                dangerous_mode=dangerous_mode,
                working_dir=effective_working_dir,
            )

        cmd = self._build_command(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            resume_session=resume_session,
            dangerous_mode=dangerous_mode,
            streaming=False,
        )

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=effective_working_dir,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            return self._parse_result(result, elapsed_ms)

        except subprocess.TimeoutExpired as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                session_id="",
                output=f"Timeout after {effective_timeout}s",
                cost_usd=0.0,
                duration_ms=elapsed_ms,
                num_turns=0,
                is_error=True,
                raw_output=str(e.stdout or ""),
                agent_type=self.AGENT_TYPE,
            )

        except FileNotFoundError:
            raise AgentExecutionError(
                f"{self.CLI_COMMAND} CLI not found. {self.INSTALL_INSTRUCTIONS}",
                agent_type=self.AGENT_TYPE,
            ) from None

        except Exception as e:
            raise AgentExecutionError(
                f"Execution failed: {e}",
                agent_type=self.AGENT_TYPE,
            ) from e

    def _build_command(
        self,
        prompt: str,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 50,
        resume_session: str | None = None,
        dangerous_mode: bool = False,
        streaming: bool = True,
    ) -> list[str]:
        """Build the claude CLI command."""
        cmd = [self.CLI_COMMAND, "-p", prompt]

        if resume_session:
            cmd.extend(["--resume", resume_session])

        if dangerous_mode:
            cmd.append("--dangerously-skip-permissions")
        elif permission_mode:
            cmd.extend(["--permission-mode", permission_mode])

        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        if self.model:
            cmd.extend(["--model", self.model])

        # Output format: stream-json for streaming, json for non-streaming
        if streaming:
            cmd.extend(["--output-format", "stream-json"])
            if self.verbose:
                cmd.append("--verbose")
            if self.debug:
                cmd.extend(["--debug", self.debug])
        else:
            cmd.extend(["--output-format", "json"])

        cmd.extend(["--max-turns", str(max_turns)])

        return cmd

    def _execute_streaming(
        self,
        prompt: str,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 50,
        timeout: int = 600,
        resume_session: str | None = None,
        dangerous_mode: bool = False,
        working_dir: Path | None = None,
    ) -> ExecutionResult:
        """Execute with streaming output."""
        cmd = self._build_command(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            resume_session=resume_session,
            dangerous_mode=dangerous_mode,
            streaming=True,
        )

        effective_working_dir = working_dir or self.working_dir
        start_time = time.time()

        # Collect all events and the final result
        all_events: list[StreamEvent] = []
        final_result_data: dict[str, Any] | None = None
        stderr_lines: list[str] = []
        stderr_thread: threading.Thread | None = None

        def _drain_stderr(stream: Any) -> None:
            if not stream:
                return
            for line in stream:
                stderr_lines.append(line)

        try:
            process = subprocess.Popen(
                cmd,
                cwd=effective_working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            if process.stderr:
                stderr_thread = threading.Thread(
                    target=_drain_stderr,
                    args=(process.stderr,),
                    daemon=True,
                )
                stderr_thread.start()

            # Read stdout line by line
            if process.stdout:
                for line in process.stdout:
                    if not line.strip():
                        continue

                    event = self._parse_stream_event(line)
                    if event:
                        all_events.append(event)

                        # Call the stream callback if provided
                        if self.stream_callback:
                            with contextlib.suppress(Exception):
                                self.stream_callback(event)

                        # Capture the final result event
                        if event.event_type == "result":
                            final_result_data = event.data

            # Wait for process to complete with timeout
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout > 0:
                process.wait(timeout=remaining_timeout)
            else:
                process.kill()
                process.wait()

            elapsed_ms = int((time.time() - start_time) * 1000)
            if stderr_thread:
                stderr_thread.join(timeout=1)

            # Parse result from final event or fallback
            if final_result_data:
                return ExecutionResult(
                    session_id=final_result_data.get("session_id", ""),
                    output=final_result_data.get("result", ""),
                    cost_usd=self._parse_cost(final_result_data),
                    duration_ms=final_result_data.get("duration_ms", elapsed_ms),
                    num_turns=final_result_data.get("num_turns", 0),
                    is_error=final_result_data.get("is_error", False) or process.returncode != 0,
                    raw_output=json.dumps(final_result_data),
                    subagent_results=final_result_data.get("subagent_results", []),
                    agent_type=self.AGENT_TYPE,
                )

            # No result event found, construct from events
            return ExecutionResult(
                session_id="",
                output="Streaming completed without result event",
                cost_usd=0.0,
                duration_ms=elapsed_ms,
                num_turns=len([e for e in all_events if e.event_type == "assistant"]),
                is_error=process.returncode != 0,
                raw_output="",
                agent_type=self.AGENT_TYPE,
            )

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            elapsed_ms = int((time.time() - start_time) * 1000)
            if stderr_thread:
                stderr_thread.join(timeout=1)
            return ExecutionResult(
                session_id="",
                output=f"Timeout after {timeout}s",
                cost_usd=0.0,
                duration_ms=elapsed_ms,
                num_turns=0,
                is_error=True,
                raw_output="",
                agent_type=self.AGENT_TYPE,
            )

        except FileNotFoundError:
            raise AgentExecutionError(
                f"{self.CLI_COMMAND} CLI not found. {self.INSTALL_INSTRUCTIONS}",
                agent_type=self.AGENT_TYPE,
            ) from None

        except Exception as e:
            raise AgentExecutionError(
                f"Streaming execution failed: {e}",
                agent_type=self.AGENT_TYPE,
            ) from e

    def _parse_stream_event(self, line: str) -> StreamEvent | None:
        """Parse a line of stream-json output into a StreamEvent."""
        try:
            data = json.loads(line.strip())
            return StreamEvent(
                event_type=data.get("type", "unknown"),
                data=data,
                source=self.AGENT_TYPE,
            )
        except json.JSONDecodeError:
            return None

    def _parse_result(
        self, result: subprocess.CompletedProcess, elapsed_ms: int
    ) -> ExecutionResult:
        """Parse the JSON output from Claude CLI."""
        raw_output = result.stdout

        # Try to parse as JSON
        try:
            data = json.loads(raw_output)
            return ExecutionResult(
                session_id=data.get("session_id", ""),
                output=data.get("result", ""),
                cost_usd=self._parse_cost(data),
                duration_ms=data.get("duration_ms", elapsed_ms),
                num_turns=data.get("num_turns", 0),
                is_error=data.get("is_error", False) or result.returncode != 0,
                raw_output=raw_output,
                subagent_results=data.get("subagent_results", []),
                agent_type=self.AGENT_TYPE,
            )
        except json.JSONDecodeError:
            # If JSON parsing fails, treat as plain text output
            return ExecutionResult(
                session_id="",
                output=raw_output,
                cost_usd=0.0,
                duration_ms=elapsed_ms,
                num_turns=0,
                is_error=result.returncode != 0,
                raw_output=raw_output,
                agent_type=self.AGENT_TYPE,
            )

    def _parse_cost(self, data: dict[str, Any]) -> float:
        """Parse cost from response data."""
        # Handle different cost formats
        if "cost_usd" in data:
            return float(data["cost_usd"])
        if "cost" in data:
            cost = data["cost"]
            if isinstance(cost, dict):
                return float(cost.get("total_usd", 0.0))
            return float(cost)
        return 0.0

    def check_available(self) -> tuple[bool, str]:
        """Check if Claude CLI is available."""
        try:
            result = subprocess.run(
                [self.CLI_COMMAND, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr
        except FileNotFoundError:
            return False, f"{self.CLI_COMMAND} CLI not found"
        except Exception as e:
            return False, str(e)


class MockClaudeExecutor(ClaudeExecutor):
    """Mock executor for testing."""

    def __init__(self, responses: dict[str, ExecutionResult] | None = None):
        super().__init__(working_dir=Path("."), stream=False)
        self.responses = responses or {}
        self.call_history: list[dict[str, Any]] = []

    def execute(
        self,
        prompt: str,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int = 50,
        timeout: int | None = None,
        resume_session: str | None = None,
        dangerous_mode: bool = False,
        working_dir: Path | None = None,
        stream: bool | None = None,
    ) -> ExecutionResult:
        """Record the call and return a mock response."""
        self.call_history.append(
            {
                "prompt": prompt,
                "permission_mode": permission_mode,
                "allowed_tools": allowed_tools,
                "max_turns": max_turns,
                "timeout": timeout,
                "resume_session": resume_session,
                "dangerous_mode": dangerous_mode,
            }
        )

        # Check for matching response
        for key, response in self.responses.items():
            if key in prompt:
                return response

        # Default success response
        return ExecutionResult(
            session_id="mock-session-123",
            output="Mock execution completed successfully",
            cost_usd=0.01,
            duration_ms=1000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
            agent_type=self.AGENT_TYPE,
        )
