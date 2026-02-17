"""Abstract base class for agent executors."""

from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionResult:
    """Result from an agent CLI execution."""

    session_id: str
    output: str
    cost_usd: float
    duration_ms: int
    num_turns: int
    is_error: bool
    raw_output: str
    subagent_results: list[dict[str, Any]] = field(default_factory=list)
    agent_type: str = "unknown"

    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return self.duration_ms / 1000.0

    def validate(self) -> ExecutionResult:
        """Flag suspicious results as errors."""
        if not self.is_error and self.cost_usd == 0.0 and not self.output.strip():
            print(
                f"[{self.agent_type}] validate: suspicious result — "
                f"zero cost, empty output, duration={self.duration_ms}ms, "
                f"raw_output={self.raw_output[:200]!r}",
                file=sys.stderr,
            )
            return ExecutionResult(
                session_id=self.session_id,
                output="Agent produced no output and reported zero cost (possible auth/config issue)",
                cost_usd=0.0,
                duration_ms=self.duration_ms,
                num_turns=self.num_turns,
                is_error=True,
                raw_output=self.raw_output,
                agent_type=self.agent_type,
            )
        return self


@dataclass
class StreamEvent:
    """A single streaming event from an agent CLI."""

    event_type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"


class AgentExecutor(ABC):
    """
    Abstract base class for agent CLI executors.

    Defines the common interface that all agent executors must implement.
    """

    AGENT_TYPE: str = "base"
    CLI_COMMAND: str = ""
    INSTALL_INSTRUCTIONS: str = ""

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
        self.working_dir = working_dir
        self.default_timeout = default_timeout
        self.model = model
        self.stream = stream
        self.stream_callback = stream_callback
        self.verbose = verbose
        self.debug = debug

    @abstractmethod
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
        Execute a prompt with the agent CLI.

        Args:
            prompt: The prompt to send to the agent
            permission_mode: Permission mode (agent-specific interpretation)
            allowed_tools: List of allowed tools (agent-specific)
            max_turns: Maximum number of agentic turns
            timeout: Timeout in seconds
            resume_session: Session ID to resume (if supported)
            dangerous_mode: Skip permission prompts
            working_dir: Override working directory
            stream: Override streaming mode

        Returns:
            ExecutionResult with parsed output
        """
        pass

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """
        Check if the agent CLI is available.

        Returns:
            Tuple of (is_available, version_or_error_message)
        """
        pass

    @abstractmethod
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
        """
        Build the CLI command to execute.

        Args:
            prompt: The prompt to send
            permission_mode: Permission mode
            allowed_tools: Allowed tools list
            max_turns: Maximum turns
            resume_session: Session to resume
            dangerous_mode: Skip permissions
            streaming: Whether to use streaming output

        Returns:
            Command as list of strings
        """
        pass

    def execute_simple(self, prompt: str, timeout: int = 60) -> str:
        """
        Execute a simple prompt and return just the text output.

        This is a convenience method for quick, simple operations.
        """
        result = self.execute(
            prompt=prompt,
            max_turns=5,
            timeout=timeout,
        )
        return result.output
