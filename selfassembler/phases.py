"""Workflow phases for SelfAssembler."""

from __future__ import annotations

import contextlib
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selfassembler.commands import get_command, parse_test_output, run_command
from selfassembler.errors import PreflightFailedError
from selfassembler.git import GitManager, copy_config_files

if TYPE_CHECKING:
    from selfassembler.config import WorkflowConfig
    from selfassembler.context import WorkflowContext
    from selfassembler.executor import ClaudeExecutor


@dataclass
class PhaseResult:
    """Result from executing a phase."""

    success: bool
    cost_usd: float = 0.0
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False
    session_id: str | None = None


class Phase(ABC):
    """
    Base class for workflow phases.

    Each phase represents a distinct step in the workflow.
    Phases can use Claude CLI, run commands, or perform other operations.
    """

    name: str = "base"
    timeout_seconds: int = 600
    approval_gate: bool = False
    claude_mode: str | None = None  # "plan" for read-only
    allowed_tools: list[str] | None = None
    max_turns: int = 50
    fresh_context: bool = False  # True = new session (unbiased)

    def __init__(
        self,
        context: WorkflowContext,
        executor: ClaudeExecutor,
        config: WorkflowConfig,
    ):
        self.context = context
        self.executor = executor
        self.config = config

    @abstractmethod
    def run(self) -> PhaseResult:
        """Execute the phase and return a result."""
        pass

    def validate_preconditions(self) -> tuple[bool, str]:
        """Validate that preconditions for this phase are met."""
        return True, ""

    def get_phase_config(self) -> Any:
        """Get the configuration for this phase."""
        return self.config.get_phase_config(self.name)

    def _dangerous_mode(self) -> bool:
        """Return whether to skip permissions in autonomous mode."""
        return self.config.autonomous_mode and self.config.claude.dangerous_mode


class PreflightPhase(Phase):
    """Validate environment before starting workflow."""

    name = "preflight"
    timeout_seconds = 60

    def run(self) -> PhaseResult:
        checks = [
            self._check_claude_cli(),
            self._check_gh_cli(),
            self._check_git_clean(),
            self._check_git_updated(),
        ]

        failed = [c for c in checks if not c["passed"]]
        if failed:
            error = PreflightFailedError(failed)
            return PhaseResult(success=False, error=str(error))

        return PhaseResult(success=True, artifacts={"checks": checks})

    def _check_claude_cli(self) -> dict[str, Any]:
        """Check if Claude CLI is installed."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {"name": "claude_cli", "passed": True, "version": result.stdout.strip()}
            return {
                "name": "claude_cli",
                "passed": False,
                "message": "Claude CLI not working. Run: npm install -g @anthropic-ai/claude-code",
            }
        except FileNotFoundError:
            return {
                "name": "claude_cli",
                "passed": False,
                "message": "Claude CLI not installed. Run: npm install -g @anthropic-ai/claude-code",
            }
        except Exception as e:
            return {"name": "claude_cli", "passed": False, "message": str(e)}

    def _check_gh_cli(self) -> dict[str, Any]:
        """Check if GitHub CLI is authenticated and configure git credentials."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Configure git to use gh as credential helper
                subprocess.run(
                    ["gh", "auth", "setup-git"],
                    capture_output=True,
                    timeout=10,
                )
                return {"name": "gh_cli", "passed": True}
            return {
                "name": "gh_cli",
                "passed": False,
                "message": "GitHub CLI not authenticated. Run: gh auth login",
            }
        except FileNotFoundError:
            return {
                "name": "gh_cli",
                "passed": False,
                "message": "GitHub CLI not installed. See: https://cli.github.com/",
            }
        except Exception as e:
            return {"name": "gh_cli", "passed": False, "message": str(e)}

    def _check_git_clean(self) -> dict[str, Any]:
        """Check if git working directory is clean."""
        try:
            git = GitManager(self.context.repo_path)
            is_clean, output = git.is_clean()
            if is_clean:
                return {"name": "git_clean", "passed": True}
            return {
                "name": "git_clean",
                "passed": False,
                "message": f"Git working directory not clean:\n{output}",
            }
        except Exception as e:
            return {"name": "git_clean", "passed": False, "message": str(e)}

    def _check_git_updated(self) -> dict[str, Any]:
        """Check if local branch is up to date with remote."""
        try:
            git = GitManager(self.context.repo_path)
            base_branch = self.config.git.base_branch
            behind = git.commits_behind(base_branch)
            if behind == 0:
                return {"name": "git_updated", "passed": True}
            return {
                "name": "git_updated",
                "passed": False,
                "message": f"Local branch is {behind} commits behind origin/{base_branch}. Run: git pull",
            }
        except Exception as e:
            return {"name": "git_updated", "passed": False, "message": str(e)}


class SetupPhase(Phase):
    """Create isolated workspace via git worktree."""

    name = "setup"
    timeout_seconds = 120

    def run(self) -> PhaseResult:
        try:
            git = GitManager(self.context.repo_path)

            # Generate branch name
            branch_name = git.generate_branch_name(
                self.context.task_name,
                prefix=self.config.git.branch_prefix,
            )

            # Create worktree
            worktree_dir = Path(self.config.git.worktree_dir)
            if not worktree_dir.is_absolute():
                # Resolve relative path from repo_path
                worktree_dir = (self.context.repo_path / worktree_dir).resolve()

            worktree_path = git.create_worktree(
                branch_name=branch_name,
                worktree_dir=worktree_dir,
                base_branch=self.config.git.base_branch,
            )

            # Copy config files
            copied = copy_config_files(
                source_dir=self.context.repo_path,
                dest_dir=worktree_path,
                patterns=self.config.copy_files,
            )

            # Update context
            self.context.worktree_path = worktree_path
            self.context.branch_name = branch_name

            return PhaseResult(
                success=True,
                artifacts={
                    "worktree_path": str(worktree_path),
                    "branch_name": branch_name,
                    "copied_files": [str(f) for f in copied],
                },
            )
        except Exception as e:
            return PhaseResult(success=False, error=str(e))


class ResearchPhase(Phase):
    """Gather context before planning."""

    name = "research"
    claude_mode = "plan"  # Read-only
    allowed_tools = ["Read", "Grep", "Glob", "LS", "WebSearch"]
    max_turns = 25
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        research_file = self.context.plans_dir / f"research-{self.context.task_name}.md"
        self.context.plans_dir.mkdir(parents=True, exist_ok=True)

        prompt = f"""
Research task: {self.context.task_description}

1. Read project conventions:
   - Look for: claude.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, .claude/*
   - Understand coding standards, patterns, and constraints

2. Find related code:
   - Search for files related to this feature
   - Understand existing patterns and conventions
   - Note reusable utilities or components

3. Identify dependencies:
   - External packages needed
   - Internal modules to import
   - API contracts to follow

Write your findings to: {research_file}

Format the research as markdown with clear sections.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            permission_mode=self.claude_mode,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            artifacts={"research_file": str(research_file)},
            session_id=result.session_id,
        )


class PlanningPhase(Phase):
    """Create detailed implementation plan."""

    name = "planning"
    claude_mode = "plan"
    fresh_context = True  # Fresh eyes to avoid research biases in plan structure
    allowed_tools = ["Read", "Grep", "Glob", "Write"]
    max_turns = 20
    timeout_seconds = 600
    approval_gate = True  # Configurable via config

    def run(self) -> PhaseResult:
        plan_file = self.context.plans_dir / f"plan-{self.context.task_name}.md"
        research_file = self.context.plans_dir / f"research-{self.context.task_name}.md"

        research_ref = ""
        if research_file.exists():
            research_ref = f"\nReference the research at: {research_file}\n"

        prompt = f"""
Create a detailed implementation plan for: {self.context.task_description}
{research_ref}
Write the plan to: {plan_file}

Plan format:
```markdown
# Implementation Plan: {self.context.task_name}

## Summary
[1-2 sentence overview of what will be implemented]

## Files to Modify/Create
- [ ] path/to/file.ext - [brief description of changes]

## Implementation Steps
### Step 1: [Name]
- Description: What this step accomplishes
- Files involved: ...
- Acceptance criteria: How to verify this step is complete

### Step 2: ...

## Testing Strategy
- [ ] Unit tests for...
- [ ] Integration tests for...

## Risks/Blockers
- Any potential issues or dependencies
```
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            permission_mode=self.claude_mode,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            artifacts={"plan_file": str(plan_file)},
            session_id=result.session_id,
        )


class PlanReviewPhase(Phase):
    """Review and improve the implementation plan with SWOT analysis."""

    name = "plan_review"
    claude_mode = "plan"
    fresh_context = True  # Critical: unbiased review
    allowed_tools = ["Read", "Grep", "Glob", "Write"]
    max_turns = 30
    timeout_seconds = 600
    approval_gate = False  # Configurable via --review-plan-approval

    def run(self) -> PhaseResult:
        plan_file = self.context.plans_dir / f"plan-{self.context.task_name}.md"
        review_file = self.context.plans_dir / f"plan-review-{self.context.task_name}.md"

        if not plan_file.exists():
            return PhaseResult(
                success=True,
                artifacts={"skipped": "No plan file found"},
            )

        prompt = f"""
Review and improve the implementation plan for: {self.context.task_description}

1. Read the plan at: {plan_file}

2. Perform a SWOT analysis of the plan:
   - Strengths: What's well-planned and will likely succeed?
   - Weaknesses: What's missing, unclear, or poorly planned?
   - Opportunities: What could be improved or added?
   - Threats: What could go wrong? What are the risks?

3. Write your review to: {review_file}

Format:
```markdown
# Plan Review: {self.context.task_name}

## SWOT Analysis

### Strengths
- [What's well-planned]

### Weaknesses
- [What's missing or unclear]

### Opportunities
- [Improvements to consider]

### Threats
- [Risks and potential issues]

## Recommended Changes
- [Specific improvements to make]

## Verdict
[Overall assessment: Ready/Needs Revision/Major Concerns]
```

4. After writing the review, update the original plan at {plan_file}:
   - Add a "## Revisions" section at the end
   - Incorporate the recommended changes
   - Address any weaknesses identified
   - Note any risks that should be monitored

Be thorough but constructive. The goal is to improve the plan, not block it.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            permission_mode=self.claude_mode,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            artifacts={
                "review_file": str(review_file),
                "plan_file": str(plan_file),
            },
            session_id=result.session_id,
        )


class ImplementationPhase(Phase):
    """Implement the planned changes."""

    name = "implementation"
    allowed_tools = ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
    max_turns = 100
    timeout_seconds = 3600

    def run(self) -> PhaseResult:
        plan_file = self.context.plans_dir / f"plan-{self.context.task_name}.md"

        plan_ref = ""
        if plan_file.exists():
            plan_ref = f"\nFollow the implementation plan at: {plan_file}\n"

        prompt = f"""
Implement the following task: {self.context.task_description}
{plan_ref}
Guidelines:
1. Follow the plan step by step
2. Write clean, well-documented code
3. Follow existing code conventions
4. Do NOT write tests yet (separate phase)
5. Do NOT commit changes (separate phase)

Mark completed items in the plan file as you progress.
"""
        phase_config = self.get_phase_config()
        dangerous_mode = self._dangerous_mode()

        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            session_id=result.session_id,
        )


class TestWritingPhase(Phase):
    """Write tests for the implementation."""

    name = "test_writing"
    allowed_tools = ["Read", "Write", "Edit", "Grep", "Glob"]
    max_turns = 50
    timeout_seconds = 1200

    def run(self) -> PhaseResult:
        plan_file = self.context.plans_dir / f"plan-{self.context.task_name}.md"

        prompt = f"""
Write comprehensive tests for the implementation of: {self.context.task_description}

1. Read the implementation files
2. Read the testing strategy from: {plan_file}
3. Write tests following project conventions:
   - Look at existing test files for patterns
   - Use the project's test framework
   - Test edge cases and error conditions

4. Include:
   - Unit tests for individual functions/methods
   - Integration tests if applicable
   - Test for error handling

Do NOT run the tests yet (separate phase).
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            session_id=result.session_id,
        )


class TestExecutionPhase(Phase):
    """Run tests with fix-and-retry loop."""

    name = "test_execution"
    allowed_tools = ["Read", "Edit", "Grep", "Glob", "Bash"]
    max_turns = 60
    timeout_seconds = 1800

    def run(self) -> PhaseResult:
        phase_config = self.get_phase_config()
        max_iterations = phase_config.max_iterations

        # Get test command
        test_cmd = get_command(
            self.context.get_working_dir(),
            "test",
            self.config.commands.test,
        )

        if not test_cmd:
            # Let Claude detect and run tests
            return self._run_with_claude_detection()

        for iteration in range(max_iterations):
            # Run tests
            success, stdout, stderr = run_command(
                self.context.get_working_dir(),
                test_cmd,
                timeout=300,
            )

            test_result = parse_test_output(stdout + stderr)

            if test_result["all_passed"] or success:
                return PhaseResult(
                    success=True,
                    cost_usd=self.context.phase_costs.get(self.name, 0.0),
                    artifacts={
                        "iterations": iteration + 1,
                        "test_results": test_result,
                    },
                )

            # Fix failures (except on last iteration)
            if iteration < max_iterations - 1:
                fix_result = self._fix_failures(stdout + stderr, test_result)
                if not fix_result.get("changes_made"):
                    return PhaseResult(
                        success=False,
                        cost_usd=self.context.phase_costs.get(self.name, 0.0),
                        error="Unable to fix test failures",
                        artifacts={"test_results": test_result, "output": stdout + stderr},
                    )

        return PhaseResult(
            success=False,
            cost_usd=self.context.phase_costs.get(self.name, 0.0),
            error=f"Tests still failing after {max_iterations} iterations",
            artifacts={"test_results": test_result, "output": stdout + stderr},
        )

    def _run_with_claude_detection(self) -> PhaseResult:
        """Let Claude detect and run tests."""
        prompt = """
Detect and run the project's tests:

1. Find the test configuration (package.json scripts, pytest.ini, etc.)
2. Run the appropriate test command
3. If tests fail, analyze failures and fix them
4. Re-run tests until they pass (max 5 iterations)

Report the final test results.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )

    def _fix_failures(self, output: str, test_result: dict[str, Any]) -> dict[str, Any]:
        """Use Claude to fix test failures."""
        failures_summary = "\n".join(test_result.get("failures", [])[:10])

        prompt = f"""
Tests failed. Analyze and fix the failures:

Test output:
{output[:3000]}

Failures detected:
{failures_summary}

Steps:
1. Read the failing test code
2. Read the implementation being tested
3. Determine if the bug is in the test or implementation
4. Fix the bug

Do NOT run tests yet (I will run them after your fixes).
"""
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=["Read", "Edit", "Grep"],
            max_turns=15,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        return {"changes_made": not result.is_error}


class CodeReviewPhase(Phase):
    """Review implementation with fresh context."""

    name = "code_review"
    claude_mode = "plan"  # Read-only
    fresh_context = True  # Critical: unbiased review
    allowed_tools = ["Read", "Grep", "Glob", "Bash"]
    max_turns = 30
    timeout_seconds = 600

    def run(self) -> PhaseResult:
        review_file = self.context.plans_dir / f"review-{self.context.task_name}.md"

        prompt = f"""
Review the implementation for: {self.context.task_description}

1. Get the diff: git diff {self.config.git.base_branch}...HEAD

2. Review for:
   - Logic errors or bugs
   - Security issues (injection, XSS, CSRF, etc.)
   - Performance problems
   - Missing edge cases
   - Code style violations
   - Incomplete implementations
   - TODOs or debug code left in
   - Hardcoded values that should be configurable
   - Missing error handling

3. Write your review findings to: {review_file}

Format:
```markdown
# Code Review: {self.context.task_name}

## Summary
[Overall assessment]

## Issues Found

### Critical
- [Issue description with file:line reference]

### Major
- [Issue description]

### Minor
- [Issue description]

## Suggestions
- [Optional improvements]
```

If no issues found, note that the code looks good.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            permission_mode=self.claude_mode,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        self.context.set_session_id(self.name, result.session_id)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
            artifacts={"review_file": str(review_file)},
            session_id=result.session_id,
        )


class FixReviewIssuesPhase(Phase):
    """Fix issues found in code review."""

    name = "fix_review_issues"
    allowed_tools = ["Read", "Write", "Edit", "Grep"]
    max_turns = 40
    timeout_seconds = 900

    def run(self) -> PhaseResult:
        review_file = self.context.plans_dir / f"review-{self.context.task_name}.md"

        if not review_file.exists():
            return PhaseResult(
                success=True,
                artifacts={"skipped": "No review file found"},
            )

        prompt = f"""
Fix the issues found in the code review.

1. Read the review at: {review_file}
2. Address all Critical and Major issues
3. Consider addressing Minor issues if straightforward
4. Update the review file to mark issues as resolved

Focus on fixing actual bugs and security issues first.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )


class LintCheckPhase(Phase):
    """Run linting and type checking."""

    name = "lint_check"
    fresh_context = True  # Fresh eyes for mechanical fixes without prior assumptions
    allowed_tools = ["Bash", "Read", "Edit"]
    max_turns = 20
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        workdir = self.context.get_working_dir()
        results = []
        phase_config = self.config.get_phase_config(self.name)
        max_iterations = phase_config.max_iterations

        # Try configured or detected commands
        lint_cmd = get_command(workdir, "lint", self.config.commands.lint)
        typecheck_cmd = get_command(workdir, "typecheck", self.config.commands.typecheck)
        format_cmd = get_command(workdir, "format")

        # If no commands found, let Claude handle it
        if not lint_cmd and not typecheck_cmd:
            return self._claude_detect_and_lint()

        # Run format first if available (no retry needed)
        if format_cmd:
            success, stdout, stderr = run_command(workdir, format_cmd, timeout=120)
            results.append({"command": "format", "success": success, "output": stdout + stderr})

        # Run lint with iterative fix loop
        lint_success = True
        if lint_cmd:
            for iteration in range(max_iterations):
                success, stdout, stderr = run_command(workdir, lint_cmd, timeout=120)
                output = stdout + stderr
                results.append(
                    {
                        "command": f"lint_iter_{iteration + 1}",
                        "success": success,
                        "output": output,
                    }
                )

                if success:
                    lint_success = True
                    break

                # Try to fix lint issues with Claude
                if iteration < max_iterations - 1:
                    fix_result = self._fix_lint_issues(output)
                    if not fix_result:
                        # Claude couldn't fix, no point retrying
                        lint_success = False
                        break
                else:
                    lint_success = False

        # Run typecheck with iterative fix loop
        typecheck_success = True
        if typecheck_cmd:
            for iteration in range(max_iterations):
                success, stdout, stderr = run_command(workdir, typecheck_cmd, timeout=180)
                output = stdout + stderr
                results.append(
                    {
                        "command": f"typecheck_iter_{iteration + 1}",
                        "success": success,
                        "output": output,
                    }
                )

                if success:
                    typecheck_success = True
                    break

                # Try to fix type issues with Claude
                if iteration < max_iterations - 1:
                    fix_result = self._fix_type_issues(output)
                    if not fix_result:
                        # Claude couldn't fix, no point retrying
                        typecheck_success = False
                        break
                else:
                    typecheck_success = False

        # Check overall success
        if not lint_success or not typecheck_success:
            failed = [r for r in results if not r["success"]]
            error_msg = "\n".join(f"{r['command']}: {r['output'][:500]}" for r in failed[-2:])
            return PhaseResult(
                success=False,
                error=f"Lint/typecheck still failing after {max_iterations} iterations:\n{error_msg}",
                artifacts={"results": results},
            )

        return PhaseResult(success=True, artifacts={"results": results})

    def _fix_lint_issues(self, output: str) -> bool:
        """Use Claude to fix lint issues."""
        prompt = f"""
Fix the linting errors:

{output[:2000]}

Make the minimal changes needed to fix the lint errors.
"""
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=["Read", "Edit"],
            max_turns=10,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )
        self.context.add_cost(self.name, result.cost_usd)
        return not result.is_error

    def _fix_type_issues(self, output: str) -> bool:
        """Use Claude to fix type checking issues."""
        prompt = f"""
Fix the type checking errors:

{output[:2000]}

Make the minimal changes needed to fix the type errors.
Add type annotations, fix type mismatches, or add type: ignore comments where appropriate.
"""
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=["Read", "Edit"],
            max_turns=10,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )
        self.context.add_cost(self.name, result.cost_usd)
        return not result.is_error

    def _claude_detect_and_lint(self) -> PhaseResult:
        """Let Claude detect and run linting."""
        prompt = """
Detect project type and run appropriate linting/formatting:

- package.json → npm run lint, eslint, prettier
- pyproject.toml → ruff check --fix, mypy
- Cargo.toml → cargo clippy, cargo fmt
- go.mod → golangci-lint run, go fmt

Run with --fix flags where available. Report any unfixable issues.
"""
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=["Bash", "Read"],
            max_turns=10,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )
        self.context.add_cost(self.name, result.cost_usd)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )


class DocumentationPhase(Phase):
    """Update documentation for the changes."""

    name = "documentation"
    allowed_tools = ["Read", "Write", "Edit", "Grep", "Glob"]
    max_turns = 30
    timeout_seconds = 600

    def run(self) -> PhaseResult:
        plan_path = self.context.plans_dir / f"plan-{self.context.task_name}.md"
        prompt = f"""
Update documentation for: {self.context.task_description}

## First, gather context by reviewing:

1. **Modified files**: Run `git diff --name-only` to see what changed
2. **Recent commits**: Run `git log --oneline -10` to understand the changes
3. **The implementation plan**: Read {plan_path} if it exists
4. **Existing documentation**: Check README.md, docs/ directory, CONTRIBUTING.md

## Then, update documentation as needed:

1. **README.md**: Update if new features, config options, or usage patterns were added
2. **docs/ files**: Update relevant guides or API documentation
3. **Code comments**: Ensure complex logic has adequate inline comments
4. **CHANGELOG.md**: If it exists, add entry to Unreleased section
5. **Configuration examples**: Update example configs if new options were added

## Guidelines:

- Only make documentation changes that are necessary
- Do NOT create new documentation files unless clearly needed
- Match the existing documentation style and format
- Keep changes focused on what was actually implemented
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )


class FinalVerificationPhase(Phase):
    """Final verification that everything works."""

    name = "final_verification"
    allowed_tools = ["Bash", "Read", "Grep"]
    max_turns = 15
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        workdir = self.context.get_working_dir()

        # Run tests one more time
        test_cmd = get_command(workdir, "test", self.config.commands.test)
        if test_cmd:
            success, stdout, stderr = run_command(workdir, test_cmd, timeout=300)
            if not success:
                return PhaseResult(
                    success=False,
                    error=f"Final test verification failed:\n{stdout}\n{stderr}",
                )

        # Run build if available
        build_cmd = get_command(workdir, "build", self.config.commands.build)
        if build_cmd:
            success, stdout, stderr = run_command(workdir, build_cmd, timeout=300)
            if not success:
                return PhaseResult(
                    success=False,
                    error=f"Build verification failed:\n{stdout}\n{stderr}",
                )

        return PhaseResult(
            success=True,
            artifacts={"test_passed": True, "build_passed": build_cmd is not None},
        )


class CommitPrepPhase(Phase):
    """Prepare and create the commit."""

    name = "commit_prep"
    allowed_tools = ["Bash", "Read"]
    max_turns = 10
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        workdir = self.context.get_working_dir()

        prompt = f"""
Prepare and create a commit for: {self.context.task_description}

1. Run `git status` to see changes
2. Run `git diff --cached` to review staged changes (if any)
3. Stage all relevant changes (avoid .env files or secrets)
4. Create a commit with a descriptive message following conventional commits

Commit message format:
```
<type>(<scope>): <description>

<body explaining what and why>

Co-Authored-By: Claude <noreply@anthropic.com>
```

Types: feat, fix, docs, style, refactor, test, chore
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=workdir,
        )

        self.context.add_cost(self.name, result.cost_usd)

        # Get commit hash
        try:
            git = GitManager(workdir)
            log = git.get_log(count=1, format_str="%H %s", cwd=workdir)
            if log:
                commit_hash = log[0].split()[0]
                return PhaseResult(
                    success=not result.is_error,
                    cost_usd=result.cost_usd,
                    artifacts={"commit_hash": commit_hash},
                )
        except Exception:
            pass

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )


class ConflictCheckPhase(Phase):
    """Check for merge conflicts with main."""

    name = "conflict_check"
    allowed_tools = ["Read", "Edit", "Bash"]
    max_turns = 20
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        workdir = self.context.get_working_dir()
        git = GitManager(workdir)
        base_branch = self.config.git.base_branch

        try:
            # Fetch latest (no-op if no remote)
            git.fetch()

            # Determine rebase target - use origin if available, otherwise local branch
            if git.has_remote():
                rebase_target = f"origin/{base_branch}"
            else:
                rebase_target = base_branch

            # Try rebase
            success, conflicts = git.rebase(rebase_target, cwd=workdir)

            if success:
                return PhaseResult(success=True)

            # Conflicts detected - try to resolve with Claude
            git.abort_rebase(cwd=workdir)

            resolve_success = self._resolve_conflicts_with_claude(conflicts)
            if resolve_success:
                return PhaseResult(success=True, artifacts={"conflicts_resolved": conflicts})

            return PhaseResult(
                success=False,
                error=f"Merge conflicts could not be auto-resolved: {', '.join(conflicts)}",
                artifacts={"conflicted_files": conflicts},
            )

        except Exception as e:
            return PhaseResult(success=False, error=str(e))

    def _resolve_conflicts_with_claude(self, conflicts: list[str]) -> bool:
        """Use Claude to resolve merge conflicts."""
        prompt = f"""
Merge conflicts detected during rebase onto origin/{self.config.git.base_branch}.

Conflicted files: {", ".join(conflicts)}

Steps:
1. Run `git status` to see conflicted files
2. For each conflicted file:
   - Read the file to see conflict markers
   - Understand both versions
   - Resolve by editing to remove markers and keep correct code
   - Run `git add <file>` after resolving
3. Run `git rebase --continue` after all conflicts are resolved

If conflicts are too complex to resolve confidently, abort with `git rebase --abort`.
"""
        result = self.executor.execute(
            prompt=prompt,
            allowed_tools=self.allowed_tools,
            max_turns=20,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)
        return not result.is_error


class PRCreationPhase(Phase):
    """Create a pull request."""

    name = "pr_creation"
    allowed_tools = ["Bash", "Read"]
    max_turns = 15
    timeout_seconds = 300

    def run(self) -> PhaseResult:
        workdir = self.context.get_working_dir()
        git = GitManager(workdir)
        branch_name = self.context.branch_name

        if not branch_name:
            return PhaseResult(success=False, error="No branch name set")

        # Skip PR creation for local-only repos
        if not git.has_remote():
            return PhaseResult(
                success=True,
                artifacts={
                    "skipped": "No remote configured - local-only repo",
                    "branch_name": branch_name,
                },
            )

        try:
            # Push branch
            git.push(branch_name, set_upstream=True, cwd=workdir)
            self.context.branch_pushed = True

            # Create PR with Claude
            prompt = f"""
Create a pull request for: {self.context.task_description}

Branch: {branch_name}
Base: {self.config.git.base_branch}

1. Review the changes: `git log {self.config.git.base_branch}..HEAD --oneline`
2. Read the plan file if it exists for context
3. Create the PR using gh CLI:

```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<bullet points of what changed>

## Changes
<list of files and what was modified>

## Testing
<how this was tested>

## Notes
<any additional context>

---
Generated with SelfAssembler
EOF
)"
```

Return the PR URL after creation.
"""
            phase_config = self.get_phase_config()
            result = self.executor.execute(
                prompt=prompt,
                allowed_tools=self.allowed_tools,
                max_turns=phase_config.max_turns,
                timeout=phase_config.timeout,
                dangerous_mode=self._dangerous_mode(),
                working_dir=workdir,
            )

            self.context.add_cost(self.name, result.cost_usd)

            # Try to extract PR URL from output
            pr_url = self._extract_pr_url(result.output)
            if pr_url:
                self.context.pr_url = pr_url
                # Extract PR number
                with contextlib.suppress(ValueError, IndexError):
                    self.context.pr_number = int(pr_url.split("/")[-1])

            return PhaseResult(
                success=not result.is_error,
                cost_usd=result.cost_usd,
                artifacts={"pr_url": pr_url},
                error=result.output if result.is_error else None,
            )

        except Exception as e:
            return PhaseResult(success=False, error=str(e))

    def _extract_pr_url(self, output: str) -> str | None:
        """Extract PR URL from output."""
        # Match GitHub PR URLs
        pattern = r"https://github\.com/[^/]+/[^/]+/pull/\d+"
        match = re.search(pattern, output)
        return match.group(0) if match else None


class PRSelfReviewPhase(Phase):
    """Self-review the PR with fresh context."""

    name = "pr_self_review"
    claude_mode = "plan"
    fresh_context = True  # Unbiased review
    allowed_tools = ["Bash", "Read"]
    max_turns = 20
    timeout_seconds = 600

    def run(self) -> PhaseResult:
        pr_number = self.context.pr_number

        if not pr_number:
            return PhaseResult(
                success=True,
                artifacts={"skipped": "No PR number available"},
            )

        prompt = f"""
Review PR #{pr_number} as a critical code reviewer.

1. Fetch the full diff: `gh pr diff {pr_number}`

2. Review for:
   - Logic errors or bugs
   - Security issues
   - Performance problems
   - Missing edge cases
   - TODOs or debug code left in
   - Secrets or credentials exposed

3. Check PR metadata:
   - Title is descriptive
   - Description explains changes

4. If issues found:
   - Add review comments: `gh pr review {pr_number} --comment --body "..."`

5. If PR looks good:
   - Approve: `gh pr review {pr_number} --approve --body "LGTM - Self-review passed. Ready for human review."`

Be critical but fair. Look for real issues, not style nitpicks.
"""
        phase_config = self.get_phase_config()
        result = self.executor.execute(
            prompt=prompt,
            permission_mode=self.claude_mode,
            allowed_tools=self.allowed_tools,
            max_turns=phase_config.max_turns,
            timeout=phase_config.timeout,
            dangerous_mode=self._dangerous_mode(),
            working_dir=self.context.get_working_dir(),
        )

        self.context.add_cost(self.name, result.cost_usd)

        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
            error=result.output if result.is_error else None,
        )


# Phase registry for the orchestrator
PHASE_CLASSES: list[type[Phase]] = [
    PreflightPhase,
    SetupPhase,
    ResearchPhase,
    PlanningPhase,
    PlanReviewPhase,
    ImplementationPhase,
    TestWritingPhase,
    TestExecutionPhase,
    CodeReviewPhase,
    FixReviewIssuesPhase,
    LintCheckPhase,
    DocumentationPhase,
    FinalVerificationPhase,
    CommitPrepPhase,
    ConflictCheckPhase,
    PRCreationPhase,
    PRSelfReviewPhase,
]

PHASE_NAMES = [cls.name for cls in PHASE_CLASSES]
