"""Workflow orchestration and state machine."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selfassembler.context import WorkflowContext
from selfassembler.error_classifier import ErrorOrigin, classify_error
from selfassembler.errors import (
    AgentExecutionError,
    ApprovalTimeoutError,
    BudgetExceededError,
    ContainerRequiredError,
    FailureCategory,
    PhaseFailedError,
)
from selfassembler.executor import ClaudeExecutor  # Keep for backward compat type hints
from selfassembler.executors import AgentExecutor, create_executor
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
        executor: AgentExecutor | ClaudeExecutor | None = None,
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

        # Create secondary executor for debate if enabled
        self.secondary_executor: AgentExecutor | None = None
        if config.debate.enabled:
            self.secondary_executor = self._create_secondary_executor(context.repo_path)

        # Create fallback executor (auto-detected or explicitly configured)
        self.fallback_executor: AgentExecutor | None = self._create_fallback_executor(
            context.repo_path
        )

        # Enforce container for autonomous mode
        if config.autonomous_mode:
            self._enforce_container_runtime()

    def _create_executor(self, working_dir: Path) -> AgentExecutor:
        """Create a new agent executor for the given working directory."""
        agent_config = self.config.get_effective_agent_config()
        self.logger.log(
            "executor_created",
            data={
                "working_dir": str(working_dir),
                "agent_type": agent_config.type,
            },
        )
        return create_executor(
            agent_type=agent_config.type,
            working_dir=working_dir,
            default_timeout=agent_config.default_timeout,
            model=agent_config.model,
            stream=self.config.streaming.enabled,
            stream_callback=self._stream_callback,
            verbose=self.config.streaming.verbose,
            debug=self.config.streaming.debug,
        )

    def _create_secondary_executor(self, working_dir: Path) -> AgentExecutor:
        """Create a secondary agent executor for debate."""
        debate_config = self.config.debate
        secondary_agent_type = debate_config.secondary_agent

        self.logger.log(
            "secondary_executor_created",
            data={
                "working_dir": str(working_dir),
                "agent_type": secondary_agent_type,
            },
        )

        return create_executor(
            agent_type=secondary_agent_type,
            working_dir=working_dir,
            default_timeout=debate_config.turn_timeout_seconds,
            model=None,  # Use default model for secondary agent
            stream=self.config.streaming.enabled,
            stream_callback=self._stream_callback,
            verbose=self.config.streaming.verbose,
            debug=self.config.streaming.debug,
        )

    def _create_fallback_executor(self, working_dir: Path) -> AgentExecutor | None:
        """Create a fallback agent executor for agent-specific failure recovery.

        If fallback_agent is explicitly configured, uses that type (even if same
        as primary — a fresh session clears accumulated context pressure).
        Otherwise, auto-detects: picks the first installed agent that differs
        from the primary agent type.
        """
        from selfassembler.executors import detect_installed_agents

        agent_config = self.config.get_effective_agent_config()
        primary_type = agent_config.type
        fallback_type = self.config.fallback.fallback_agent

        if fallback_type is None:
            # Auto-detect: pick a different installed agent
            installed = detect_installed_agents()
            for agent_type, available in installed.items():
                if available and agent_type != primary_type:
                    fallback_type = agent_type
                    break

            if fallback_type is None:
                self.logger.log(
                    "fallback_executor_unavailable",
                    data={
                        "reason": "No alternative agent installed",
                        "primary_type": primary_type,
                    },
                )
                return None

        self.logger.log(
            "fallback_executor_created",
            data={
                "working_dir": str(working_dir),
                "agent_type": fallback_type,
                "primary_type": primary_type,
            },
        )

        return create_executor(
            agent_type=fallback_type,
            working_dir=working_dir,
            default_timeout=agent_config.default_timeout,
            model=None,  # Use default model for fallback agent
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
            # Update plans_dir to be inside the worktree so that agents
            # running in the worktree write output files to the correct
            # location (relative to their cwd)
            old_plans_dir = self.context.plans_dir
            relative_plans = self.context.plans_dir.relative_to(self.context.repo_path)
            self.context.plans_dir = self.context.worktree_path / relative_plans

            self.logger.log(
                "executor_reinitializing_for_worktree",
                data={
                    "old_working_dir": str(self.executor.working_dir),
                    "new_working_dir": str(self.context.worktree_path),
                    "old_plans_dir": str(old_plans_dir),
                    "new_plans_dir": str(self.context.plans_dir),
                },
            )
            self.executor = self._create_executor(self.context.worktree_path)

            # Also reinitialize secondary executor for debate
            if self.secondary_executor is not None:
                self.logger.log(
                    "secondary_executor_reinitializing_for_worktree",
                    data={
                        "old_working_dir": str(self.secondary_executor.working_dir),
                        "new_working_dir": str(self.context.worktree_path),
                    },
                )
                self.secondary_executor = self._create_secondary_executor(
                    self.context.worktree_path
                )

            # Also reinitialize fallback executor
            if self.fallback_executor is not None:
                self.logger.log(
                    "fallback_executor_reinitializing_for_worktree",
                    data={
                        "old_working_dir": str(self.fallback_executor.working_dir),
                        "new_working_dir": str(self.context.worktree_path),
                    },
                )
                self.fallback_executor = self._create_fallback_executor(
                    self.context.worktree_path
                )

    def _create_phase(self, phase_class: type[Phase]) -> Phase:
        """Create a phase instance, passing secondary executor if supported.

        For phases that inherit from DebatePhase, LintCheckPhase, or
        TestExecutionPhase, the secondary executor is passed to enable
        multi-agent collaboration (agent alternation for fix loops).
        """
        from selfassembler.phases import DebatePhase, LintCheckPhase, TestExecutionPhase

        # Pass secondary executor to phases that support it
        if issubclass(phase_class, (DebatePhase, LintCheckPhase, TestExecutionPhase)):
            return phase_class(
                context=self.context,
                executor=self.executor,
                config=self.config,
                secondary_executor=self.secondary_executor,
            )
        else:
            return phase_class(
                context=self.context,
                executor=self.executor,
                config=self.config,
            )

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
                phase = self._create_phase(phase_class)
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

    # Phases excluded from fallback — infrastructure, non-idempotent, or side-effect phases
    _FALLBACK_EXCLUDED_PHASES = frozenset({
        "preflight", "setup", "commit_prep", "pr_creation", "pr_self_review",
        "conflict_check",
    })

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

            try:
                result = phase.run()
            except AgentExecutionError as e:
                result = PhaseResult(
                    success=False,
                    error=str(e),
                    failure_category=FailureCategory.AGENT_SPECIFIC,
                )
            last_result = result

            self.logger.log(
                "phase_attempt_complete",
                phase=phase_name,
                data={
                    "attempt": attempt,
                    "success": result.success,
                    "cost_usd": result.cost_usd,
                    "error": result.error[:500] if result.error else None,
                    "failure_category": str(result.failure_category) if result.failure_category else None,
                },
                output=str(result.artifacts) if result.artifacts else None,
            )

            # Check for budget warning
            self.notifier.on_budget_warning(self.context)

            if result.success:
                break

            # Category-based retry decision
            if result.failure_category in (FailureCategory.FATAL, FailureCategory.OSCILLATING):
                break  # No point retrying (notification deferred until after fallback)

            # If not the last attempt, notify and retry
            if attempt < max_retries:
                self.notifier.on_phase_failed(phase_name, result, will_retry=True)
            # else: defer final failure notification until after fallback attempt

        # Attempt fallback if retries exhausted and phase still failed
        if (
            last_result
            and not last_result.success
            and self.fallback_executor is not None
            and self.context.budget_remaining() > 0
            and self._should_attempt_fallback(last_result, phase)
        ):
            fallback_result = self._attempt_fallback(phase, last_result)
            if fallback_result is not None:
                last_result = fallback_result

        # Now emit final failure notification if still failed
        if last_result and not last_result.success:
            self.notifier.on_phase_failed(phase_name, last_result, will_retry=False)

        if last_result and last_result.success:
            # Mark phase complete
            self.context.mark_phase_complete(phase_name)

            # Store artifacts
            for key, value in last_result.artifacts.items():
                self.context.set_artifact(f"{phase_name}_{key}", value)

            # Accumulate warnings for workflow-level reporting
            if last_result.warnings:
                existing_warnings = self.context.get_artifact("workflow_warnings", [])
                for w in last_result.warnings:
                    existing_warnings.append(f"[{phase_name}] {w}")
                self.context.set_artifact("workflow_warnings", existing_warnings)

            self.notifier.on_phase_complete(phase_name, last_result)
            self.logger.log(
                "phase_completed",
                phase=phase_name,
                data={
                    "cost_usd": last_result.cost_usd,
                    "artifacts": list(last_result.artifacts.keys()),
                    "warnings": last_result.warnings or None,
                },
            )

            # Handle approval gate
            if self._needs_approval(phase):
                self._wait_for_approval(phase_name, last_result.artifacts)

        else:
            failure_cat = last_result.failure_category if last_result else None
            fail_data: dict[str, Any] = {
                "error": last_result.error if last_result else "No result",
                "failure_category": str(failure_cat) if failure_cat else None,
            }
            if last_result and last_result.artifacts:
                fail_data["artifacts"] = {
                    k: str(v)[:500] for k, v in last_result.artifacts.items()
                }
            if last_result and last_result.warnings:
                fail_data["warnings"] = last_result.warnings
            self.logger.log(
                "phase_failed",
                phase=phase_name,
                data=fail_data,
            )
            raise PhaseFailedError(
                phase_name,
                error=last_result.error if last_result else "Phase returned no result",
                artifacts=last_result.artifacts if last_result else {},
            )

        return last_result

    def _should_attempt_fallback(self, result: PhaseResult, phase: Phase) -> bool:
        """Determine whether to attempt fallback for a failed phase.

        Returns False for:
        - Phases in _FALLBACK_EXCLUDED_PHASES (infrastructure, non-idempotent)
        - DebatePhase, LintCheckPhase, or TestExecutionPhase subclasses
          (have their own multi-agent logic via agent alternation)
        - Task errors when trigger is "agent_errors"
        """
        from selfassembler.phases import DebatePhase, LintCheckPhase, TestExecutionPhase

        # Excluded phase names
        if phase.name in self._FALLBACK_EXCLUDED_PHASES:
            return False

        # Excluded phase types (have their own secondary executor handling)
        if isinstance(phase, (DebatePhase, LintCheckPhase, TestExecutionPhase)):
            return False

        # If already categorized as agent-specific (e.g., from AgentExecutionError),
        # always allow fallback regardless of trigger mode
        if result.failure_category == FailureCategory.AGENT_SPECIFIC:
            return True

        # Check trigger mode
        if self.config.fallback.trigger == "all_errors":
            return True

        # "agent_errors" mode: classify the error text
        agent_type = getattr(phase.executor, "AGENT_TYPE", None)
        classification = classify_error(result.error, agent_type)
        return classification.origin == ErrorOrigin.AGENT

    def _attempt_fallback(self, phase: Phase, primary_result: PhaseResult) -> PhaseResult | None:
        """Attempt to run the phase with the fallback executor.

        Temporarily swaps the phase's executor to the fallback executor,
        runs the phase, and always restores the original executor.

        Returns the fallback PhaseResult if successful, None if fallback also failed.
        """
        if self.fallback_executor is None:
            return None

        fallback_type = getattr(self.fallback_executor, "AGENT_TYPE", "unknown")
        primary_type = getattr(self.executor, "AGENT_TYPE", "unknown")
        max_attempts = self.config.fallback.max_fallback_attempts

        self.logger.log(
            "fallback_attempting",
            phase=phase.name,
            data={
                "primary_agent": primary_type,
                "fallback_agent": fallback_type,
                "primary_error": primary_result.error[:300] if primary_result.error else None,
                "max_attempts": max_attempts,
            },
        )

        original_executor = phase.executor
        try:
            phase.executor = self.fallback_executor

            for attempt in range(max_attempts):
                try:
                    result = phase.run()
                except AgentExecutionError as e:
                    result = PhaseResult(
                        success=False,
                        error=str(e),
                        failure_category=FailureCategory.AGENT_SPECIFIC,
                    )

                self.logger.log(
                    "fallback_attempt_complete",
                    phase=phase.name,
                    data={
                        "attempt": attempt,
                        "success": result.success,
                        "cost_usd": result.cost_usd,
                        "fallback_agent": fallback_type,
                        "error": result.error[:300] if result.error else None,
                    },
                )

                if result.success:
                    result.executed_by = fallback_type
                    result.warnings.append(
                        f"Phase executed by fallback agent '{fallback_type}' "
                        f"after primary agent '{primary_type}' failed"
                    )
                    return result

                # If fallback also hits an agent-specific error, stop early
                is_agent_error = result.failure_category == FailureCategory.AGENT_SPECIFIC
                if not is_agent_error:
                    agent_type_fb = getattr(self.fallback_executor, "AGENT_TYPE", None)
                    fb_classification = classify_error(result.error, agent_type_fb)
                    is_agent_error = fb_classification.origin == ErrorOrigin.AGENT
                if is_agent_error:
                    self.logger.log(
                        "fallback_agent_error",
                        phase=phase.name,
                        data={
                            "reason": "Fallback agent also hit agent-specific error",
                            "error": result.error[:300] if result.error else None,
                        },
                    )
                    break

        finally:
            phase.executor = original_executor

        self.logger.log(
            "fallback_failed",
            phase=phase.name,
            data={"fallback_agent": fallback_type},
        )
        return None

    def _needs_approval(self, phase: Phase) -> bool:
        """Check if phase requires approval."""
        if not self.config.approvals.enabled:
            return False

        # Check if this specific phase has an approval gate configured
        gates = self.config.approvals.gates
        phase_name_normalized = phase.name.replace("-", "_")
        gate_config = getattr(gates, phase_name_normalized, None)
        if gate_config is True:
            return True
        if gate_config is False:
            return False
        return phase.approval_gate

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
            checkpoint_id = self.checkpoint_manager.create_checkpoint(
                self.context, config=self.config,
            )
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

        Loads config from the checkpoint snapshot first (if available),
        then falls back to file-based config. CLI-level overrides should
        be applied on the returned orchestrator's config after this call.

        Args:
            checkpoint_id: The checkpoint ID to resume from
            config: Optional config override (used as fallback)

        Returns:
            An Orchestrator ready to resume the workflow
        """
        from selfassembler.config import WorkflowConfig

        checkpoint_manager = CheckpointManager()
        context = checkpoint_manager.load_checkpoint(checkpoint_id)

        # Load config from snapshot (prefer stored config over file-based)
        raw_data = checkpoint_manager.store.load(checkpoint_id)
        if raw_data and raw_data.get("config"):
            loaded_config = WorkflowConfig.model_validate(raw_data["config"])
        elif config is not None:
            loaded_config = config
        else:
            loaded_config = WorkflowConfig.load()

        return cls(context, loaded_config)

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
