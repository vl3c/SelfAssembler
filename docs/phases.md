# Workflow Phases

SelfAssembler executes a 16-phase workflow to automate the complete development lifecycle. This document describes each phase in detail.

> **Tip**: Use `selfassembler --help-phases` to see detailed information about each phase directly in your terminal, including timing, tools available, and configuration examples. You can also specify phases: `selfassembler --help-phases planning implementation`

## Phase Overview

```
PREFLIGHT → SETUP → RESEARCH → PLANNING → [approval] →
IMPLEMENTATION → TEST_WRITING → TEST_EXECUTION (with fix loop) →
CODE_REVIEW → FIX_REVIEW_ISSUES → LINT_CHECK →
DOCUMENTATION → FINAL_VERIFICATION → COMMIT_PREP →
CONFLICT_CHECK → PR_CREATION → PR_SELF_REVIEW → COMPLETE
```

## Phase Details

### 1. Preflight

**Purpose**: Validate the environment before starting work.

**Checks performed**:
- Configured agent CLI is installed and working (Claude or Codex)
- GitHub CLI is authenticated
- Git working directory is clean
- Local branch is up to date with remote

**Auto-update behavior** (when `git.auto_update: true`, the default):
1. Checks out the base branch (e.g., `main`) if not already on it
2. Pulls latest changes from remote
3. Then verifies the branch is up to date

This allows workflows to start even when the local branch is behind the remote, without requiring manual git operations.

**Failure handling**: If any check fails, the workflow stops with a clear error message explaining what needs to be fixed.

**Configuration**:
```yaml
phases:
  preflight:
    timeout: 60
    enabled: true

git:
  auto_update: true  # Set to false to disable auto-pull
```

---

### 2. Setup

**Purpose**: Create an isolated workspace using git worktrees.

**Actions**:
1. Generate a branch name from the task name
2. Create a git worktree with a new branch
3. Copy configuration files (`.env`, `.claude/*`, etc.)

**Artifacts produced**:
- `worktree_path`: Path to the created worktree
- `branch_name`: Name of the new branch

**Configuration**:
```yaml
git:
  branch_prefix: "feature/"
  worktree_dir: "../.worktrees"

copy_files:
  - ".env"
  - ".env.local"
  - ".claude/*"
```

---

### 3. Research

**Purpose**: Gather context about the project before planning.

**Claude mode**: Read-only (`plan` mode)

**Tools available**: Read, Grep, Glob, LS, WebSearch

**Actions**:
1. Read project conventions (CLAUDE.md, CONTRIBUTING.md, etc.)
2. Find related code and existing patterns
3. Identify dependencies and APIs

**Output**: Research findings written to `plans/research-{task_name}.md`

---

### 4. Planning

**Purpose**: Create a detailed implementation plan.

**Claude mode**: Read-only with Write for plan file

**Tools available**: Read, Grep, Glob, Write

**Approval gate**: Yes (by default)

**Actions**:
1. Read research findings
2. Analyze the codebase
3. Create a step-by-step implementation plan

**Output**: Plan written to `plans/plan-{task_name}.md`

**Plan format**:
```markdown
# Implementation Plan: {task_name}

## Summary
Brief overview of changes

## Files to Modify/Create
- [ ] path/to/file.ext - description

## Implementation Steps
### Step 1: Name
- Description
- Acceptance criteria

## Testing Strategy
- Test cases

## Risks/Blockers
- Potential issues
```

---

### 5. Implementation

**Purpose**: Execute the implementation plan.

**Claude mode**: Full access

**Tools available**: Read, Write, Edit, Grep, Glob, Bash

**Actions**:
1. Follow the plan step by step
2. Write code following project conventions
3. Mark completed steps in the plan

**Configuration**:
```yaml
phases:
  implementation:
    timeout: 3600
    max_turns: 100
```

---

### 6. Test Writing

**Purpose**: Write comprehensive tests for the implementation.

**Tools available**: Read, Write, Edit, Grep, Glob

**Actions**:
1. Read the implementation
2. Identify test cases from the plan
3. Write tests following project patterns

---

### 7. Test Execution

**Purpose**: Run tests and fix failures automatically.

**Tools available**: Read, Edit, Grep, Glob, Bash

**Special behavior**: This phase includes an automatic fix-and-retry loop:

1. Run tests
2. If tests fail, analyze failures
3. Fix the failing code (test or implementation)
4. Repeat until tests pass or max iterations reached

**Baseline-diff behavior**: On the first test run, the phase captures a baseline of pre-existing test failures (before any fix attempts). Subsequent test runs diff current failures against this baseline — only **net-new** failures trigger the fix loop or cause a phase failure. Pre-existing failures (e.g. environment-specific tests that fail in Docker) are ignored and reported as warnings.

You can also list known failures in a `.sa-known-failures` file (one test ID per line, `#` comments allowed) which are treated the same as baseline failures.

If the test command exits non-zero but produces no parseable failure IDs (e.g. import errors, collection crashes), the phase fails strictly to avoid silently passing broken runs.

**Configuration**:
```yaml
phases:
  test_execution:
    timeout: 1800
    max_iterations: 5  # Max fix-and-retry loops
    baseline_enabled: true  # Capture and diff against pre-existing test failures
```

---

### 8. Code Review

**Purpose**: Review the implementation with fresh context.

**Claude mode**: Read-only (`plan` mode)

**Fresh context**: Yes (starts new Claude session for unbiased review)

**Tools available**: Read, Grep, Glob, Bash (for git diff)

**Review criteria**:
- Logic errors or bugs
- Security issues (injection, XSS, CSRF)
- Performance problems
- Missing edge cases
- TODOs or debug code
- Hardcoded values

**Output**: Review written to `plans/review-{task_name}.md`

---

### 9. Fix Review Issues

**Purpose**: Address issues found during code review.

**Tools available**: Read, Write, Edit, Grep

**Actions**:
1. Read review findings
2. Fix Critical and Major issues
3. Optionally fix Minor issues
4. Update review file with resolutions

---

### 10. Lint Check

**Purpose**: Run linting and type checking.

**Tools available**: Bash, Read, Edit

**Actions**:
1. Detect project type (Python, Node.js, etc.)
2. Run appropriate lint command
3. Run type checking if available
4. Auto-fix issues where possible

**Auto-detected commands**:

| Project Type | Lint | Type Check |
|--------------|------|------------|
| Python | `ruff check --fix .` | `mypy .` |
| Node.js | `npm run lint` | `npx tsc --noEmit` |
| Rust | `cargo clippy` | (built-in) |
| Go | `golangci-lint run` | (built-in) |

---

### 11. Documentation

**Purpose**: Update documentation for the changes.

**Tools available**: Read, Write, Edit, Grep, Glob

**Actions**:
1. Update README if needed
2. Update relevant docs/ files
3. Add code comments for complex logic
4. Update CHANGELOG.md

**Note**: Only makes necessary changes. Does not create unnecessary documentation.

---

### 12. Final Verification

**Purpose**: Verify everything works before committing.

**Tools available**: Bash, Read, Grep

**Actions**:
1. Run tests one final time
2. Run build if available
3. Verify no regressions

**Baseline tolerance**: Pre-existing test failures captured during the Test Execution phase are tolerated here as well — only net-new failures cause a failure. Build failures remain strict (no baseline tolerance).

---

### 13. Commit Prep

**Purpose**: Stage and commit changes.

**Tools available**: Bash, Read

**Actions**:
1. Review git status
2. Stage relevant changes (excluding secrets)
3. Create commit with descriptive message

**Commit format**:
```
<type>(<scope>): <description>

<body>

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

### 14. Conflict Check

**Purpose**: Ensure branch can be merged cleanly.

**Tools available**: Read, Edit, Bash

**Actions**:
1. Fetch latest from origin
2. Attempt rebase onto base branch
3. If conflicts, try to resolve automatically
4. If unresolvable, abort and report

---

### 15. PR Creation

**Purpose**: Create a pull request.

**Tools available**: Bash, Read

**Actions**:
1. Push branch to remote
2. Create PR with descriptive title and body
3. Include summary, changes, and testing info

**PR body format**:
```markdown
## Summary
- Key changes

## Changes
- File changes

## Testing
- How tested

---
Generated with SelfAssembler
```

---

### 16. PR Self-Review

**Purpose**: Self-review the PR with fresh context.

**Claude mode**: Read-only (`plan` mode)

**Fresh context**: Yes (unbiased review)

**Tools available**: Bash (for `gh` commands), Read

**Actions**:
1. Fetch PR diff
2. Review for issues
3. Add comments if problems found
4. Approve if looks good

## Phase Flow Control

### Skipping Phases

Skip to a specific phase:
```bash
selfassembler "Task" --skip-to implementation
```

### Disabling Phases

Disable in configuration:
```yaml
phases:
  documentation:
    enabled: false
```

### Approval Gates

Configure which phases require approval:
```yaml
approvals:
  enabled: true
  gates:
    planning: true
    implementation: false
    pr_creation: false
```

## Phase Artifacts

Each phase may produce artifacts stored in the context:

| Phase | Artifacts |
|-------|-----------|
| Setup | `worktree_path`, `branch_name` |
| Research | `research_file` |
| Planning | `plan_file` |
| Test Execution | `iterations`, `test_results`, `baseline_failures_present`, `warnings` |
| Code Review | `review_file` |
| Commit Prep | `commit_hash` |
| PR Creation | `pr_url` |

Access artifacts in subsequent phases via `context.get_artifact()`.
