"""Executors package for agent CLI implementations."""

from selfassembler.executors.base import AgentExecutor, ExecutionResult, StreamEvent
from selfassembler.executors.claude import ClaudeExecutor, MockClaudeExecutor
from selfassembler.executors.codex import CodexExecutor, MockCodexExecutor
from selfassembler.executors.factory import (
    EXECUTOR_REGISTRY,
    create_executor,
    get_executor_class,
    list_available_agents,
    register_executor,
)

__all__ = [
    # Base classes
    "AgentExecutor",
    "ExecutionResult",
    "StreamEvent",
    # Claude executor
    "ClaudeExecutor",
    "MockClaudeExecutor",
    # Codex executor
    "CodexExecutor",
    "MockCodexExecutor",
    # Factory functions
    "create_executor",
    "get_executor_class",
    "list_available_agents",
    "register_executor",
    "EXECUTOR_REGISTRY",
]
