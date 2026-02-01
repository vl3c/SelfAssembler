"""SelfAssembler - Autonomous multi-phase workflow orchestrator for agent CLIs."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("selfassembler")
except PackageNotFoundError:
    __version__ = "0.2.0"  # Fallback for development
__author__ = "SelfAssembler Contributors"

from selfassembler.config import AgentConfig, WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.executor import ClaudeExecutor, ExecutionResult
from selfassembler.executors import (
    AgentExecutor,
    CodexExecutor,
    StreamEvent,
    create_executor,
    list_available_agents,
)
from selfassembler.orchestrator import Orchestrator

__all__ = [
    "__version__",
    # Config
    "WorkflowConfig",
    "AgentConfig",
    "WorkflowContext",
    # Executors
    "AgentExecutor",
    "ClaudeExecutor",
    "CodexExecutor",
    "ExecutionResult",
    "StreamEvent",
    "create_executor",
    "list_available_agents",
    # Orchestration
    "Orchestrator",
]
