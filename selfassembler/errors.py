"""Custom exceptions for SelfAssembler."""

from __future__ import annotations


class SelfAssemblerError(Exception):
    """Base exception for all SelfAssembler errors."""

    pass


class BudgetExceededError(SelfAssemblerError):
    """Raised when the workflow budget limit is exceeded."""

    def __init__(self, message: str, current_cost: float = 0.0, budget_limit: float = 0.0):
        super().__init__(message)
        self.current_cost = current_cost
        self.budget_limit = budget_limit


class ApprovalTimeoutError(SelfAssemblerError):
    """Raised when waiting for approval times out."""

    def __init__(self, phase: str, timeout_hours: float):
        super().__init__(f"Approval timeout for phase '{phase}' after {timeout_hours} hours")
        self.phase = phase
        self.timeout_hours = timeout_hours


class PhaseFailedError(SelfAssemblerError):
    """Raised when a phase fails to complete successfully."""

    def __init__(self, phase: str, error: str | None = None, artifacts: dict | None = None):
        msg = f"Phase '{phase}' failed"
        if error:
            msg += f": {error}"
        super().__init__(msg)
        self.phase = phase
        self.error = error
        self.artifacts = artifacts or {}


class PreflightFailedError(SelfAssemblerError):
    """Raised when preflight checks fail."""

    def __init__(self, failed_checks: list[dict]):
        messages = [check["message"] for check in failed_checks]
        super().__init__(f"Preflight checks failed:\n" + "\n".join(f"  - {m}" for m in messages))
        self.failed_checks = failed_checks


class ConfigurationError(SelfAssemblerError):
    """Raised when configuration is invalid."""

    pass


class CheckpointError(SelfAssemblerError):
    """Raised when checkpoint operations fail."""

    pass


class GitOperationError(SelfAssemblerError):
    """Raised when git operations fail."""

    def __init__(self, operation: str, error: str, returncode: int = 1):
        super().__init__(f"Git {operation} failed: {error}")
        self.operation = operation
        self.error = error
        self.returncode = returncode


class ClaudeExecutionError(SelfAssemblerError):
    """Raised when Claude CLI execution fails."""

    def __init__(self, message: str, output: str = "", returncode: int = 1):
        super().__init__(message)
        self.output = output
        self.returncode = returncode


class ContainerRequiredError(SelfAssemblerError):
    """Raised when autonomous mode is attempted outside a container."""

    def __init__(self):
        super().__init__(
            "Autonomous mode requires container isolation. "
            "Run with Docker or set SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS='I_ACCEPT_THE_RISK'"
        )


class WorktreeError(SelfAssemblerError):
    """Raised when worktree operations fail."""

    pass


class ConflictResolutionError(SelfAssemblerError):
    """Raised when merge conflicts cannot be resolved."""

    def __init__(self, conflicted_files: list[str] | None = None):
        msg = "Merge conflicts could not be auto-resolved"
        if conflicted_files:
            msg += f": {', '.join(conflicted_files)}"
        super().__init__(msg)
        self.conflicted_files = conflicted_files or []
