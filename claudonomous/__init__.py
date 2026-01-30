"""Claudonomous - Autonomous multi-phase workflow orchestrator for Claude Code CLI."""

__version__ = "0.1.0"
__author__ = "Claudonomous Contributors"

from claudonomous.config import WorkflowConfig
from claudonomous.context import WorkflowContext
from claudonomous.executor import ClaudeExecutor, ExecutionResult
from claudonomous.orchestrator import Orchestrator

__all__ = [
    "__version__",
    "WorkflowConfig",
    "WorkflowContext",
    "ClaudeExecutor",
    "ExecutionResult",
    "Orchestrator",
]
