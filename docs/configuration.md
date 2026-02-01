# Configuration Guide

SelfAssembler can be configured via a YAML file, command-line arguments, or environment variables.

## Configuration File

Create `selfassembler.yaml` in your project root. The configuration file is optional - sensible defaults are used when not provided.

### Full Configuration Reference

```yaml
# =============================================================================
# Budget & General Settings
# =============================================================================

# Maximum cost in USD for the entire workflow
# The workflow will stop if this limit is exceeded
budget_limit_usd: 15.0

# Enable fully autonomous mode (requires container)
# When true, uses --dangerously-skip-permissions
autonomous_mode: false

# Directory for plans, research, and review artifacts
# Relative paths are resolved from the repository root
plans_dir: "./plans"

# =============================================================================
# Agent CLI Settings
# =============================================================================

# Agent configuration (selects which CLI to use)
agent:
  # Which agent CLI to use: "claude" or "codex"
  type: "claude"

  # Default timeout in seconds for agent CLI calls
  default_timeout: 600

  # Default maximum turns for agentic operations
  max_turns_default: 50

  # Use dangerous mode (skip all permission prompts)
  # Only effective when autonomous_mode is true
  dangerous_mode: false

  # Override the default model (optional)
  # For Claude: claude-sonnet-4-20250514, etc.
  # For Codex: gpt-4o, o3, etc.
  model: null

# Legacy Claude-specific settings (for backward compatibility)
# These values are merged into agent config when agent.type is "claude"
claude:
  default_timeout: 600
  max_turns_default: 50
  dangerous_mode: false

# =============================================================================
# Git Settings
# =============================================================================

git:
  # Base branch to create feature branches from
  base_branch: "main"

  # Directory for git worktrees (relative to repo parent)
  worktree_dir: "../.worktrees"

  # Prefix for generated branch names
  branch_prefix: "feature/"

  # Clean up worktree on workflow failure
  cleanup_on_fail: true

  # Delete remote branch on workflow failure
  # Only applies if branch was pushed
  cleanup_remote_on_fail: false

  # Automatically pull latest changes and checkout base branch in preflight
  # When true, preflight will checkout the base branch and pull before checking
  # if the local branch is up to date. This allows workflows to start even when
  # behind the remote. Set to false to require manual git operations.
  auto_update: true

# =============================================================================
# Command Overrides
# =============================================================================

# Override auto-detected commands
# Set to null for auto-detection, or specify a custom command
commands:
  # Linting command
  lint: null  # e.g., "npm run lint" or "ruff check ."

  # Type checking command
  typecheck: null  # e.g., "npx tsc --noEmit" or "mypy ."

  # Test command
  test: null  # e.g., "npm test" or "pytest"

  # Build command
  build: null  # e.g., "npm run build" or "python -m build"

# =============================================================================
# Phase Configuration
# =============================================================================

phases:
  preflight:
    timeout: 60
    max_turns: 1
    estimated_cost: 0.0
    enabled: true

  setup:
    timeout: 120
    max_turns: 1
    estimated_cost: 0.0
    enabled: true

  research:
    timeout: 300
    max_turns: 25
    estimated_cost: 0.5
    enabled: true

  planning:
    timeout: 600
    max_turns: 20
    estimated_cost: 1.0
    enabled: true

  implementation:
    timeout: 3600
    max_turns: 100
    estimated_cost: 3.0
    enabled: true

  test_writing:
    timeout: 1200
    max_turns: 50
    estimated_cost: 1.5
    enabled: true

  test_execution:
    timeout: 1800
    max_turns: 60
    max_iterations: 5  # Max fix-and-retry loops
    estimated_cost: 2.0
    enabled: true

  code_review:
    timeout: 600
    max_turns: 30
    estimated_cost: 1.0
    enabled: true

  fix_review_issues:
    timeout: 900
    max_turns: 40
    estimated_cost: 1.0
    enabled: true

  lint_check:
    timeout: 300
    max_turns: 20
    estimated_cost: 0.5
    enabled: true

  documentation:
    timeout: 600
    max_turns: 30
    estimated_cost: 0.5
    enabled: true

  final_verification:
    timeout: 300
    max_turns: 15
    estimated_cost: 0.5
    enabled: true

  commit_prep:
    timeout: 300
    max_turns: 10
    estimated_cost: 0.3
    enabled: true

  conflict_check:
    timeout: 300
    max_turns: 20
    estimated_cost: 0.5
    enabled: true

  pr_creation:
    timeout: 300
    max_turns: 15
    estimated_cost: 0.3
    enabled: true

  pr_self_review:
    timeout: 600
    max_turns: 20
    estimated_cost: 0.5
    enabled: true

# =============================================================================
# Approval Gates
# =============================================================================

approvals:
  # Enable/disable approval system entirely
  enabled: true

  # Hours to wait for approval before timing out
  timeout_hours: 24.0

  # Which phases require approval
  gates:
    planning: true       # Recommended: review plan before implementation
    implementation: false
    pr_creation: false

# =============================================================================
# Notifications
# =============================================================================

notifications:
  # Console output
  console:
    enabled: true
    colors: true  # ANSI colors

  # HTTP webhook
  webhook:
    enabled: false
    url: null  # "https://your-server.com/webhook"
    events:
      - workflow_complete
      - workflow_failed
      - approval_needed

  # Slack incoming webhook
  slack:
    enabled: false
    webhook_url: null  # "https://hooks.slack.com/services/..."

# =============================================================================
# Rules / Guidelines
# =============================================================================

# Rules written to CLAUDE.md in the worktree to guide Claude's behavior
rules:
  # IDs of builtin rules to enable
  # Available: no-signature, no-emojis, no-yapping
  enabled_rules:
    - "no-signature"

  # Additional custom rule descriptions
  custom_rules: []

# =============================================================================
# File Copying
# =============================================================================

# Files to copy from main repo to worktree
# Supports glob patterns
copy_files:
  - ".env"
  - ".env.local"
  - ".claude/*"
```

## Command-Line Overrides

Command-line arguments override configuration file settings:

```bash
# Override budget
selfassembler "Task" --budget 25.0

# Override plans directory
selfassembler "Task" --plans-dir ./my-plans

# Disable approvals
selfassembler "Task" --no-approvals

# Enable autonomous mode
selfassembler "Task" --autonomous

# Use OpenAI Codex instead of Claude Code
selfassembler "Task" --agent codex
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Required for Claude CLI |
| `OPENAI_API_KEY` | Required for Codex CLI |
| `GH_TOKEN` | GitHub token for PR creation |
| `SELFASSEMBLER_ALLOW_HOST_AUTONOMOUS` | Set to `I_ACCEPT_THE_RISK` to bypass container requirement |

## Configuration Precedence

1. Command-line arguments (highest priority)
2. Configuration file
3. Default values (lowest priority)

## Per-Project Configuration

Place `selfassembler.yaml` in your project root. When running from a subdirectory, SelfAssembler searches upward for the configuration file.

Search order:
1. `selfassembler.yaml`
2. `selfassembler.yml`
3. `.selfassembler.yaml`
4. `.selfassembler.yml`

## Disabling Phases

Disable specific phases by setting `enabled: false`:

```yaml
phases:
  documentation:
    enabled: false  # Skip documentation phase
  pr_self_review:
    enabled: false  # Skip self-review
```

## Rules and Guidelines

SelfAssembler can write a `CLAUDE.md` file to the worktree containing rules that Claude should follow. This file is automatically created after the setup phase.

### Builtin Rules

| Rule ID | Description |
|---------|-------------|
| `no-signature` | Do not add Co-Authored-By, signature lines, or AI attribution to commits, PRs, or code comments |
| `no-emojis` | Do not use emojis in code, commits, or documentation |
| `no-yapping` | Be concise, avoid excessive explanations or verbose output |

### Configuration

```yaml
rules:
  # Enable specific builtin rules by ID
  enabled_rules:
    - "no-signature"
    - "no-emojis"

  # Add custom rules (free-form descriptions)
  custom_rules:
    - "Always use type hints in Python code"
    - "Prefer functional components in React"
```

By default, only `no-signature` is enabled.

## Estimated Costs

The `estimated_cost` setting is used for budget checking before starting a phase. If the remaining budget is less than the estimated cost, the workflow will stop with a budget error.

Adjust these values based on your experience with actual costs:

```yaml
phases:
  implementation:
    estimated_cost: 5.0  # Increase for complex tasks
```

## Example Configurations

### Minimal Configuration

```yaml
budget_limit_usd: 10.0
approvals:
  enabled: false
```

### CI/CD Configuration

```yaml
budget_limit_usd: 20.0
autonomous_mode: true

approvals:
  enabled: false

notifications:
  webhook:
    enabled: true
    url: "${WEBHOOK_URL}"
```

### Conservative Configuration

```yaml
budget_limit_usd: 5.0

approvals:
  enabled: true
  gates:
    planning: true
    implementation: true
    pr_creation: true

phases:
  implementation:
    max_turns: 50  # Limit complexity
```

### Using OpenAI Codex

```yaml
agent:
  type: "codex"
  model: "o3"  # Optional: specify model

# Disable git auto-update if you prefer manual control
git:
  auto_update: false
```
