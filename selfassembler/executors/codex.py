"""OpenAI Codex CLI executor implementation."""

from __future__ import annotations

import contextlib
import functools
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from selfassembler.errors import AgentExecutionError
from selfassembler.executors.base import AgentExecutor, ExecutionResult, StreamEvent


@functools.lru_cache(maxsize=1)
def _check_landlock_available() -> bool:
    """Check if Linux Landlock is available and working on this system.

    Note: Even when /sys/kernel/security/landlock exists, Codex's workspace-write
    sandbox can fail with Landlock errors on some systems. We always return False
    to use danger-full-access, relying on external sandboxing for safety.

    TODO: Implement a runtime test that actually tries workspace-write mode.
    """
    # Always use danger-full-access - Landlock detection is unreliable
    # External sandboxing should be used for safety
    return False


class CodexExecutor(AgentExecutor):
    """
    Wrapper for the OpenAI Codex CLI.

    Handles command construction, execution, and output parsing for the
    OpenAI Codex command-line interface.

    Codex CLI uses `codex exec` for non-interactive/headless execution.
    Key flags:
      -a, --ask-for-approval: untrusted|on-failure|on-request|never
      -s, --sandbox: read-only|workspace-write|danger-full-access
      -m, --model: Model to use
      -C, --cd: Working directory
      --json: Output as JSONL
      --full-auto: Shortcut for -a on-request --sandbox workspace-write
      --dangerously-bypass-approvals-and-sandbox: Skip all prompts (DANGEROUS)
    """

    AGENT_TYPE = "codex"
    CLI_COMMAND = "codex"
    INSTALL_INSTRUCTIONS = "Install from: https://github.com/openai/codex"

    # Mapping from SelfAssembler permission modes to Codex sandbox modes
    # codex exec only supports: -s (sandbox) and --full-auto flags
    # Sandbox values: read-only, workspace-write, danger-full-access
    PERMISSION_MODE_MAP = {
        "plan": "read-only",  # Read-only sandbox
        "acceptEdits": "workspace-write",  # Allow file edits in workspace
        "default": "read-only",  # Safe default
    }

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

    def _map_permission_mode(
        self, permission_mode: str | None, dangerous_mode: bool
    ) -> tuple[str | None, bool, bool]:
        """
        Map SelfAssembler permission modes to Codex CLI flags.

        codex exec supports:
        - -s, --sandbox: read-only | workspace-write | danger-full-access
        - --full-auto: Shortcut for workspace-write with model-driven approval
        - --dangerously-bypass-approvals-and-sandbox: Skip all prompts (DANGEROUS)

        Note: We always use danger-full-access for write operations because Codex's
        Landlock-based workspace-write sandbox is unreliable on many systems.
        External sandboxing should be used for safety in production.

        Args:
            permission_mode: SelfAssembler permission mode
            dangerous_mode: Whether dangerous mode is enabled

        Returns:
            Tuple of (sandbox_mode, use_full_auto, use_dangerous_flag)
            - sandbox_mode: Value for -s flag (or None to omit)
            - use_full_auto: Whether to use --full-auto flag
            - use_dangerous_flag: Whether to use --dangerously-bypass-approvals-and-sandbox
        """
        if dangerous_mode:
            # Use the dangerous bypass flag for full autonomy
            return None, False, True

        if permission_mode is None:
            sandbox = self.PERMISSION_MODE_MAP["default"]
            return sandbox, False, False

        # For acceptEdits, use danger-full-access since Landlock is unreliable
        # External sandboxing should be used for safety
        if permission_mode == "acceptEdits":
            return "danger-full-access", False, False

        sandbox = self.PERMISSION_MODE_MAP.get(
            permission_mode, self.PERMISSION_MODE_MAP["default"]
        )
        return sandbox, False, False

    def _log_error_result(self, result: ExecutionResult, context: str) -> None:
        """Log diagnostic info when an execution result is an error."""
        if result.is_error:
            print(
                f"[codex] {context}: is_error=True, "
                f"output={result.output[:300]!r}, "
                f"raw_output={result.raw_output[:200]!r}, "
                f"duration={result.duration_ms}ms, turns={result.num_turns}",
                file=sys.stderr,
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
        Execute a prompt with Codex CLI.

        Args:
            prompt: The prompt to send to Codex
            permission_mode: Permission mode (mapped to Codex approval modes)
            allowed_tools: List of allowed tools (not directly supported by Codex)
            max_turns: Maximum number of agentic turns
            timeout: Timeout in seconds (uses default if not specified)
            resume_session: Session ID to resume (supported via `codex exec resume`)
            dangerous_mode: Use full-auto approval mode
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
            result = self._execute_streaming(
                prompt=prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=max_turns,
                timeout=effective_timeout,
                resume_session=resume_session,
                dangerous_mode=dangerous_mode,
                working_dir=effective_working_dir,
            ).validate()
            self._log_error_result(result, "execute(streaming)")
            return result

        cmd = self._build_command(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            resume_session=resume_session,
            dangerous_mode=dangerous_mode,
            streaming=False,
            working_dir=effective_working_dir,
        )

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            parsed = self._parse_result(result, elapsed_ms).validate()
            self._log_error_result(parsed, "execute(non-streaming)")
            return parsed

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
        working_dir: Path | None = None,
    ) -> list[str]:
        """Build the codex CLI command for headless execution.

        Uses `codex exec` subcommand for non-interactive operation.

        Args:
            prompt: The prompt/instruction to execute
            permission_mode: SelfAssembler permission mode to map
            allowed_tools: Not used (Codex doesn't support tool filtering)
            max_turns: Not used (Codex manages turns internally)
            resume_session: Session ID to resume via `codex exec resume`
            dangerous_mode: Use --dangerously-bypass-approvals-and-sandbox
            streaming: Not used in command building (handled by --json)
            working_dir: Working directory to use via -C flag
        """
        # Use 'codex exec' for headless/non-interactive mode
        if resume_session:
            # Resume a previous session by ID
            cmd = [self.CLI_COMMAND, "exec", "resume", resume_session]
        else:
            cmd = [self.CLI_COMMAND, "exec", prompt]

        # Map permission mode to Codex flags
        sandbox_mode, use_full_auto, use_dangerous = self._map_permission_mode(
            permission_mode, dangerous_mode
        )

        if use_dangerous:
            # Full bypass - extremely dangerous, only for externally sandboxed envs
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif use_full_auto:
            # Use --full-auto for workspace-write with automatic approval
            cmd.append("--full-auto")
        elif sandbox_mode:
            # Apply sandbox mode
            cmd.extend(["-s", sandbox_mode])

        # Model selection
        if self.model:
            cmd.extend(["-m", self.model])

        # Working directory
        if working_dir:
            cmd.extend(["-C", str(working_dir)])

        # Use JSON output for machine-readable parsing
        cmd.append("--json")

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
        """Execute with streaming output (JSONL)."""
        effective_working_dir = working_dir or self.working_dir

        cmd = self._build_command(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=max_turns,
            resume_session=resume_session,
            dangerous_mode=dangerous_mode,
            streaming=True,
            working_dir=effective_working_dir,
        )

        start_time = time.time()

        # Collect output
        all_events: list[StreamEvent] = []
        stdout_lines: list[str] = []
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
                    stdout_lines.append(line)

                    if not line.strip():
                        continue

                    # Try to parse as JSON event
                    event = self._parse_stream_event(line)
                    if event:
                        all_events.append(event)

                        # Call the stream callback if provided
                        if self.stream_callback:
                            with contextlib.suppress(Exception):
                                self.stream_callback(event)

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

            # Construct result from collected output
            output = "".join(stdout_lines)
            if process.returncode != 0:
                stderr_text = "".join(stderr_lines).strip()
                print(
                    f"[codex] _execute_streaming: returncode={process.returncode}, "
                    f"stderr={stderr_text[:500]!r}",
                    file=sys.stderr,
                )
            return ExecutionResult(
                session_id="",  # Codex doesn't provide session IDs
                output=output.strip(),
                cost_usd=0.0,  # Codex doesn't report cost in CLI output
                duration_ms=elapsed_ms,
                num_turns=len([e for e in all_events if e.event_type == "assistant"]),
                is_error=process.returncode != 0,
                raw_output=output,
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
        """Parse a line of output into a StreamEvent if possible."""
        try:
            data = json.loads(line.strip())
            return StreamEvent(
                event_type=data.get("type", "unknown"),
                data=data,
                source=self.AGENT_TYPE,
            )
        except json.JSONDecodeError:
            # Plain text output, create a text event
            if line.strip():
                return StreamEvent(
                    event_type="text",
                    data={"content": line.strip()},
                    source=self.AGENT_TYPE,
                )
            return None

    def _parse_result(
        self, result: subprocess.CompletedProcess, elapsed_ms: int
    ) -> ExecutionResult:
        """Parse the output from Codex CLI.

        Handles both single JSON object and JSONL (multiple JSON objects per line)
        output formats. For JSONL, prefers the last "result" type event.
        """
        raw_output = result.stdout

        # Try to parse as single JSON object first
        try:
            data = json.loads(raw_output)
            return ExecutionResult(
                session_id=data.get("session_id", ""),
                output=data.get("result", data.get("output", "")),
                cost_usd=0.0,  # Codex doesn't report cost
                duration_ms=data.get("duration_ms", elapsed_ms),
                num_turns=data.get("num_turns", 0),
                is_error=data.get("is_error", False) or result.returncode != 0,
                raw_output=raw_output,
                agent_type=self.AGENT_TYPE,
            )
        except json.JSONDecodeError:
            pass

        # Try JSONL parsing (multiple JSON objects, one per line)
        events: list[dict[str, Any]] = []
        text_lines: list[str] = []

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                text_lines.append(line)

        if events:
            # Look for a "result" type event, prefer the last one
            result_event = None
            for event in reversed(events):
                if event.get("type") == "result":
                    result_event = event
                    break

            if result_event:
                return ExecutionResult(
                    session_id=result_event.get("session_id", ""),
                    output=result_event.get("result", result_event.get("output", "")),
                    cost_usd=0.0,
                    duration_ms=result_event.get("duration_ms", elapsed_ms),
                    num_turns=result_event.get("num_turns", len(events)),
                    is_error=result_event.get("is_error", False)
                    or result.returncode != 0,
                    raw_output=raw_output,
                    agent_type=self.AGENT_TYPE,
                )

            # No result event, but we have events - extract content from them
            output_parts = []
            for event in events:
                if "content" in event:
                    output_parts.append(event["content"])
                elif "text" in event:
                    output_parts.append(event["text"])
                elif "output" in event:
                    output_parts.append(event["output"])

            return ExecutionResult(
                session_id="",
                output="\n".join(output_parts) if output_parts else raw_output.strip(),
                cost_usd=0.0,
                duration_ms=elapsed_ms,
                num_turns=len(events),
                is_error=result.returncode != 0,
                raw_output=raw_output,
                agent_type=self.AGENT_TYPE,
            )

        # Plain text output (no valid JSON found)
        return ExecutionResult(
            session_id="",
            output=raw_output.strip(),
            cost_usd=0.0,
            duration_ms=elapsed_ms,
            num_turns=0,
            is_error=result.returncode != 0,
            raw_output=raw_output,
            agent_type=self.AGENT_TYPE,
        )

    def check_available(self) -> tuple[bool, str]:
        """Check if Codex CLI is available."""
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


class MockCodexExecutor(CodexExecutor):
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
            session_id="",
            output="Mock Codex execution completed successfully",
            cost_usd=0.0,
            duration_ms=1000,
            num_turns=1,
            is_error=False,
            raw_output="{}",
            agent_type=self.AGENT_TYPE,
        )
