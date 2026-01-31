"""SelfAssembler - Autonomous multi-phase workflow orchestrator for Claude Code CLI."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("selfassembler")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development
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
