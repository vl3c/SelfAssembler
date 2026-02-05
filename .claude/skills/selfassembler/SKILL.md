---
name: selfassembler
description: Run SelfAssembler autonomous workflow orchestrator for multi-phase development tasks. Use when the user wants to automate a complete development workflow including research, planning, implementation, testing, code review, and PR creation.
disable-model-invocation: true
argument-hint: [task description] [--name name]
---

# SelfAssembler

Autonomous multi-phase workflow orchestrator for CLI coding agents.

## Default Usage

```bash
./run-selfassembler.sh $ARGUMENTS
```

Note: Uses the wrapper script which activates the virtual environment.

## Quick Start Examples

**Basic task with approval gates:**
```bash
selfassembler "Add user authentication" --name auth-feature
```

**Without approval gates (simpler tasks):**
```bash
selfassembler "Fix login bug" --name fix-login --no-approvals
```

**Use existing plan file:**
```bash
selfassembler @plans/my-plan.md --skip-to implementation
```

**Use Codex instead of Claude:**
```bash
selfassembler "Add feature" --name feature --agent codex
```

**Enable multi-agent debate (Claude + Codex):**
```bash
selfassembler "Complex feature" --name feature --debate
```

## Core Options

| Flag | Description |
|------|-------------|
| `--name, -n <NAME>` | Short name for task (used in branch names) |
| `--repo <PATH>` | Target repository path (default: current directory) |
| `--budget <USD>` | Budget limit in USD (default: 15.0) |
| `--agent {claude,codex}` | Agent CLI to use (default: claude) |
| `--config, -c <PATH>` | Path to configuration file |
| `--plans-dir <PATH>` | Directory for plans/artifacts (default: ./plans) |

## Execution Modes

| Flag | Description |
|------|-------------|
| (default) | Approval gates enabled, permission prompts active |
| `--no-approvals` | Skip approval gates (still prompts for dangerous ops) |
| `--autonomous` | Full autonomy, no prompts (**requires Docker container**) |
| `--debate` | Enable Claude + Codex multi-agent debate |
| `--no-debate` | Force single-agent mode |

## Resume & Recovery

```bash
# List available checkpoints
selfassembler --list-checkpoints

# Resume from checkpoint
selfassembler --resume checkpoint_abc123

# Skip to specific phase
selfassembler "Task" --name task --skip-to implementation
```

## Workflow Phases

| # | Phase | Description |
|---|-------|-------------|
| 1 | preflight | Validate environment, auto-pull latest |
| 2 | setup | Create git worktree |
| 3 | research | Gather project context |
| 4 | planning | Create implementation plan |
| 5 | plan_review | Review the plan |
| 6 | implementation | Write the code |
| 7 | test_writing | Write tests |
| 8 | test_execution | Run tests with fix loops |
| 9 | code_review | Review implementation |
| 10 | fix_review_issues | Address review findings |
| 11 | lint_check | Linting and type checking |
| 12 | documentation | Update docs |
| 13 | final_verification | Final test/build pass |
| 14 | commit_prep | Stage and commit |
| 15 | conflict_check | Rebase, resolve conflicts |
| 16 | pr_creation | Create pull request |
| 17 | pr_self_review | Self-review the PR |

## Utility Commands

```bash
# List all phases
selfassembler --list-phases

# Show phase help
selfassembler --help-phases
selfassembler --help-phases planning implementation

# Create default config
selfassembler --init-config

# Grant approval for a phase
selfassembler --approve planning --plans-dir ./plans

# Dry run (show phases without executing)
selfassembler "Task" --name task --dry-run
```

## Output Options

| Flag | Description |
|------|-------------|
| `--quiet, -q` | Suppress non-essential output |
| `--verbose, -v` | Enable verbose output |
| `--no-stream` | Wait for complete response (no streaming) |
| `--debug <CATEGORIES>` | Debug mode (e.g., 'api,mcp') |

## Configuration

Create `selfassembler.yaml` in project root:

```yaml
budget_limit_usd: 15.0
plans_dir: "./plans"

agent:
  type: "claude"  # or "codex"

git:
  base_branch: "main"
  branch_prefix: "feature/"

approvals:
  enabled: true
  gates:
    planning: true

debate:
  enabled: false
  primary_agent: claude
  secondary_agent: codex
```

## Sandboxed Execution

For safer execution, run inside GritGuard:

```bash
gritguard selfassembler "Add feature" --repo /path/to/project
```
