"""Configuration models for SelfAssembler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ClaudeConfig(BaseModel):
    """Configuration for Claude CLI execution."""

    default_timeout: int = Field(default=600, ge=60, le=7200)
    max_turns_default: int = Field(default=50, ge=1, le=500)
    dangerous_mode: bool = Field(default=False)


class GitConfig(BaseModel):
    """Configuration for git operations."""

    base_branch: str = Field(default="main")
    worktree_dir: str = Field(default="../.worktrees")
    branch_prefix: str = Field(default="feature/")
    cleanup_on_fail: bool = Field(default=True)
    cleanup_remote_on_fail: bool = Field(default=False)


class PhaseConfig(BaseModel):
    """Configuration for a specific phase."""

    timeout: int = Field(default=600, ge=60)
    max_turns: int = Field(default=50, ge=1)
    max_iterations: int = Field(default=5, ge=1)
    estimated_cost: float = Field(default=1.0, ge=0.0)
    enabled: bool = Field(default=True)


class PhasesConfig(BaseModel):
    """Configuration for all phases."""

    preflight: PhaseConfig = Field(default_factory=lambda: PhaseConfig(timeout=60, max_turns=1))
    setup: PhaseConfig = Field(default_factory=lambda: PhaseConfig(timeout=120, max_turns=1))
    research: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=25, estimated_cost=0.5)
    )
    planning: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=600, max_turns=20, estimated_cost=1.0)
    )
    implementation: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=3600, max_turns=100, estimated_cost=3.0)
    )
    test_writing: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=1200, max_turns=50, estimated_cost=1.5)
    )
    test_execution: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(
            timeout=1800, max_turns=60, max_iterations=5, estimated_cost=2.0
        )
    )
    code_review: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=600, max_turns=30, estimated_cost=1.0)
    )
    fix_review_issues: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=900, max_turns=40, estimated_cost=1.0)
    )
    lint_check: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=20, estimated_cost=0.5)
    )
    documentation: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=600, max_turns=30, estimated_cost=0.5)
    )
    final_verification: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=15, estimated_cost=0.5)
    )
    commit_prep: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=10, estimated_cost=0.3)
    )
    conflict_check: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=20, estimated_cost=0.5)
    )
    pr_creation: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=300, max_turns=15, estimated_cost=0.3)
    )
    pr_self_review: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=600, max_turns=20, estimated_cost=0.5)
    )


class ApprovalGatesConfig(BaseModel):
    """Configuration for approval gates."""

    planning: bool = Field(default=True)
    implementation: bool = Field(default=False)
    pr_creation: bool = Field(default=False)


class ApprovalsConfig(BaseModel):
    """Configuration for the approval system."""

    enabled: bool = Field(default=True)
    timeout_hours: float = Field(default=24.0, ge=0.1)
    gates: ApprovalGatesConfig = Field(default_factory=ApprovalGatesConfig)


class ConsoleNotificationConfig(BaseModel):
    """Console notification settings."""

    enabled: bool = Field(default=True)
    colors: bool = Field(default=True)


class WebhookNotificationConfig(BaseModel):
    """Webhook notification settings."""

    enabled: bool = Field(default=False)
    url: str | None = Field(default=None)
    events: list[str] = Field(
        default_factory=lambda: ["workflow_complete", "workflow_failed", "approval_needed"]
    )


class NotificationsConfig(BaseModel):
    """Configuration for notifications."""

    console: ConsoleNotificationConfig = Field(default_factory=ConsoleNotificationConfig)
    webhook: WebhookNotificationConfig = Field(default_factory=WebhookNotificationConfig)


class CommandsConfig(BaseModel):
    """Language-agnostic command overrides."""

    lint: str | None = Field(default=None)
    typecheck: str | None = Field(default=None)
    test: str | None = Field(default=None)
    build: str | None = Field(default=None)


class WorkflowConfig(BaseModel):
    """Main configuration for SelfAssembler workflows."""

    budget_limit_usd: float = Field(default=15.0, ge=0.0)
    autonomous_mode: bool = Field(default=False)
    plans_dir: str = Field(default="./plans")

    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    phases: PhasesConfig = Field(default_factory=PhasesConfig)
    approvals: ApprovalsConfig = Field(default_factory=ApprovalsConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    copy_files: list[str] = Field(default_factory=lambda: [".env", ".env.local", ".claude/*"])

    @classmethod
    def load(cls, config_path: Path | None = None) -> "WorkflowConfig":
        """Load configuration from a YAML file."""
        if config_path is None:
            # Search for config file in standard locations
            search_paths = [
                Path("selfassembler.yaml"),
                Path("selfassembler.yml"),
                Path(".selfassembler.yaml"),
                Path(".selfassembler.yml"),
            ]
            for path in search_paths:
                if path.exists():
                    config_path = path
                    break

        if config_path and config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return cls.model_validate(data)

        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return self.model_dump()

    def save(self, config_path: Path) -> None:
        """Save configuration to a YAML file."""
        with open(config_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def get_phase_config(self, phase_name: str) -> PhaseConfig:
        """Get configuration for a specific phase."""
        phase_name_normalized = phase_name.replace("-", "_")
        return getattr(self.phases, phase_name_normalized, PhaseConfig())
