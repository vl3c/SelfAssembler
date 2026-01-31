# SelfAssembler

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Autonomous multi-phase workflow orchestrator for Claude Code CLI.**

SelfAssembler automates the complete software development lifecycle by orchestrating Claude Code through 16 distinct phases: environment validation, git worktree setup, research, planning, implementation, testing with fix loops, code review, documentation, commits, and PR creation with self-review.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Workflow Phases](#workflow-phases)
- [Configuration](#configuration)
- [Operating Modes](#operating-modes)
- [Checkpoints & Recovery](#checkpoints--recovery)
- [Notifications](#notifications)
- [Development](#development)
- [Architecture](#architecture)
- [License](#license)

## Features

- **16-Phase Workflow**: Complete development lifecycle from preflight to PR self-review
- **Cost Tracking**: Budget limits with per-phase cost monitoring and alerts
- **Checkpoint Recovery**: Resume workflows from any phase after interruption
- **Approval Gates**: Pause for human review at configurable points
- **Language Agnostic**: Auto-detects Python, Node.js, Rust, Go, Java, Ruby, and more
- **Git Worktrees**: Isolated workspaces that don't affect your main branch
- **Container Isolation**: Safe autonomous mode with Docker
- **Notifications**: Console, webhook, and Slack support
- **Test Fix Loops**: Automatic retry with fixes when tests fail

## Installation

### From PyPI (when published)

```bash
pip install selfassembler
```

### From Source

```bash
git clone https://github.com/selfassembler/selfassembler.git
cd selfassembler
pip install -e .
```

### Requirements

- **Python 3.11+**
- **[Claude Code CLI](https://github.com/anthropics/claude-code)**:
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```
- **[GitHub CLI](https://cli.github.com/)** (for PR creation):
  ```bash
  # macOS
  brew install gh

  # Windows
  winget install GitHub.cli

  # Then authenticate
  gh auth login
  ```

## Quick Start

```bash
# Run a task with approval gates (default)
selfassembler "Add user authentication" --name auth-feature

# Review the generated plan at ./plans/plan-auth-feature.md
# Then approve to continue:
touch ./plans/.approved_planning

# Or run without approval gates for simpler tasks
selfassembler "Fix login bug" --name fix-login --no-approvals
```

## Usage

### Basic Commands

```bash
# Start a new task
selfassembler "Add user authentication" --name auth-feature

# Use an existing plan file
selfassembler @plans/my-plan.md --skip-to implementation

# Set a custom budget
selfassembler "Complex feature" --name feature --budget 25.0

# Specify repository path
selfassembler "Fix bug" --name bugfix --repo /path/to/project
```

### Utility Commands

```bash
# List all workflow phases
selfassembler --list-phases

# List available checkpoints
selfassembler --list-checkpoints

# Create default configuration file
selfassembler --init-config

# Grant approval for a phase
selfassembler --approve planning --plans-dir ./plans
```

### Resume & Recovery

```bash
# Resume from a checkpoint
selfassembler --resume checkpoint_abc123

# Skip to a specific phase
selfassembler "Task" --name task --skip-to implementation
```

## Workflow Phases

SelfAssembler executes 16 phases in sequence:

| # | Phase | Description | Approval Gate |
|---|-------|-------------|---------------|
| 1 | **Preflight** | Validate environment (CLI tools, git state) | No |
| 2 | **Setup** | Create git worktree and isolated workspace | No |
| 3 | **Research** | Gather project context and conventions | No |
| 4 | **Planning** | Create detailed implementation plan | **Yes** (default) |
| 5 | **Implementation** | Execute the plan, write code | No |
| 6 | **Test Writing** | Write comprehensive tests | No |
| 7 | **Test Execution** | Run tests with fix-and-retry loop | No |
| 8 | **Code Review** | Review implementation (fresh context) | No |
| 9 | **Fix Review Issues** | Address findings from review | No |
| 10 | **Lint Check** | Run linting and type checking | No |
| 11 | **Documentation** | Update docs if needed | No |
| 12 | **Final Verification** | Verify tests and build pass | No |
| 13 | **Commit Prep** | Stage and commit changes | No |
| 14 | **Conflict Check** | Rebase onto main, resolve conflicts | No |
| 15 | **PR Creation** | Create pull request | No |
| 16 | **PR Self-Review** | Self-review the PR with fresh context | No |

## Configuration

Create `selfassembler.yaml` in your project root:

```yaml
# Budget limit in USD for the entire workflow
budget_limit_usd: 15.0

# Directory for plans and artifacts
plans_dir: "./plans"

# Git settings
git:
  base_branch: "main"
  branch_prefix: "feature/"
  worktree_dir: "../.worktrees"
  cleanup_on_fail: true

# Command overrides (null = auto-detect)
commands:
  lint: null
  typecheck: null
  test: null

# Phase-specific settings
phases:
  planning:
    timeout: 600
    max_turns: 20
  test_execution:
    max_iterations: 5  # Max fix-and-retry loops

# Approval gates
approvals:
  enabled: true
  timeout_hours: 24.0
  gates:
    planning: true  # Pause after planning

# Notifications
notifications:
  console:
    enabled: true
  webhook:
    enabled: false
    url: "https://your-webhook.example.com/notify"
```

See [`selfassembler.yaml.example`](selfassembler.yaml.example) for all available options.

## Operating Modes

| Mode | Flag | Container | Permissions | Approval Gates |
|------|------|-----------|-------------|----------------|
| **Safe** (default) | none | No | Tool whitelist | Yes |
| **No Approvals** | `--no-approvals` | No | Tool whitelist | No |
| **Autonomous** | `--autonomous` | **Required** | Full access | No |

### Safe Mode (Default)

Uses Claude's permission system with tool whitelists. Pauses at approval gates for human review.

```bash
selfassembler "Add feature" --name feature
```

### No Approvals Mode

Skips approval gates but still uses Claude's permission prompts for dangerous operations.

```bash
selfassembler "Fix bug" --name bugfix --no-approvals
```

### Autonomous Mode (Requires Docker)

Grants Claude full system access. **Must run in a container** for safety:

```bash
# Build the Docker image
docker build -t selfassembler .

# Run with helper script (recommended)
./run-autonomous.sh ~/myproject "Add auth system" auth-system

# Or run directly with Docker
docker run --rm -it \
  -v ~/myproject:/workspace \
  -v ~/.gitconfig:/home/claude/.gitconfig:ro \
  -v ~/.ssh:/home/claude/.ssh:ro \
  -e ANTHROPIC_API_KEY \
  -e GH_TOKEN \
  selfassembler:latest \
  "Add auth system" \
  --name auth-system \
  --autonomous
```

## Checkpoints & Recovery

SelfAssembler automatically creates checkpoints at each phase transition. If a workflow fails or is interrupted, you can resume from where it left off:

```bash
# List available checkpoints
selfassembler --list-checkpoints

# Resume from a checkpoint
selfassembler --resume checkpoint_abc123
```

Checkpoints are stored in `~/.local/state/selfassembler/` and include:
- Complete workflow context
- Cost tracking data
- Completed phases
- Session IDs for potential Claude session resume

## Notifications

### Console (Default)

Colored output showing phase progress, costs, and errors.

### Webhook

Send notifications to any HTTP endpoint:

```yaml
notifications:
  webhook:
    enabled: true
    url: "https://your-server.com/webhook"
    events:
      - workflow_complete
      - workflow_failed
      - approval_needed
```

### Slack

Send notifications to a Slack channel:

```yaml
notifications:
  slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/services/..."
```

## Development

### Setup

```bash
# Clone and install with dev dependencies
git clone https://github.com/selfassembler/selfassembler.git
cd selfassembler
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=selfassembler

# Run specific test file
pytest tests/test_phases.py -v
```

### Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy selfassembler/

# Format code
ruff format .
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI (cli.py)                        │
│                    Argument parsing, entry point            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator (orchestrator.py)            │
│              State machine, phase runner, cleanup           │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────┐
│ Phases (phases.py)│ │State (state.py)│ │Notifications      │
│ 16 phase classes  │ │ Checkpoints   │ │ (notifications.py)│
└───────────────────┘ │ Approvals     │ └───────────────────┘
            │         └───────────────┘
            ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────┐
│Executor           │ │Git (git.py)   │ │Commands           │
│(executor.py)      │ │ Worktrees     │ │(commands.py)      │
│ Claude CLI wrapper│ │ Branches      │ │ Language detection│
└───────────────────┘ │ Commits       │ │ Test parsing      │
                      └───────────────┘ └───────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code CLI                         │
│                   (external dependency)                      │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

- **`cli.py`**: Command-line interface with argparse
- **`orchestrator.py`**: Manages phase transitions, checkpoints, approvals
- **`phases.py`**: All 16 phase implementations
- **`executor.py`**: Wraps Claude CLI, parses JSON output
- **`context.py`**: Workflow state with cost tracking
- **`config.py`**: Pydantic models for configuration
- **`state.py`**: Checkpoint and approval persistence
- **`git.py`**: Git operations (worktrees, branches, commits)
- **`commands.py`**: Language-agnostic command detection
- **`notifications.py`**: Notification channels

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting PRs.

## Acknowledgments

Built to work with [Claude Code](https://github.com/anthropics/claude-code) by Anthropic.
