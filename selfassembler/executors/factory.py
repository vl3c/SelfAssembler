"""Factory and registry for agent executors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from selfassembler.executors.base import AgentExecutor, StreamEvent

if TYPE_CHECKING:
    pass


# Registry of executor types
EXECUTOR_REGISTRY: dict[str, type[AgentExecutor]] = {}


def register_executor(agent_type: str, executor_class: type[AgentExecutor]) -> None:
    """
    Register an executor class for a given agent type.

    Args:
        agent_type: The agent type identifier (e.g., "claude", "codex")
        executor_class: The executor class to register
    """
    EXECUTOR_REGISTRY[agent_type] = executor_class


def get_executor_class(agent_type: str) -> type[AgentExecutor]:
    """
    Get the executor class for a given agent type.

    Args:
        agent_type: The agent type identifier

    Returns:
        The executor class

    Raises:
        ValueError: If the agent type is not registered
    """
    if agent_type not in EXECUTOR_REGISTRY:
        available = ", ".join(EXECUTOR_REGISTRY.keys())
        raise ValueError(f"Unknown agent type: '{agent_type}'. Available types: {available}")
    return EXECUTOR_REGISTRY[agent_type]


def create_executor(
    agent_type: str,
    working_dir: Path,
    default_timeout: int = 600,
    model: str | None = None,
    stream: bool = True,
    stream_callback: Callable[[StreamEvent], None] | None = None,
    verbose: bool = True,
    debug: str | None = None,
    **kwargs,
) -> AgentExecutor:
    """
    Create an executor instance for the given agent type.

    Args:
        agent_type: The agent type identifier (e.g., "claude", "codex")
        working_dir: Working directory for the executor
        default_timeout: Default timeout in seconds
        model: Model to use (agent-specific)
        stream: Whether to enable streaming
        stream_callback: Callback for streaming events
        verbose: Whether to enable verbose output
        debug: Debug categories to enable
        **kwargs: Additional arguments passed to the executor

    Returns:
        An instance of the appropriate executor class

    Raises:
        ValueError: If the agent type is not registered
    """
    executor_class = get_executor_class(agent_type)
    return executor_class(
        working_dir=working_dir,
        default_timeout=default_timeout,
        model=model,
        stream=stream,
        stream_callback=stream_callback,
        verbose=verbose,
        debug=debug,
        **kwargs,
    )


def list_available_agents() -> list[str]:
    """
    List all registered agent types.

    Returns:
        List of agent type identifiers
    """
    return list(EXECUTOR_REGISTRY.keys())


def detect_installed_agents() -> dict[str, bool]:
    """
    Detect which agent CLIs are installed on the system.

    Returns:
        Dict mapping agent type to whether it's installed (e.g., {"claude": True, "codex": False})
    """
    installed = {}
    for agent_type, executor_class in EXECUTOR_REGISTRY.items():
        try:
            # Create a minimal executor just to check availability
            executor = executor_class(working_dir=Path("."), stream=False)
            is_available, _ = executor.check_available()
            installed[agent_type] = is_available
        except Exception:
            installed[agent_type] = False
    return installed


def get_available_agents() -> list[str]:
    """
    Get list of agent types that are actually installed.

    Returns:
        List of installed agent type identifiers
    """
    installed = detect_installed_agents()
    return [agent for agent, available in installed.items() if available]


def auto_configure_agents() -> tuple[str, str | None, bool]:
    """
    Auto-detect installed agents and return optimal configuration.

    Returns:
        Tuple of (primary_agent, secondary_agent, debate_enabled)
        - If both claude and codex installed: ("claude", "codex", True)
        - If only claude installed: ("claude", None, False)
        - If only codex installed: ("codex", None, False)
        - If neither installed: ("claude", None, False) with warning

    The preference order for primary agent is: claude > codex
    """
    installed = detect_installed_agents()

    claude_available = installed.get("claude", False)
    codex_available = installed.get("codex", False)

    if claude_available and codex_available:
        # Both available - enable debate with claude as primary
        return "claude", "codex", True
    elif claude_available:
        # Only claude - single agent mode
        return "claude", None, False
    elif codex_available:
        # Only codex - single agent mode
        return "codex", None, False
    else:
        # Neither available - default to claude, will fail at runtime
        return "claude", None, False


def _register_default_executors() -> None:
    """Register the default executor implementations."""
    from selfassembler.executors.claude import ClaudeExecutor
    from selfassembler.executors.codex import CodexExecutor

    register_executor("claude", ClaudeExecutor)
    register_executor("codex", CodexExecutor)


# Register default executors on module import
_register_default_executors()
