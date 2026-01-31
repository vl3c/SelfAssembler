"""SelfAssembler - Autonomous multi-phase workflow orchestrator for Claude Code CLI."""

__version__ = "0.1.0"
__author__ = "SelfAssembler Contributors"

from selfassembler.config import WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.executor import ClaudeExecutor, ExecutionResult
from selfassembler.orchestrator import Orchestrator

__all__ = [
    "__version__",
    "WorkflowConfig",
    "WorkflowContext",
    "ClaudeExecutor",
    "ExecutionResult",
    "Orchestrator",
]
