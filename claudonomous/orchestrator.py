"""Workflow orchestration and state machine."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from claudonomous.context import WorkflowContext
from claudonomous.errors import (
    ApprovalTimeoutError,
    BudgetExceededError,
    ContainerRequiredError,
    PhaseFailedError,
)
from claudonomous.executor import ClaudeExecutor
from claudonomous.git import GitManager
from claudonomous.notifications import Notifier, create_notifier_from_config
from claudonomous.phases import PHASE_CLASSES, PHASE_NAMES, Phase, PhaseResult
from claudonomous.state import ApprovalStore, CheckpointManager, StateStore

if TYPE_CHECKING:
    from claudonomous.config import WorkflowConfig


class Orchestrator:
    """
    Orchestrates the workflow execution through all phases.

    The orchestrator:
    - Manages phase transitions
    - Handles checkpointing and recovery
    - Enforces budget limits
    - Manages approval gates
    - Sends notifications
    - Handles cleanup on failure
    """

    PHASES = PHASE_CLASSES

    def __init__(
        self,
        context: WorkflowContext,
        config: "WorkflowConfig",
        executor: ClaudeExecutor | None = None,
        notifier: Notifier | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        self.context = context
        self.config = config
        self.executor = executor or ClaudeExecutor(
            working_dir=context.repo_path,
            default_timeout=config.claude.default_timeout,
        )
        self.notifier = notifier or create_notifier_from_config(config.to_dict())
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.approval_store = ApprovalStore(context.plans_dir)

        # Enforce container for autonomous mode
        if config.autonomous_mode:
            self._enforce_container_runtime()

    def _enforce_container_runtime(self) -> None:
        """Refuse to run autonomous mode outside a container."""
        # Check 1: Look for /.dockerenv file (Docker)
        in_docker = os.path.exists("/.dockerenv")

        # Check 2: Check cgroup (Docker/Podman)
        in_cgroup = False
        try:
            with open("/proc/1/cgroup") as f:
                content = f.read()
                in_cgroup = "docker" in content or "kubepods" in content
        except (FileNotFoundError, PermissionError):
            pass

        # Check 3: Environment variable override (for testing)
        override = os.environ.get("CLAUDONOMOUS_ALLOW_HOST_AUTONOMOUS") == "I_ACCEPT_THE_RISK"

        if not (in_docker or in_cgroup or override):
            print(
                """
╔══════════════════════════════════════════════════════════════════╗
║  ERROR: Autonomous mode requires container isolation             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Autonomous mode grants Claude full system access, including:    ║
║  - Execute any shell command                                     ║
║  - Read/write any file you have access to                        ║
║  - Make network requests                                         ║
║                                                                  ║
║  To protect your system, run inside a Docker container:          ║
║                                                                  ║
║    ./run-autonomous.sh /path/to/project "task" task-name         ║
║                                                                  ║
║  Or build and run manually:                                      ║
║                                                                  ║
║    docker build -t claudonomous .                                ║
║    docker run -v /project:/workspace claudonomous "task"         ║
║                                                                  ║
║  To bypass (NOT RECOMMENDED):                                    ║
║    export CLAUDONOMOUS_ALLOW_HOST_AUTONOMOUS="I_ACCEPT_THE_RISK" ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""",
                file=sys.stderr,
            )
            raise ContainerRequiredError()

        if override:
            print(
                """
⚠️  WARNING: Running autonomous mode on HOST SYSTEM
⚠️  Claude has full access to your files and system
⚠️  You accepted this risk via CLAUDONOMOUS_ALLOW_HOST_AUTONOMOUS
""",
                file=sys.stderr,
            )

    def run_workflow(self, skip_to: str | None = None) -> WorkflowContext:
        """
        Run the complete workflow through all phases.

        Args:
            skip_to: Optional phase name to skip to (for resume)

        Returns:
            The final workflow context

        Raises:
            PhaseFailedError: If a phase fails
            BudgetExceededError: If budget is exceeded
            ApprovalTimeoutError: If approval times out
        """
        self.notifier.on_workflow_started(self.context)

        # Determine starting phase
        start_index = 0
        if skip_to:
            try:
                start_index = PHASE_NAMES.index(skip_to)
            except ValueError:
                raise ValueError(f"Unknown phase: {skip_to}. Valid phases: {PHASE_NAMES}")

        try:
            for i, phase_class in enumerate(self.PHASES):
                # Skip phases until we reach the starting phase
                if i < start_index:
                    continue

                # Skip disabled phases
                phase_config = self.config.get_phase_config(phase_class.name)
                if not phase_config.enabled:
                    continue

                # Create and run phase
                phase = phase_class(self.context, self.executor, self.config)
                self._run_phase(phase)

            # Workflow complete
            self.notifier.on_workflow_complete(self.context)
            return self.context

        except (BudgetExceededError, PhaseFailedError, ApprovalTimeoutError) as e:
            self.notifier.on_workflow_failed(self.context, e)

            # Cleanup on failure if configured
            if self.config.git.cleanup_on_fail:
                self.cleanup(reason=str(e))

            raise

        except Exception as e:
            self.notifier.on_workflow_failed(self.context, e)
            raise

    def _run_phase(self, phase: Phase) -> PhaseResult:
        """Run a single phase with all the orchestration logic."""
        phase_name = phase.name
        phase_config = self.config.get_phase_config(phase_name)

        # Update current phase and checkpoint
        self.context.current_phase = phase_name
        self._checkpoint()

        # Check budget before starting
        if self.context.budget_remaining() < phase_config.estimated_cost:
            raise BudgetExceededError(
                f"Insufficient budget for {phase_name}. "
                f"Remaining: ${self.context.budget_remaining():.2f}, "
                f"Estimated: ${phase_config.estimated_cost:.2f}",
                current_cost=self.context.total_cost_usd,
                budget_limit=self.context.budget_limit_usd,
            )

        # Validate preconditions
        valid, error = phase.validate_preconditions()
        if not valid:
            raise PhaseFailedError(phase_name, error=f"Precondition failed: {error}")

        # Notify phase start
        self.notifier.on_phase_started(phase_name)

        # Run the phase
        result = phase.run()

        # Check for budget warning
        self.notifier.on_budget_warning(self.context)

        if result.success:
            # Mark phase complete
            self.context.mark_phase_complete(phase_name)

            # Store artifacts
            for key, value in result.artifacts.items():
                self.context.set_artifact(f"{phase_name}_{key}", value)

            self.notifier.on_phase_complete(phase_name, result)

            # Handle approval gate
            if self._needs_approval(phase):
                self._wait_for_approval(phase_name, result.artifacts)

        else:
            self.notifier.on_phase_failed(phase_name, result)
            raise PhaseFailedError(
                phase_name,
                error=result.error,
                artifacts=result.artifacts,
            )

        return result

    def _needs_approval(self, phase: Phase) -> bool:
        """Check if phase requires approval."""
        if not self.config.approvals.enabled:
            return False

        # Check if this specific phase has an approval gate configured
        gates = self.config.approvals.gates
        return getattr(gates, phase.name, False) or phase.approval_gate

    def _wait_for_approval(self, phase_name: str, artifacts: dict) -> None:
        """Wait for approval before continuing."""
        self.notifier.on_approval_needed(phase_name, artifacts)

        # Check if already approved
        if self.approval_store.is_approved(phase_name):
            return

        # Wait for approval file
        approved = self.approval_store.wait_for_approval(
            phase_name,
            timeout_hours=self.config.approvals.timeout_hours,
        )

        if not approved:
            raise ApprovalTimeoutError(phase_name, self.config.approvals.timeout_hours)

    def _checkpoint(self) -> None:
        """Create a checkpoint of the current state."""
        try:
            checkpoint_id = self.checkpoint_manager.create_checkpoint(self.context)
            self.notifier.on_checkpoint_created(checkpoint_id)
        except Exception:
            pass  # Don't fail workflow on checkpoint failure

    def cleanup(self, reason: str = "manual") -> None:
        """
        Clean up resources after workflow completion or failure.

        This removes the worktree and optionally the remote branch.
        """
        # Remove worktree
        if self.context.worktree_path and self.context.worktree_path.exists():
            try:
                git = GitManager(self.context.repo_path)
                git.remove_worktree(self.context.worktree_path, force=True)
            except Exception:
                pass

        # Remove remote branch if configured and pushed
        if (
            self.config.git.cleanup_remote_on_fail
            and self.context.branch_pushed
            and self.context.branch_name
        ):
            try:
                git = GitManager(self.context.repo_path)
                git.delete_remote_branch(self.context.branch_name)
            except Exception:
                pass

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_id: str,
        config: "WorkflowConfig | None" = None,
    ) -> "Orchestrator":
        """
        Create an orchestrator from a checkpoint.

        Args:
            checkpoint_id: The checkpoint ID to resume from
            config: Optional config override

        Returns:
            An Orchestrator ready to resume the workflow
        """
        from claudonomous.config import WorkflowConfig

        checkpoint_manager = CheckpointManager()
        context = checkpoint_manager.load_checkpoint(checkpoint_id)

        # Load config from file if not provided
        if config is None:
            config = WorkflowConfig.load()

        return cls(context, config)

    def resume_workflow(self) -> WorkflowContext:
        """
        Resume a workflow from the last completed phase.

        Returns:
            The final workflow context
        """
        # Find the first incomplete phase
        skip_to = None
        for phase_name in PHASE_NAMES:
            if phase_name not in self.context.completed_phases:
                skip_to = phase_name
                break

        if skip_to is None:
            # All phases complete
            return self.context

        return self.run_workflow(skip_to=skip_to)


def create_orchestrator(
    task_description: str,
    task_name: str,
    repo_path: Path | None = None,
    config: "WorkflowConfig | None" = None,
) -> Orchestrator:
    """
    Create a new Orchestrator for a task.

    Args:
        task_description: Description of the task
        task_name: Short name for the task (used in branch/file names)
        repo_path: Path to the repository (defaults to current directory)
        config: Optional configuration

    Returns:
        A configured Orchestrator
    """
    from claudonomous.config import WorkflowConfig

    if repo_path is None:
        repo_path = Path.cwd()

    if config is None:
        config = WorkflowConfig.load()

    plans_dir = Path(config.plans_dir)
    if not plans_dir.is_absolute():
        plans_dir = repo_path / plans_dir

    context = WorkflowContext(
        task_description=task_description,
        task_name=task_name,
        repo_path=repo_path,
        plans_dir=plans_dir,
        budget_limit_usd=config.budget_limit_usd,
    )

    return Orchestrator(context, config)
