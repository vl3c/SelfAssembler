# Contributing to SelfAssembler

Thank you for your interest in contributing to SelfAssembler! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Style Guidelines](#style-guidelines)
- [Architecture Overview](#architecture-overview)

## Code of Conduct

Please be respectful and constructive in all interactions. We're building something together.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment
4. Create a branch for your changes
5. Make your changes
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- GitHub CLI (`gh`) for testing PR features

### Installation

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/selfassembler.git
cd selfassembler

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Verify Setup

```bash
# Run tests
pytest

# Check linting
ruff check .

# Check types
mypy selfassembler/
```

## Making Changes

### Branch Naming

Use descriptive branch names:

- `feature/add-slack-notifications`
- `fix/checkpoint-recovery-bug`
- `docs/improve-configuration-guide`
- `refactor/simplify-phase-runner`

### Commit Messages

Follow conventional commit format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(phases): add retry logic to test execution phase

fix(git): handle detached HEAD state in worktree creation

docs(readme): add troubleshooting section
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_phases.py

# Run with coverage
pytest --cov=selfassembler --cov-report=html

# Run only fast tests (no integration)
pytest -m "not integration"
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_<module>.py`
- Use pytest fixtures for common setup
- Test both success and failure cases
- Mock external dependencies (Claude CLI, git, etc.)

Example test:

```python
import pytest
from selfassembler.context import WorkflowContext
from selfassembler.errors import BudgetExceededError

class TestWorkflowContext:
    @pytest.fixture
    def context(self):
        return WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/test"),
            plans_dir=Path("/test/plans"),
            budget_limit_usd=10.0,
        )

    def test_budget_exceeded(self, context):
        context.add_cost("phase1", 5.0)
        with pytest.raises(BudgetExceededError):
            context.add_cost("phase2", 6.0)
```

## Submitting Changes

### Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add tests for new functionality
4. Run linting and type checks
5. Create a pull request with a clear description

### PR Description Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- List of specific changes made

## Testing
- How was this tested?
- Any manual testing steps?

## Related Issues
Fixes #123
```

### Review Process

- All PRs require at least one review
- Address review feedback promptly
- Keep discussions constructive

## Style Guidelines

### Python Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check style
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

Key conventions:
- Line length: 100 characters
- Use type hints for all function signatures
- Use docstrings for public functions and classes
- Prefer explicit imports over star imports

### Documentation Style

- Use clear, concise language
- Include code examples where helpful
- Keep README focused on getting started
- Put detailed docs in the `docs/` folder

## Architecture Overview

### Adding a New Phase

1. Create a new class in `phases.py` inheriting from `Phase`
2. Implement the `run()` method
3. Add the phase to `PHASE_CLASSES` list (in order)
4. Add configuration in `config.py` if needed
5. Add tests in `tests/test_phases.py`

Example:

```python
class MyNewPhase(Phase):
    """Description of what this phase does."""

    name = "my_new_phase"
    timeout_seconds = 300
    allowed_tools = ["Read", "Write"]

    def run(self) -> PhaseResult:
        # Implementation here
        result = self.executor.execute(
            prompt="...",
            allowed_tools=self.allowed_tools,
        )
        return PhaseResult(
            success=not result.is_error,
            cost_usd=result.cost_usd,
        )
```

### Adding a Notification Channel

1. Create a class inheriting from `NotificationChannel` in `notifications.py`
2. Implement the `send()` method
3. Add configuration in `config.py`
4. Update `create_notifier_from_config()`

### Key Files

| File | Purpose |
|------|---------|
| `cli.py` | Entry point, argument parsing |
| `orchestrator.py` | Phase sequencing, state machine |
| `phases.py` | All phase implementations |
| `executor.py` | Claude CLI wrapper |
| `context.py` | Workflow state |
| `config.py` | Configuration models |
| `state.py` | Persistence (checkpoints, approvals) |
| `git.py` | Git operations |
| `commands.py` | Language detection |
| `notifications.py` | Notification system |
| `errors.py` | Custom exceptions |

## Questions?

Feel free to open an issue for questions or discussions about potential contributions.

Thank you for contributing!
