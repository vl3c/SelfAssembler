# SelfAssembler

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Autonomous multi-phase workflow orchestrator for CLI coding agents.**

SelfAssembler automates the complete software development lifecycle by orchestrating collaborative CLI coding agents through distinct phases: environment validation, git worktree setup, research, planning, implementation, testing with fix loops, code review, documentation, commits, and PR creation with self-review.

Supports multiple agent backends:
- **Claude Code** (default) - Anthropic's Claude Code CLI
- **OpenAI Codex** - OpenAI's Codex CLI

Optionally enables **multi-agent debate** where Claude and Codex collaborate through structured debates on key phases for higher quality outputs.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Workflow Phases](#workflow-phases)
- [Configuration](#configuration)
- [Operating Modes](#operating-modes)
- [Multi-Agent Debate](#multi-agent-debate)
- [Checkpoints & Recovery](#checkpoints--recovery)
- [Notifications](#notifications)
- [Development](#development)
- [Architecture](#architecture)
- [License](#license)

## Features

- **Multi-Phase Workflow**: Complete development lifecycle from preflight to PR self-review
- **Multi-Agent Debate**: Optional Claude + Codex collaboration through feedback review or structured debates
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
- **Agent CLI** (one of the following):
  - **[Claude Code CLI](https://github.com/anthropics/claude-code)** (default):
    ```bash
    npm install -g @anthropic-ai/claude-code
    ```
  - **[OpenAI Codex CLI](https://github.com/openai/codex)**:
    ```bash
    npm install -g @openai/codex
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

# Use OpenAI Codex instead of Claude Code
selfassembler "Add feature" --name feature --agent codex
```

### Utility Commands

```bash
# List all workflow phases
selfassembler --list-phases

# Show detailed help for all phases
selfassembler --help-phases

# Show detailed help for specific phases
selfassembler --help-phases planning implementation

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

SelfAssembler executes the following phases in sequence:

| # | Phase | Description |
|---|-------|-------------|
| 1 | **Preflight** | Validate environment, auto-pull latest changes |
| 2 | **Setup** | Create git worktree and isolated workspace |
| 3 | **Research** | Gather project context and conventions |
| 4 | **Planning** | Create detailed implementation plan |
| 5 | **Implementation** | Execute the plan, write code |
| 6 | **Test Writing** | Write comprehensive tests |
| 7 | **Test Execution** | Run tests with fix-and-retry loop |
| 8 | **Code Review** | Review implementation (fresh context) |
| 9 | **Fix Review Issues** | Address findings from review |
| 10 | **Lint Check** | Run linting and type checking |
| 11 | **Documentation** | Update docs if needed |
| 12 | **Final Verification** | Verify tests and build pass |
| 13 | **Commit Prep** | Stage and commit changes |
| 14 | **Conflict Check** | Rebase onto main, resolve conflicts |
| 15 | **PR Creation** | Create pull request |
| 16 | **PR Self-Review** | Self-review the PR with fresh context |

## Configuration

Create `selfassembler.yaml` in your project root:

```yaml
# Budget limit in USD for the entire workflow
budget_limit_usd: 15.0

# Directory for plans and artifacts
plans_dir: "./plans"

# Agent settings (choose which CLI to use)
agent:
  type: "claude"  # or "codex" for OpenAI Codex CLI
  model: null     # optional: override default model

# Git settings
git:
  base_branch: "main"
  branch_prefix: "feature/"
  worktree_dir: "../.worktrees"
  cleanup_on_fail: true
  auto_update: true  # auto-pull and checkout base branch in preflight

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

# Rules written to CLAUDE.md in the worktree
rules:
  enabled_rules:
    - "no-signature"  # Available: no-signature, no-emojis, no-yapping
  custom_rules: []    # Add custom rule descriptions

# Multi-agent debate (optional)
debate:
  enabled: false
  primary_agent: claude
  secondary_agent: codex
  mode: feedback       # "feedback" or "debate"
  intensity: low       # "low" or "high" (debate mode only)
  phases:
    research: true
    planning: true
    plan_review: true
    code_review: true

# Notifications
notifications:
  console:
    enabled: true
  webhook:
    enabled: false
    url: "https://your-webhook.example.com/notify"
```

See [`docs/configuration.md`](docs/configuration.md) for all available options.

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

## Multi-Agent Debate

SelfAssembler supports an optional **multi-agent debate mode** where Claude (primary) and Codex (secondary) collaborate to produce higher-quality outputs. Two modes are available:

### Debate Modes

#### Feedback Mode (`mode: feedback`, default)

A lightweight review pass. The primary agent does the work, the secondary agent reviews it, and the primary agent incorporates the feedback.

1. **Generate**: Primary agent produces its output
2. **Feedback**: Secondary agent reviews and critiques the output
3. **Synthesis**: Primary agent incorporates feedback into the final result

Best for: most tasks. Adds a second perspective at minimal extra cost.

#### Debate Mode (`mode: debate`)

Both agents independently generate output, then argue back and forth before the primary agent synthesizes everything.

1. **Turn 1 - Independent Generation**: Both agents work in parallel, producing independent analyses
2. **Turn 2 - Debate Exchange**: Agents exchange critiques. Primary always opens and closes.
   - `intensity: low` - one exchange (3 messages: primary, secondary, primary)
   - `intensity: high` - two exchanges (5 messages)
3. **Turn 3 - Synthesis**: Primary agent synthesizes all outputs into a final result

Best for: high-stakes tasks where independent perspectives and adversarial critique justify the extra cost.

### Debate-Enabled Phases

| Phase | Rationale |
|-------|-----------|
| **Research** | A second agent catches gaps in research |
| **Planning** | Alternative plans reveal different architectures and trade-offs |
| **Plan Review** | Independent SWOT analyses from different perspectives |
| **Code Review** | Two reviewers catch different issues |

### Enabling Debate Mode

**Auto-Detection (Default)**: SelfAssembler automatically detects installed agents. If both `claude` and `codex` CLIs are available, debate mode is enabled by default with Claude as primary and Codex as secondary.

**CLI Flags**:
```bash
# Force enable debate mode
selfassembler "Add feature" --debate

# Force disable debate mode (single agent)
selfassembler "Add feature" --no-debate
```

**Configuration** in `selfassembler.yaml`:

```yaml
debate:
  enabled: true
  primary_agent: claude      # Primary agent (generates output, does synthesis)
  secondary_agent: codex     # Secondary agent (reviews or provides alternative perspective)

  # "feedback" - secondary reviews primary's work (default)
  # "debate"   - both generate independently, then exchange critiques
  mode: feedback

  # Only applies when mode is "debate":
  # "low"  - one exchange back and forth (3 messages)
  # "high" - two exchanges back and forth (5 messages)
  intensity: low

  phases:
    research: true
    planning: true
    plan_review: true
    code_review: true
```

### Output Files

Debate mode produces additional files in your plans directory:

```
plans/
  # Primary agent output (always present)
  research-{task}-primary.md

  # Secondary agent output (full debate mode only)
  research-{task}-secondary.md

  # Debate/feedback transcript
  debates/
    research-{task}-debate.md

  # Final synthesized output
  research-{task}.md
```

### Cost Considerations

- **Feedback mode**: ~1.5x cost per phase. Secondary only runs once (review), no independent generation.
- **Debate mode** (low): ~2-2.5x cost per phase. Both agents generate independently, then one exchange.
- **Debate mode** (high): ~2.5-3x cost per phase. Same as low with an additional exchange round.

Consider increasing `budget_limit_usd` when using debate mode.

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
# Clone the repository
git clone https://github.com/selfassembler/selfassembler.git
cd selfassembler

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

> **Note**: A virtual environment is required on systems with externally-managed Python (Debian 12+, Ubuntu 23.04+, etc.).

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
│ Phase classes     │ │ Checkpoints   │ │ (notifications.py)│
└───────────────────┘ │ Approvals     │ └───────────────────┘
            │         └───────────────┘
            ├─────────────────┐
            ▼                 ▼
┌───────────────────┐ ┌───────────────────┐
│Executors          │ │Debate (debate/)   │
│(executors/)       │ │ DebateOrchestrator│
│ Claude, Codex     │ │ Prompts, Logs     │
└───────────────────┘ └───────────────────┘
            │                 │
            ├─────────────────┘
            ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────┐
│Git (git.py)       │ │Commands       │ │Config (config.py) │
│ Worktrees         │ │(commands.py)  │ │ Pydantic models   │
│ Branches, Commits │ │ Lang detection│ │ YAML loading      │
└───────────────────┘ └───────────────┘ └───────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│               Agent CLI (Claude Code or Codex)              │
│                   (external dependency)                      │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

- **`cli.py`**: Command-line interface with argparse
- **`orchestrator.py`**: Manages phase transitions, checkpoints, approvals
- **`phases.py`**: All phase implementations
- **`executors/`**: Agent CLI implementations (Claude, Codex)
- **`debate/`**: Multi-agent debate system (orchestrator, prompts, transcripts)
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
