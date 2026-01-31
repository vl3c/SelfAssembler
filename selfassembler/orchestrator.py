"""Workflow orchestration and state machine."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selfassembler.context import WorkflowContext
from selfassembler.errors import (
    ApprovalTimeoutError,
    BudgetExceededError,
    ContainerRequiredError,
    PhaseFailedError,
)
from selfassembler.executor import ClaudeExecutor
from selfassembler.git import GitManager
from selfassembler.notifications import (
    Notifier,
    create_notifier_from_config,
    create_stream_callback,
)
from selfassembler.phases import PHASE_CLASSES, PHASE_NAMES, Phase, PhaseResult
from selfassembler.rules import RulesManager
from selfassembler.state import ApprovalStore, CheckpointManager

if TYPE_CHECKING:
    from selfassembler.config import WorkflowConfig


class WorkflowLogger:
    """Comprehensive logging for workflow debugging."""

    def __init__(self, log_dir: Path, task_name: str):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file = log_dir / f"workflow-{task_name}-{timestamp}.log"
        self.json_log_file = log_dir / f"workflow-{task_name}-{timestamp}.jsonl"
        self._entries: list[dict[str, Any]] = []

    def log(
        self,
        event: str,
        phase: str | None = None,
        data: dict[str, Any] | None = None,
        output: str | None = None,
    ) -> None:
        """Log an event with optional data and output."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "phase": phase,
            "data": data or {},
        }
        if output:
            entry["output"] = output[:10000]  # Truncate very long outputs

        self._entries.append(entry)

        # Write to text log
        with open(self.log_file, "a") as f:
            f.write(f"\n{'=' * 80}\n")
            f.write(f"[{entry['timestamp']}] {event}")
            if phase:
                f.write(f" (phase: {phase})")
            f.write("\n")
            if data:
                for k, v in data.items():
                    f.write(f"  {k}: {v}\n")
            if output:
                f.write(f"\n--- Output ---\n{output}\n--- End Output ---\n")

        # Write to JSON log
        with open(self.json_log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_command(self, command: str | list, cwd: Path | None, phase: str | None = None) -> None:
        """Log a command execution."""
        cmd_str = " ".join(command) if isinstance(command, list) else command
        self.log(
            "command_executed",
            phase=phase,
            data={"command": cmd_str, "cwd": str(cwd) if cwd else None},
        )

    def log_claude_call(
        self,
        prompt: str,
        working_dir: Path,
        phase: str | None = None,
        result: Any = None,
    ) -> None:
        """Log a Claude CLI invocation."""
        self.log(
            "claude_invocation",
            phase=phase,
            data={
                "working_dir": str(working_dir),
                "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt,
            },
            output=str(result) if result else None,
        )

    def finalize(self) -> Path:
        """Finalize and return the log file path."""
        self.log("workflow_log_finalized", data={"total_entries": len(self._entries)})
        return self.log_file


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
        config: WorkflowConfig,
        executor: ClaudeExecutor | None = None,
        notifier: Notifier | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        self.context = context
        self.config = config
        self.notifier = notifier or create_notifier_from_config(config.to_dict())

        # Initialize workflow logger
        log_dir = context.plans_dir.parent / "logs"
        self.logger = WorkflowLogger(log_dir, context.task_name)
        self.logger.log(
            "orchestrator_initialized",
            data={
                "task_name": context.task_name,
                "task_description": context.task_description,
                "repo_path": str(context.repo_path),
                "budget_limit": context.budget_limit_usd,
            },
        )

        # Set up streaming callback if streaming is enabled
        self._stream_callback = None
        if config.streaming.enabled:
            self._stream_callback = create_stream_callback(
                self.notifier,
                show_tool_calls=config.streaming.show_tool_calls,
                truncate_length=config.streaming.truncate_length,
            )

        self.executor = executor or self._create_executor(context.repo_path)
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.approval_store = ApprovalStore(context.plans_dir)

        # Enforce container for autonomous mode
        if config.autonomous_mode:
            self._enforce_container_runtime()

    def _create_executor(self, working_dir: Path) -> ClaudeExecutor:
        """Create a new ClaudeExecutor for the given working directory."""
        self.logger.log(
            "executor_created",
            data={"working_dir": str(working_dir)},
        )
        return ClaudeExecutor(
            working_dir=working_dir,
            default_timeout=self.config.claude.default_timeout,
            stream=self.config.streaming.enabled,
            stream_callback=self._stream_callback,
            verbose=self.config.streaming.verbose,
            debug=self.config.streaming.debug,
        )

    def _reinitialize_executor_for_worktree(self) -> None:
        """Reinitialize executor to use worktree as working directory.

        Called after setup phase creates the worktree to ensure all
        subsequent Claude operations happen inside the worktree.
        """
        if self.context.worktree_path and self.context.worktree_path.exists():
            self.logger.log(
                "executor_reinitializing_for_worktree",
                data={
                    "old_working_dir": str(self.executor.working_dir),
                    "new_working_dir": str(self.context.worktree_path),
                },
            )
            self.executor = self._create_executor(self.context.worktree_path)

    def _write_rules_to_worktree(self) -> None:
        """Write CLAUDE.md with project rules to the worktree.

        Called after setup phase to ensure Claude follows project rules.
        """
        if not self.context.worktree_path or not self.context.worktree_path.exists():
            return

        rules_manager = RulesManager(
            enabled_rules=self.config.rules.enabled_rules,
            custom_rules=self.config.rules.custom_rules,
        )

        rules_manager.write_to_worktree(self.context.worktree_path)

        active_rules = rules_manager.get_active_rules()
        if active_rules:
            self.logger.log(
                "rules_written_to_worktree",
                data={
                    "worktree_path": str(self.context.worktree_path),
                    "rule_count": len(active_rules),
                    "rule_ids": [r.id for r in active_rules],
                },
            )

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
        override = os.environ.get("SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS") == "I_ACCEPT_THE_RISK"

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
║    docker build -t selfassembler .                                ║
║    docker run -v /project:/workspace selfassembler "task"         ║
║                                                                  ║
║  To bypass (NOT RECOMMENDED):                                    ║
║    export SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS="I_ACCEPT_THE_RISK" ║
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
⚠️  You accepted this risk via SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS
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
        self.logger.log("workflow_started", data={"skip_to": skip_to})

        # Determine starting phase
        start_index = 0
        if skip_to:
            try:
                start_index = PHASE_NAMES.index(skip_to)
            except ValueError:
                raise ValueError(f"Unknown phase: {skip_to}. Valid phases: {PHASE_NAMES}") from None

        try:
            for i, phase_class in enumerate(self.PHASES):
                # Skip phases until we reach the starting phase
                if i < start_index:
                    self.logger.log(
                        "phase_skipped",
                        phase=phase_class.name,
                        data={"reason": "skip_to"},
                    )
                    continue

                # Skip disabled phases
                phase_config = self.config.get_phase_config(phase_class.name)
                if not phase_config.enabled:
                    self.logger.log(
                        "phase_skipped",
                        phase=phase_class.name,
                        data={"reason": "disabled"},
                    )
                    continue

                # Create and run phase
                phase = phase_class(self.context, self.executor, self.config)
                self._run_phase(phase)

                # After setup phase, reinitialize executor for worktree and write rules
                if phase_class.name == "setup" and self.context.worktree_path:
                    self._reinitialize_executor_for_worktree()
                    self._write_rules_to_worktree()

            # Workflow complete
            self.notifier.on_workflow_complete(self.context)
            self.logger.log(
                "workflow_completed",
                data={
                    "total_cost": self.context.total_cost_usd,
                    "pr_url": self.context.pr_url,
                    "branch_name": self.context.branch_name,
                },
            )

            # Smart cleanup: only if PR created and pushed
            if self._can_cleanup_safely():
                self.cleanup(reason="workflow_complete")

            log_file = self.logger.finalize()
            print(f"\nWorkflow log saved to: {log_file}")

            return self.context

        except (BudgetExceededError, PhaseFailedError, ApprovalTimeoutError) as e:
            self.notifier.on_workflow_failed(self.context, e)
            self.logger.log(
                "workflow_failed",
                data={"error": str(e), "error_type": type(e).__name__},
            )

            # Only cleanup if explicitly configured AND safe to do so
            if self.config.git.cleanup_on_fail and self._can_cleanup_safely():
                self.cleanup(reason=str(e))

            log_file = self.logger.finalize()
            print(f"\nWorkflow log saved to: {log_file}")

            raise

        except Exception as e:
            self.notifier.on_workflow_failed(self.context, e)
            self.logger.log(
                "workflow_error",
                data={"error": str(e), "error_type": type(e).__name__},
            )
            log_file = self.logger.finalize()
            print(f"\nWorkflow log saved to: {log_file}")
            raise

    def _can_cleanup_safely(self) -> bool:
        """Check if it's safe to cleanup the worktree.

        Only safe if:
        - PR was created (work is preserved in remote)
        - Branch was pushed
        """
        return bool(self.context.pr_url and self.context.branch_pushed)

    def _run_phase(self, phase: Phase) -> PhaseResult:
        """Run a single phase with all the orchestration logic."""
        phase_name = phase.name
        phase_config = self.config.get_phase_config(phase_name)
        max_retries = phase_config.max_retries

        self.logger.log(
            "phase_starting",
            phase=phase_name,
            data={
                "max_retries": max_retries,
                "estimated_cost": phase_config.estimated_cost,
                "working_dir": str(self.context.get_working_dir()),
                "executor_working_dir": str(self.executor.working_dir),
            },
        )

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
            self.logger.log(
                "phase_precondition_failed",
                phase=phase_name,
                data={"error": error},
            )
            raise PhaseFailedError(phase_name, error=f"Precondition failed: {error}")

        # Notify phase start
        self.notifier.on_phase_started(phase_name)

        # Run the phase with retry logic
        last_result = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                self.logger.log(
                    "phase_retry",
                    phase=phase_name,
                    data={"attempt": attempt, "max_retries": max_retries},
                )
                self.notifier.on_phase_retry(phase_name, attempt, max_retries)

            result = phase.run()
            last_result = result

            self.logger.log(
                "phase_attempt_complete",
                phase=phase_name,
                data={
                    "attempt": attempt,
                    "success": result.success,
                    "cost_usd": result.cost_usd,
                    "error": result.error[:500] if result.error else None,
                },
                output=str(result.artifacts) if result.artifacts else None,
            )

            # Check for budget warning
            self.notifier.on_budget_warning(self.context)

            if result.success:
                break

            # If not the last attempt, log and retry
            if attempt < max_retries:
                self.notifier.on_phase_failed(phase_name, result, will_retry=True)
            else:
                # Final attempt failed
                self.notifier.on_phase_failed(phase_name, result, will_retry=False)

        if last_result and last_result.success:
            # Mark phase complete
            self.context.mark_phase_complete(phase_name)

            # Store artifacts
            for key, value in last_result.artifacts.items():
                self.context.set_artifact(f"{phase_name}_{key}", value)

            self.notifier.on_phase_complete(phase_name, last_result)
            self.logger.log(
                "phase_completed",
                phase=phase_name,
                data={
                    "cost_usd": last_result.cost_usd,
                    "artifacts": list(last_result.artifacts.keys()),
                },
            )

            # Handle approval gate
            if self._needs_approval(phase):
                self._wait_for_approval(phase_name, last_result.artifacts)

        else:
            self.logger.log(
                "phase_failed",
                phase=phase_name,
                data={"error": last_result.error if last_result else "No result"},
            )
            raise PhaseFailedError(
                phase_name,
                error=last_result.error if last_result else "Phase returned no result",
                artifacts=last_result.artifacts if last_result else {},
            )

        return last_result

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
        config: WorkflowConfig | None = None,
    ) -> Orchestrator:
        """
        Create an orchestrator from a checkpoint.

        Args:
            checkpoint_id: The checkpoint ID to resume from
            config: Optional config override

        Returns:
            An Orchestrator ready to resume the workflow
        """
        from selfassembler.config import WorkflowConfig

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
    config: WorkflowConfig | None = None,
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
    from selfassembler.config import WorkflowConfig

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
