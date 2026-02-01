"""Configuration models for SelfAssembler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for agent CLI execution."""

    type: str = Field(default="claude")  # "claude" or "codex"
    default_timeout: int = Field(default=600, ge=60, le=7200)
    max_turns_default: int = Field(default=50, ge=1, le=500)
    dangerous_mode: bool = Field(default=False)
    model: str | None = Field(default=None)


class ClaudeConfig(BaseModel):
    """Configuration for Claude CLI execution (legacy, for backward compatibility)."""

    default_timeout: int = Field(default=600, ge=60, le=7200)
    max_turns_default: int = Field(default=50, ge=1, le=500)
    dangerous_mode: bool = Field(default=False)


class StreamingConfig(BaseModel):
    """Configuration for streaming output."""

    enabled: bool = Field(default=True)
    verbose: bool = Field(default=True)  # --verbose flag
    debug: str | None = Field(default=None)  # --debug categories
    show_tool_calls: bool = Field(default=True)
    truncate_length: int = Field(default=200)


class GitConfig(BaseModel):
    """Configuration for git operations."""

    base_branch: str = Field(default="main")
    worktree_dir: str = Field(default="../.worktrees")
    branch_prefix: str = Field(default="feature/")
    cleanup_on_fail: bool = Field(default=False)  # Preserve worktree for resume
    cleanup_remote_on_fail: bool = Field(default=False)
    auto_update: bool = Field(default=True)  # Auto-pull and checkout in preflight


class PhaseConfig(BaseModel):
    """Configuration for a specific phase."""

    timeout: int = Field(default=600, ge=60)
    max_turns: int = Field(default=50, ge=1)
    max_iterations: int = Field(default=5, ge=1)  # Iterations within phase (e.g., lint fix loops)
    max_retries: int = Field(default=0, ge=0)  # Phase-level retries on failure
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
    plan_review: PhaseConfig = Field(
        default_factory=lambda: PhaseConfig(timeout=600, max_turns=30, estimated_cost=1.0)
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
        default_factory=lambda: PhaseConfig(
            timeout=300, max_turns=20, estimated_cost=0.5, max_retries=3
        )
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
    plan_review: bool = Field(default=False)
    implementation: bool = Field(default=False)
    pr_creation: bool = Field(default=False)


class ApprovalsConfig(BaseModel):
    """Configuration for the approval system."""

    enabled: bool = Field(default=False)  # Autonomous by default
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


class RulesConfig(BaseModel):
    """Configuration for rules/guidelines written to CLAUDE.md."""

    enabled_rules: list[str] = Field(default_factory=lambda: ["no-signature"])
    custom_rules: list[str] = Field(default_factory=list)


class DebatePhasesConfig(BaseModel):
    """Which phases have debate enabled."""

    research: bool = Field(default=True)
    planning: bool = Field(default=True)
    plan_review: bool = Field(default=True)
    code_review: bool = Field(default=True)


class DebateConfig(BaseModel):
    """Configuration for multi-agent debate system."""

    enabled: bool = Field(default=False)
    max_turns: int = Field(default=3, ge=1, le=5)

    # Agent roles
    primary_agent: str = Field(default="claude")
    secondary_agent: str = Field(default="codex")

    # Phases with debate enabled
    phases: DebatePhasesConfig = Field(default_factory=DebatePhasesConfig)

    # Execution settings
    parallel_turn_1: bool = Field(default=True)
    turn_timeout_seconds: int = Field(default=300)

    # Message exchange settings (Turn 2)
    # Must be odd so primary agent always closes the debate
    max_exchange_messages: int = Field(default=3, ge=3, le=5)
    message_timeout_seconds: int = Field(default=180)

    # Output settings
    keep_intermediate_files: bool = Field(default=True)
    debate_subdir: str = Field(default="debates")

    # Synthesis settings
    include_attribution: bool = Field(default=True)
    max_unresolved_conflicts: int = Field(default=5)


class WorkflowConfig(BaseModel):
    """Main configuration for SelfAssembler workflows."""

    budget_limit_usd: float = Field(default=15.0, ge=0.0)
    autonomous_mode: bool = Field(default=False)
    plans_dir: str = Field(default="./plans")

    agent: AgentConfig = Field(default_factory=AgentConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)  # Legacy, for backward compat
    git: GitConfig = Field(default_factory=GitConfig)
    phases: PhasesConfig = Field(default_factory=PhasesConfig)
    approvals: ApprovalsConfig = Field(default_factory=ApprovalsConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    debate: DebateConfig = Field(default_factory=DebateConfig)
    copy_files: list[str] = Field(default_factory=lambda: [".env", ".env.local", ".claude/*"])

    @classmethod
    def load(cls, config_path: Path | None = None) -> WorkflowConfig:
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

    def get_effective_agent_config(self) -> AgentConfig:
        """
        Get the effective agent configuration.

        Merges legacy claude config into agent config if agent.type is "claude"
        and certain fields haven't been explicitly set.

        Returns:
            AgentConfig with effective values
        """
        # Start with the agent config
        effective = self.agent.model_copy()

        # If using claude agent, merge legacy claude config values
        if effective.type == "claude":
            # Only override if agent config has defaults (600, 50, False)
            # This ensures explicit agent config values take precedence
            if effective.default_timeout == 600 and self.claude.default_timeout != 600:
                effective.default_timeout = self.claude.default_timeout
            if effective.max_turns_default == 50 and self.claude.max_turns_default != 50:
                effective.max_turns_default = self.claude.max_turns_default
            if not effective.dangerous_mode and self.claude.dangerous_mode:
                effective.dangerous_mode = self.claude.dangerous_mode

        return effective
