# SelfAssembler - AI Usage Guide

This document provides comprehensive documentation for AI agents to understand and use SelfAssembler effectively.

## Overview

SelfAssembler is a CLI tool that orchestrates AI coding agents (Claude Code or OpenAI Codex) through a multi-phase software development workflow. It automates research, planning, implementation, testing, code review, and PR creation.

## Command Syntax

```bash
selfassembler [TASK] [OPTIONS]
```

### Positional Arguments

| Argument | Description |
|----------|-------------|
| `TASK` | Task description or path to plan file (prefix with `@` for file) |

### Examples

```bash
# Simple task description
selfassembler "Add user authentication with JWT tokens"

# Use existing plan file
selfassembler @plans/my-plan.md

# With task name
selfassembler "Fix login bug in auth module" --name fix-login-bug
```

## CLI Flags Reference

### Core Options

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--name` | `-n` | string | auto | Task name for branch/file naming |
| `--repo` | `-r` | path | `.` | Repository path |
| `--budget` | `-b` | float | `15.0` | Budget limit in USD |
| `--plans-dir` | | path | `./plans` | Directory for plans and artifacts |

### Agent Selection

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--agent` | `-a` | string | `claude` | Agent type: `claude` or `codex` |
| `--model` | `-m` | string | none | Override default model |

### Execution Modes

| Flag | Short | Description |
|------|-------|-------------|
| `--autonomous` | | Full access mode (requires Docker container) |
| `--no-approvals` | | Skip approval gates but keep permission prompts |

### Phase Control

| Flag | Type | Description |
|------|------|-------------|
| `--skip-to` | string | Skip to specific phase |
| `--resume` | string | Resume from checkpoint ID |
| `--disable-phase` | string | Disable specific phase(s) (repeatable) |

### Information Commands

| Flag | Description |
|------|-------------|
| `--list-phases` | List all workflow phases |
| `--help-phases` | Show detailed help for phases |
| `--list-checkpoints` | List available checkpoints |
| `--init-config` | Create default configuration file |
| `--version` | Show version |

### Approval Management

| Flag | Type | Description |
|------|------|-------------|
| `--approve` | string | Grant approval for a phase |

## Configuration File

Create `selfassembler.yaml` in project root:

```yaml
# =============================================================================
# SELFASSEMBLER CONFIGURATION
# =============================================================================

# Maximum budget for entire workflow (USD)
budget_limit_usd: 15.0

# Run without human approval gates
autonomous_mode: false

# Directory for plans, research, and artifacts
plans_dir: "./plans"

# =============================================================================
# AGENT SETTINGS
# =============================================================================
agent:
  type: "claude"              # "claude" or "codex"
  default_timeout: 600        # Timeout per phase (seconds)
  max_turns_default: 50       # Max agentic turns per phase
  dangerous_mode: false       # Skip permission prompts (autonomous only)
  model: null                 # Override model (e.g., "opus", "gpt-4")

# =============================================================================
# GIT SETTINGS
# =============================================================================
git:
  base_branch: "main"         # Base branch for PRs
  branch_prefix: "feature/"   # Prefix for feature branches
  worktree_dir: "../.worktrees"  # Worktree location
  cleanup_on_fail: false      # Remove worktree on failure
  cleanup_remote_on_fail: false  # Delete remote branch on failure
  auto_update: true           # Auto-pull base branch in preflight

# =============================================================================
# PHASE SETTINGS
# =============================================================================
phases:
  preflight:
    timeout: 60
    max_turns: 1
    enabled: true

  setup:
    timeout: 120
    max_turns: 1

  research:
    timeout: 300
    max_turns: 25
    estimated_cost: 0.5

  planning:
    timeout: 600
    max_turns: 20
    estimated_cost: 1.0

  plan_review:
    timeout: 600
    max_turns: 30
    estimated_cost: 1.0

  implementation:
    timeout: 3600
    max_turns: 100
    estimated_cost: 3.0

  test_writing:
    timeout: 1200
    max_turns: 50
    estimated_cost: 1.5

  test_execution:
    timeout: 1800
    max_turns: 60
    max_iterations: 5         # Fix-and-retry loops
    estimated_cost: 2.0

  code_review:
    timeout: 600
    max_turns: 30
    estimated_cost: 1.0

  fix_review_issues:
    timeout: 900
    max_turns: 40
    estimated_cost: 1.0

  lint_check:
    timeout: 300
    max_turns: 20
    max_iterations: 5
    max_retries: 3
    estimated_cost: 0.5

  documentation:
    timeout: 600
    max_turns: 30
    estimated_cost: 0.5

  final_verification:
    timeout: 300
    max_turns: 15
    estimated_cost: 0.5

  commit_prep:
    timeout: 300
    max_turns: 10
    estimated_cost: 0.3

  conflict_check:
    timeout: 300
    max_turns: 20
    estimated_cost: 0.5

  pr_creation:
    timeout: 300
    max_turns: 15
    estimated_cost: 0.3

  pr_self_review:
    timeout: 600
    max_turns: 20
    estimated_cost: 0.5

# =============================================================================
# APPROVAL GATES
# =============================================================================
approvals:
  enabled: true               # Enable approval system
  timeout_hours: 24.0         # Timeout waiting for approval
  gates:
    planning: true            # Pause after planning phase
    plan_review: false
    implementation: false
    pr_creation: false

# =============================================================================
# COMMAND OVERRIDES
# =============================================================================
commands:
  lint: null                  # e.g., "npm run lint" or "ruff check ."
  typecheck: null             # e.g., "npm run typecheck" or "mypy ."
  test: null                  # e.g., "npm test" or "pytest"
  build: null                 # e.g., "npm run build"

# =============================================================================
# RULES (written to CLAUDE.md in worktree)
# =============================================================================
rules:
  enabled_rules:
    - "no-signature"          # Don't add AI attribution to commits
    # - "no-emojis"           # Don't use emojis
    # - "no-yapping"          # Be concise
  custom_rules: []            # Add custom rule strings

# =============================================================================
# MULTI-AGENT DEBATE (Optional)
# =============================================================================
debate:
  enabled: false              # Enable multi-agent debate
  primary_agent: "claude"     # Primary agent (does synthesis)
  secondary_agent: "codex"    # Secondary agent (provides alternatives)

  # Debate structure
  max_turns: 3                # Total turns (1-5)
  max_exchange_messages: 3    # Messages in Turn 2 (2-6)
  parallel_turn_1: true       # Run Turn 1 in parallel

  # Timeouts
  turn_timeout_seconds: 300   # Timeout per turn
  message_timeout_seconds: 180  # Timeout per message in Turn 2

  # Output
  keep_intermediate_files: true  # Keep agent-specific outputs
  debate_subdir: "debates"    # Subdirectory for debate logs
  include_attribution: true   # [Claude]/[Codex] markers

  # Phases with debate enabled
  phases:
    research: true
    planning: true
    plan_review: true
    code_review: true

# =============================================================================
# NOTIFICATIONS
# =============================================================================
notifications:
  console:
    enabled: true
    colors: true

  webhook:
    enabled: false
    url: null
    events:
      - workflow_complete
      - workflow_failed
      - approval_needed

# =============================================================================
# STREAMING OUTPUT
# =============================================================================
streaming:
  enabled: true
  verbose: true
  debug: null                 # Debug categories: "api", "mcp", etc.
  show_tool_calls: true
  truncate_length: 200

# =============================================================================
# FILES TO COPY TO WORKTREE
# =============================================================================
copy_files:
  - ".env"
  - ".env.local"
  - ".claude/*"
```

## Workflow Phases

### Phase Execution Order

1. **preflight** - Validate environment, check CLI tools, auto-pull
2. **setup** - Create git worktree, copy config files
3. **research** - Gather project context, find related code
4. **planning** - Create detailed implementation plan
5. **plan_review** - SWOT analysis of the plan
6. **implementation** - Execute the plan, write code
7. **test_writing** - Write comprehensive tests
8. **test_execution** - Run tests with fix loops
9. **code_review** - Review implementation (fresh context)
10. **fix_review_issues** - Address review findings
11. **lint_check** - Run linting and type checking
12. **documentation** - Update docs as needed
13. **final_verification** - Verify tests and build pass
14. **commit_prep** - Stage and commit changes
15. **conflict_check** - Rebase, resolve conflicts
16. **pr_creation** - Create pull request
17. **pr_self_review** - Self-review the PR

### Phase Properties

| Phase | Fresh Context | Approval Gate | Write Access |
|-------|---------------|---------------|--------------|
| research | Yes | No | No |
| planning | Yes | Configurable | No |
| plan_review | Yes | Configurable | No |
| implementation | No | No | Yes |
| code_review | Yes | No | No |
| pr_self_review | Yes | No | Yes |

## Common Usage Patterns

### Simple Bug Fix

```bash
selfassembler "Fix null pointer exception in user service" \
  --name fix-null-pointer \
  --no-approvals
```

### Feature Implementation with Review

```bash
selfassembler "Add OAuth2 authentication with Google provider" \
  --name oauth2-google \
  --budget 25.0
```

### Using Existing Plan

```bash
selfassembler @plans/my-feature-plan.md \
  --name my-feature \
  --skip-to implementation
```

### Resume Failed Workflow

```bash
# List checkpoints
selfassembler --list-checkpoints

# Resume from checkpoint
selfassembler --resume checkpoint_abc123def
```

### Autonomous Mode (Docker)

```bash
docker run --rm -it \
  -v /path/to/project:/workspace \
  -v ~/.gitconfig:/home/user/.gitconfig:ro \
  -e ANTHROPIC_API_KEY \
  -e GH_TOKEN \
  selfassembler:latest \
  "Add caching layer" \
  --name add-caching \
  --autonomous
```

### Using OpenAI Codex

```bash
selfassembler "Refactor database queries" \
  --name refactor-db \
  --agent codex
```

### Enable Multi-Agent Debate

```bash
# Via config file (recommended)
# Set debate.enabled: true in selfassembler.yaml

# The workflow will automatically use debate for:
# - research phase
# - planning phase
# - plan_review phase
# - code_review phase
```

## Output Files

### Plans Directory Structure

```
plans/
  research-{task}.md          # Research findings
  plan-{task}.md              # Implementation plan
  plan-review-{task}.md       # Plan SWOT analysis
  review-{task}.md            # Code review findings

  # With debate enabled:
  research-{task}-claude.md   # Claude's research
  research-{task}-codex.md    # Codex's research
  debates/
    research-{task}-debate.md # Debate transcript
```

### Logs

```
logs/
  workflow-{task}-{timestamp}.log    # Human-readable log
  workflow-{task}-{timestamp}.jsonl  # Machine-readable log
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Phase failed |
| 4 | Budget exceeded |
| 5 | Approval timeout |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Claude |
| `OPENAI_API_KEY` | API key for Codex |
| `GH_TOKEN` | GitHub token for PR creation |
| `SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS` | Set to `I_ACCEPT_THE_RISK` to run autonomous mode without container (dangerous) |

## Tips for AI Agents

1. **Always specify `--name`**: Use descriptive, kebab-case names for better organization

2. **Check budget**: Complex tasks may need `--budget 25.0` or higher

3. **Use `--no-approvals` for simple tasks**: Speeds up execution for bug fixes

4. **Review generated plans**: The plan at `plans/plan-{name}.md` shows what will be implemented

5. **Resume on failure**: Use `--list-checkpoints` and `--resume` to continue failed workflows

6. **Disable unnecessary phases**: Use `--disable-phase documentation` to skip phases

7. **Use plan files for complex tasks**: Write detailed plans and use `@plans/plan.md` syntax

8. **Enable debate for critical work**: Multi-agent debate produces higher quality outputs for research, planning, and review phases
