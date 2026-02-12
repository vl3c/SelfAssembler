"""Command-line interface for SelfAssembler."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from selfassembler import __version__
from selfassembler.config import WorkflowConfig
from selfassembler.errors import (
    ApprovalTimeoutError,
    BudgetExceededError,
    ContainerRequiredError,
    PhaseFailedError,
    SelfAssemblerError,
)
from selfassembler.orchestrator import Orchestrator, create_orchestrator
from selfassembler.phases import PHASE_NAMES
from selfassembler.state import CheckpointManager


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="selfassembler",
        description="Autonomous multi-phase workflow orchestrator for Claude Code CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a task with approval gates
  selfassembler "Add user authentication" --name auth-feature

  # Run without approval gates
  selfassembler "Fix login bug" --name fix-login --no-approvals

  # Run in fully autonomous mode (requires container)
  selfassembler "Add new feature" --name feature --autonomous

  # Resume from checkpoint
  selfassembler --resume checkpoint_abc123

  # Skip to a specific phase
  selfassembler @plans/auth-feature.md --skip-to implementation

  # List available checkpoints
  selfassembler --list-checkpoints
""",
    )

    # Main arguments
    parser.add_argument(
        "task",
        nargs="?",
        help="Task description (or @path/to/plan.md to use existing plan)",
    )

    parser.add_argument(
        "--name",
        "-n",
        dest="task_name",
        help="Short name for the task (used in branch names)",
    )

    # Mode flags
    mode_group = parser.add_argument_group("execution modes")
    mode_group.add_argument(
        "--autonomous",
        action="store_true",
        help="Run in fully autonomous mode (requires container). "
        "No approval gates, no permission prompts, full system access.",
    )
    mode_group.add_argument(
        "--no-approvals",
        action="store_true",
        help="Disable approval gates (still prompts for permissions unless --autonomous)",
    )

    # Debate mode (mutually exclusive)
    debate_group = mode_group.add_mutually_exclusive_group()
    debate_group.add_argument(
        "--debate",
        action="store_true",
        default=None,
        help="Enable multi-agent debate mode (Claude + Codex). "
        "Auto-enabled when both agents are installed.",
    )
    debate_group.add_argument(
        "--no-debate",
        action="store_true",
        help="Disable multi-agent debate, use single agent only.",
    )

    # Resume and skip
    resume_group = parser.add_argument_group("resume options")
    resume_group.add_argument(
        "--resume",
        metavar="CHECKPOINT",
        help="Resume from a checkpoint ID",
    )
    resume_group.add_argument(
        "--skip-to",
        metavar="PHASE",
        choices=PHASE_NAMES,
        help=f"Skip to a specific phase. Choices: {', '.join(PHASE_NAMES)}",
    )
    resume_group.add_argument(
        "--skip-phases",
        metavar="PHASES",
        help="Comma-separated phases to mark complete and skip (e.g., 'lint_check,documentation'). "
        "Persistent: skipped phases stay skipped on future resumes.",
    )

    # Configuration
    config_group = parser.add_argument_group("configuration")
    config_group.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to configuration file (default: selfassembler.yaml)",
    )
    config_group.add_argument(
        "--budget",
        type=float,
        metavar="USD",
        help="Budget limit in USD (default: 15.0)",
    )
    config_group.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository (default: current directory)",
    )
    config_group.add_argument(
        "--plans-dir",
        type=Path,
        help="Directory for plans and artifacts (default: ./plans)",
    )
    config_group.add_argument(
        "--agent",
        choices=["claude", "codex"],
        help="Agent CLI to use (default: claude)",
    )

    # Utility commands
    util_group = parser.add_argument_group("utilities")
    util_group.add_argument(
        "--list-checkpoints",
        action="store_true",
        help="List available checkpoints and exit",
    )
    util_group.add_argument(
        "--list-phases",
        action="store_true",
        help="List all workflow phases and exit",
    )
    util_group.add_argument(
        "--init-config",
        action="store_true",
        help="Create a default configuration file and exit",
    )
    util_group.add_argument(
        "--approve",
        metavar="PHASE",
        help="Grant approval for a phase",
    )
    util_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what phases would run without executing them",
    )
    util_group.add_argument(
        "--help-phases",
        nargs="*",
        metavar="PHASE",
        help="Show detailed help for workflow phases. Optionally specify phase names.",
    )

    # Output
    output_group = parser.add_argument_group("output")
    output_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress non-essential output",
    )
    output_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    output_group.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming output (wait for complete response)",
    )
    output_group.add_argument(
        "--debug",
        type=str,
        metavar="CATEGORIES",
        help="Enable CC debug mode (e.g., 'api,mcp' or '!statsig,!file')",
    )

    # Plan review options
    plan_group = parser.add_argument_group("plan review")
    plan_group.add_argument(
        "--review-plan-approval",
        action="store_true",
        help="Require approval after plan review phase",
    )
    plan_group.add_argument(
        "--skip-plan-review",
        action="store_true",
        help="Skip the plan review phase entirely",
    )

    # Version
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def generate_task_name(task_description: str) -> str:
    """Generate a task name from the description."""
    import re

    # Extract first few words and slugify
    words = task_description.split()[:5]
    slug = "-".join(words)
    slug = re.sub(r"[^\w\s-]", "", slug.lower())
    slug = re.sub(r"[\s_]+", "-", slug)[:40].strip("-")
    return slug or "task"


def handle_list_checkpoints() -> int:
    """List available checkpoints."""
    manager = CheckpointManager()
    checkpoints = manager.list_checkpoints()

    if not checkpoints:
        print("No checkpoints found.")
        return 0

    print("Available checkpoints:\n")
    for cp in checkpoints:
        print(f"  {cp['id']}")
        print(f"    Task: {cp['task_name']}")
        print(f"    Phase: {cp['current_phase']}")
        print(f"    Cost: ${cp['cost_usd']:.2f}")
        print(f"    Created: {cp['created_at']}")
        print()

    return 0


def handle_list_phases() -> int:
    """List all workflow phases."""
    from selfassembler.phases import PHASE_CLASSES

    print("Workflow phases:\n")
    for i, phase_class in enumerate(PHASE_CLASSES, 1):
        approval = " (approval gate)" if phase_class.approval_gate else ""
        print(f"  {i:2}. {phase_class.name}{approval}")
        if phase_class.__doc__:
            print(f"      {phase_class.__doc__.strip()}")
    print()

    return 0


def _print_phase_help(phase_class: type, phase_num: int, total_phases: int) -> None:
    """Print detailed help for a single phase."""
    term_width = shutil.get_terminal_size().columns
    separator = "=" * term_width
    subseparator = "-" * term_width

    # Phase header
    print(separator)
    print(f"PHASE: {phase_class.name} ({phase_num} of {total_phases})")
    print(separator)
    print()

    # DESCRIPTION
    print("DESCRIPTION")
    description = (
        phase_class.__doc__.strip() if phase_class.__doc__ else "No description available."
    )
    print(f"    {description}")
    print()

    # CLAUDE MODE (only if set)
    if phase_class.claude_mode:
        print("CLAUDE MODE")
        mode_desc = (
            "plan (read-only)" if phase_class.claude_mode == "plan" else phase_class.claude_mode
        )
        print(f"    {mode_desc}")
        print()

    # CONTEXT (only if fresh_context is True)
    if phase_class.fresh_context:
        print("CONTEXT")
        print("    fresh_context: Yes (starts new Claude session for unbiased analysis)")
        print()

    # TOOLS AVAILABLE (only if allowed_tools is set)
    if phase_class.allowed_tools:
        print("TOOLS AVAILABLE")
        print(f"    {', '.join(phase_class.allowed_tools)}")
        print()

    # TIMING
    print("TIMING")
    timeout = phase_class.timeout_seconds
    if timeout >= 60:
        minutes = timeout // 60
        seconds = timeout % 60
        if seconds:
            timeout_str = f"{timeout} seconds ({minutes} minutes {seconds} seconds)"
        else:
            timeout_str = f"{timeout} seconds ({minutes} minutes)"
    else:
        timeout_str = f"{timeout} seconds"
    print(f"    Timeout:    {timeout_str}")
    print(f"    Max turns:  {phase_class.max_turns}")
    print()

    # APPROVAL GATE
    print("APPROVAL GATE")
    if phase_class.approval_gate:
        print("    Yes (requires approval before proceeding)")
    else:
        print("    No")
    print()

    # CONFIGURATION
    print("CONFIGURATION")
    print("    phases:")
    print(f"      {phase_class.name}:")
    print(f"        timeout: {phase_class.timeout_seconds}")
    print(f"        max_turns: {phase_class.max_turns}")
    print("        enabled: true")
    print()

    print(subseparator)


def handle_help_phases(phase_names: list[str] | None) -> int:
    """Show detailed help for workflow phases.

    Args:
        phase_names: Optional list of phase names to show. If None or empty, shows all phases.

    Returns:
        0 on success, 1 on invalid phase name.
    """
    from selfassembler.phases import PHASE_CLASSES, PHASE_NAMES

    term_width = shutil.get_terminal_size().columns
    separator = "=" * term_width

    # If specific phases requested, validate them
    if phase_names:
        invalid_phases = [p for p in phase_names if p not in PHASE_NAMES]
        if invalid_phases:
            print(f"Error: Unknown phase(s): {', '.join(invalid_phases)}", file=sys.stderr)
            print(f"\nValid phases: {', '.join(PHASE_NAMES)}", file=sys.stderr)
            return 1

        # Filter to requested phases
        phases_to_show = [cls for cls in PHASE_CLASSES if cls.name in phase_names]
    else:
        phases_to_show = PHASE_CLASSES

    # Print header
    print()
    print(separator)
    title = "SELFASSEMBLER WORKFLOW PHASES"
    padding = (term_width - len(title)) // 2
    print(" " * padding + title)
    print(separator)
    print()

    # Print each phase
    total_phases = len(PHASE_CLASSES)
    for phase_class in phases_to_show:
        phase_num = PHASE_CLASSES.index(phase_class) + 1
        _print_phase_help(phase_class, phase_num, total_phases)
        print()

    return 0


def handle_dry_run(config: WorkflowConfig, skip_to: str | None = None) -> int:
    """Display phases that would run without executing them.

    Shows phase name, approval gate status, estimated cost, and running total.
    Respects --skip-to and disabled phases configuration.
    """
    from selfassembler.phases import PHASE_CLASSES, PHASE_NAMES

    # Determine start index based on skip_to
    start_index = 0
    if skip_to:
        try:
            start_index = PHASE_NAMES.index(skip_to)
        except ValueError:
            print(f"Unknown phase: {skip_to}", file=sys.stderr)
            return 1

    # Collect phases that would run
    phases_to_run: list[dict] = []
    for i, phase_class in enumerate(PHASE_CLASSES):
        # Skip phases before skip_to
        if i < start_index:
            continue

        # Get phase config to check if enabled
        phase_config = config.get_phase_config(phase_class.name)
        if not phase_config.enabled:
            continue

        # Determine effective approval gate status
        # Phase has a gate if approvals are enabled AND either:
        # 1. The phase class has approval_gate=True (default gates like planning), OR
        # 2. The gate is explicitly enabled in config.approvals.gates (e.g., plan_review)
        has_approval_gate = False
        if config.approvals.enabled:
            phase_name_normalized = phase_class.name.replace("-", "_")
            gate_config = getattr(config.approvals.gates, phase_name_normalized, None)
            # Gate is active if explicitly configured True, or if phase has default gate
            if gate_config is True or (phase_class.approval_gate and gate_config is not False):
                has_approval_gate = True

        phases_to_run.append(
            {
                "name": phase_class.name,
                "approval_gate": has_approval_gate,
                "estimated_cost": phase_config.estimated_cost,
            }
        )

    # Handle case where no phases would run
    if not phases_to_run:
        print("No phases would run with the current configuration.")
        return 0

    # Print header
    print("Dry-run: Phases that would execute\n")
    print(f" {'#':>2}  {'Phase':<20} {'Approval Gate':<14} {'Est. Cost':<10} {'Running Total':<12}")
    print("─" * 65)

    # Print each phase
    running_total = 0.0
    for idx, phase in enumerate(phases_to_run, 1):
        running_total += phase["estimated_cost"]
        approval_str = "Yes" if phase["approval_gate"] else "No"
        print(
            f" {idx:>2}  {phase['name']:<20} {approval_str:<14} "
            f"${phase['estimated_cost']:<9.2f} ${running_total:<11.2f}"
        )

    # Print footer
    print("─" * 65)
    print(f"Total estimated cost: ${running_total:.2f}")
    print(f"Budget limit: ${config.budget_limit_usd:.2f}")

    # Show budget warning if total exceeds budget
    if running_total > config.budget_limit_usd:
        print(
            f"\n⚠ Warning: Estimated cost (${running_total:.2f}) "
            f"exceeds budget limit (${config.budget_limit_usd:.2f})"
        )

    return 0


def handle_init_config(path: Path | None = None) -> int:
    """Create a default configuration file."""
    config = WorkflowConfig()
    config_path = path or Path("selfassembler.yaml")

    if config_path.exists():
        print(f"Configuration file already exists: {config_path}")
        response = input("Overwrite? [y/N] ")
        if response.lower() != "y":
            return 1

    config.save(config_path)
    print(f"Created configuration file: {config_path}")
    return 0


def handle_approve(phase: str, plans_dir: Path) -> int:
    """Grant approval for a phase."""
    from selfassembler.state import ApprovalStore

    store = ApprovalStore(plans_dir)
    store.grant_approval(phase)
    print(f"Granted approval for phase: {phase}")
    return 0


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    parsed = parser.parse_args(args)

    # Handle utility commands
    if parsed.list_checkpoints:
        return handle_list_checkpoints()

    if parsed.list_phases:
        return handle_list_phases()

    if parsed.help_phases is not None:
        return handle_help_phases(parsed.help_phases if parsed.help_phases else None)

    if parsed.init_config:
        return handle_init_config(parsed.config)

    # Load configuration
    config = WorkflowConfig.load(parsed.config)

    # Apply CLI overrides
    if parsed.autonomous:
        config.autonomous_mode = True
        config.approvals.enabled = False
        config.agent.dangerous_mode = True
        config.claude.dangerous_mode = True  # Legacy compatibility
    elif parsed.no_approvals:
        config.approvals.enabled = False

    if parsed.budget:
        config.budget_limit_usd = parsed.budget

    # Apply streaming options
    if parsed.no_stream:
        config.streaming.enabled = False
    if parsed.debug:
        config.streaming.debug = parsed.debug

    # Apply plan review options
    if parsed.review_plan_approval:
        config.approvals.gates.plan_review = True
    if parsed.skip_plan_review:
        config.phases.plan_review.enabled = False

    if parsed.plans_dir:
        config.plans_dir = str(parsed.plans_dir)

    # Apply debate mode (auto-detect if not specified)
    # This must happen before agent selection to allow auto-detect to set primary
    from selfassembler.executors import auto_configure_agents, detect_installed_agents

    detected_primary, detected_secondary, detected_debate = auto_configure_agents()
    installed = detect_installed_agents()

    if parsed.no_debate:
        config.debate.enabled = False
    elif parsed.debate:
        config.debate.enabled = True
        # If debate forced but agents not configured, use auto-detected values
        if config.debate.primary_agent == "claude" and config.debate.secondary_agent == "codex":
            # Default values - apply auto-detection
            if detected_debate:
                # Both agents available
                config.debate.primary_agent = detected_primary
                config.debate.secondary_agent = detected_secondary
            else:
                # Only one agent installed - use same-agent debate
                config.debate.primary_agent = detected_primary
                config.debate.secondary_agent = detected_primary  # Same agent
                if not parsed.quiet:
                    print(f"Note: Only {detected_primary} installed, using {detected_primary.title()} vs {detected_primary.title()} debate")
    elif not config.debate.enabled:
        # Auto-configure debate if not already set in config file
        config.debate.enabled = detected_debate
        if detected_debate:
            config.debate.primary_agent = detected_primary
            config.debate.secondary_agent = detected_secondary
            if not parsed.quiet:
                print(f"Auto-detected: Both {detected_primary} and {detected_secondary} installed, enabling debate mode")

    # Apply agent selection
    if parsed.agent:
        # User explicitly specified agent - use it as primary
        config.agent.type = parsed.agent
        if config.debate.enabled:
            # Align debate primary with explicit agent choice
            config.debate.primary_agent = parsed.agent
            # Set secondary to the other available agent, or same agent if other not available
            if parsed.agent == "claude":
                if installed.get("codex"):
                    config.debate.secondary_agent = "codex"
                else:
                    config.debate.secondary_agent = "claude"  # Same-agent debate
                    if not parsed.quiet:
                        print(f"Note: Codex not installed, using Claude vs Claude debate")
            elif parsed.agent == "codex":
                if installed.get("claude"):
                    config.debate.secondary_agent = "claude"
                else:
                    config.debate.secondary_agent = "codex"  # Same-agent debate
                    if not parsed.quiet:
                        print(f"Note: Claude not installed, using Codex vs Codex debate")
    else:
        # No explicit agent - respect config file if set, otherwise use auto-detected
        # Only override if config has default value and auto-detection found something different
        if config.agent.type == "claude" and detected_primary != "claude":
            # Config has default, but auto-detection found only codex
            config.agent.type = detected_primary
        elif not installed.get(config.agent.type):
            # Config's agent isn't installed, fall back to detected
            config.agent.type = detected_primary
            if not parsed.quiet:
                print(f"Note: Configured agent not installed, using {detected_primary}")

    # Determine plans directory
    plans_dir = Path(config.plans_dir)
    if not plans_dir.is_absolute():
        plans_dir = parsed.repo / plans_dir

    # Handle approval
    if parsed.approve:
        return handle_approve(parsed.approve, plans_dir)

    # Handle dry-run
    if parsed.dry_run:
        return handle_dry_run(config, parsed.skip_to)

    # Handle resume
    if parsed.resume:
        try:
            orchestrator = Orchestrator.from_checkpoint(parsed.resume, config)

            # Apply CLI overrides on top of snapshot config
            if parsed.budget:
                orchestrator.config.budget_limit_usd = parsed.budget
            if parsed.no_approvals or parsed.autonomous:
                orchestrator.config.approvals.enabled = False
            if parsed.autonomous:
                orchestrator.config.autonomous_mode = True
                orchestrator.config.agent.dangerous_mode = True
                orchestrator.config.claude.dangerous_mode = True
            if parsed.no_stream:
                orchestrator.config.streaming.enabled = False
            if parsed.debug:
                orchestrator.config.streaming.debug = parsed.debug

            print(f"Resuming from checkpoint: {parsed.resume}")
            print(f"Task: {orchestrator.context.task_name}")
            print(f"Last phase: {orchestrator.context.current_phase}")

            # Mark phases as persistently complete (--skip-phases)
            if parsed.skip_phases:
                for phase in parsed.skip_phases.split(","):
                    phase = phase.strip()
                    if phase in PHASE_NAMES:
                        orchestrator.context.mark_phase_complete(phase)
                        print(f"Skipping phase: {phase}")
                    else:
                        print(f"Warning: Unknown phase '{phase}', ignoring", file=sys.stderr)

            print()

            # --skip-to with --resume: mark all phases before target as complete
            if parsed.skip_to:
                skip_idx = PHASE_NAMES.index(parsed.skip_to)
                for phase_name in PHASE_NAMES[:skip_idx]:
                    orchestrator.context.mark_phase_complete(phase_name)
                orchestrator.run_workflow(skip_to=parsed.skip_to)
            else:
                orchestrator.resume_workflow()

            return 0

        except SelfAssemblerError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Validate required arguments for new workflow
    if not parsed.task:
        parser.print_help()
        return 1

    # Handle plan file reference
    task_description = parsed.task
    if task_description.startswith("@"):
        plan_path = Path(task_description[1:])
        if not plan_path.exists():
            print(f"Plan file not found: {plan_path}", file=sys.stderr)
            return 1
        task_description = f"Implement according to plan: {plan_path}"

    # Generate task name if not provided
    task_name = parsed.task_name or generate_task_name(task_description)

    # Create and run orchestrator
    try:
        orchestrator = create_orchestrator(
            task_description=task_description,
            task_name=task_name,
            repo_path=parsed.repo,
            config=config,
        )

        if not parsed.quiet:
            print(f"Starting workflow: {task_name}")
            print(f"Task: {task_description}")
            print(f"Budget: ${config.budget_limit_usd:.2f}")
            print()

        if parsed.skip_to:
            orchestrator.run_workflow(skip_to=parsed.skip_to)
        else:
            orchestrator.run_workflow()

        return 0

    except ContainerRequiredError:
        return 1

    except BudgetExceededError as e:
        print(f"\nBudget exceeded: {e}", file=sys.stderr)
        print(
            f"Resume with: selfassembler --resume {orchestrator.context.checkpoint_id}",
            file=sys.stderr,
        )
        return 1

    except ApprovalTimeoutError as e:
        print(f"\nApproval timeout: {e}", file=sys.stderr)
        print(
            f"Grant approval: selfassembler --approve {e.phase} --plans-dir {plans_dir}",
            file=sys.stderr,
        )
        print(
            f"Then resume: selfassembler --resume {orchestrator.context.checkpoint_id}",
            file=sys.stderr,
        )
        return 1

    except PhaseFailedError as e:
        print(f"\nPhase failed: {e.phase}", file=sys.stderr)
        if e.error:
            print(f"Error: {e.error[:500]}", file=sys.stderr)
        print(
            f"Resume with: selfassembler --resume {orchestrator.context.checkpoint_id}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130

    except SelfAssemblerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if parsed.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
