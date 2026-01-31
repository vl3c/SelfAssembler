"""Command-line interface for SelfAssembler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from selfassembler import __version__
from selfassembler.config import WorkflowConfig
from selfassembler.errors import (
    ApprovalTimeoutError,
    BudgetExceededError,
    SelfAssemblerError,
    ContainerRequiredError,
    PhaseFailedError,
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

    if parsed.init_config:
        return handle_init_config(parsed.config)

    # Load configuration
    config = WorkflowConfig.load(parsed.config)

    # Apply CLI overrides
    if parsed.autonomous:
        config.autonomous_mode = True
        config.approvals.enabled = False
        config.claude.dangerous_mode = True
    elif parsed.no_approvals:
        config.approvals.enabled = False

    if parsed.budget:
        config.budget_limit_usd = parsed.budget

    if parsed.plans_dir:
        config.plans_dir = str(parsed.plans_dir)

    # Determine plans directory
    plans_dir = Path(config.plans_dir)
    if not plans_dir.is_absolute():
        plans_dir = parsed.repo / plans_dir

    # Handle approval
    if parsed.approve:
        return handle_approve(parsed.approve, plans_dir)

    # Handle resume
    if parsed.resume:
        try:
            orchestrator = Orchestrator.from_checkpoint(parsed.resume, config)
            print(f"Resuming from checkpoint: {parsed.resume}")
            print(f"Task: {orchestrator.context.task_name}")
            print(f"Last phase: {orchestrator.context.current_phase}")
            print()

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
