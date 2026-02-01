"""Tests for configuration module."""

import tempfile
from pathlib import Path

from selfassembler.config import (
    AgentConfig,
    ClaudeConfig,
    GitConfig,
    RulesConfig,
    StreamingConfig,
    WorkflowConfig,
)


class TestWorkflowConfig:
    """Tests for WorkflowConfig."""

    def test_default_config(self):
        """Test that default config loads correctly."""
        config = WorkflowConfig()
        assert config.budget_limit_usd == 15.0
        assert config.autonomous_mode is False
        assert config.git.base_branch == "main"
        assert config.approvals.enabled is False  # Autonomous by default

    def test_load_nonexistent_file(self):
        """Test loading returns defaults when file doesn't exist."""
        config = WorkflowConfig.load(Path("/nonexistent/config.yaml"))
        assert config.budget_limit_usd == 15.0

    def test_save_and_load(self):
        """Test saving and loading config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Create and save config
            config = WorkflowConfig(budget_limit_usd=25.0)
            config.git.branch_prefix = "test/"
            config.save(config_path)

            # Load and verify
            loaded = WorkflowConfig.load(config_path)
            assert loaded.budget_limit_usd == 25.0
            assert loaded.git.branch_prefix == "test/"

    def test_get_phase_config(self):
        """Test getting phase configuration."""
        config = WorkflowConfig()

        planning = config.get_phase_config("planning")
        assert planning.timeout == 600
        assert planning.max_turns == 20

        test_exec = config.get_phase_config("test_execution")
        assert test_exec.max_iterations == 5

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = WorkflowConfig()
        data = config.to_dict()

        assert "budget_limit_usd" in data
        assert "claude" in data
        assert "git" in data
        assert "phases" in data


class TestStreamingConfig:
    """Tests for streaming configuration."""

    def test_default_config(self):
        """Test streaming defaults."""
        config = StreamingConfig()
        assert config.enabled is True
        assert config.verbose is True
        assert config.debug is None
        assert config.show_tool_calls is True
        assert config.truncate_length == 200

    def test_in_workflow_config(self):
        """Test streaming config in workflow config."""
        config = WorkflowConfig()
        assert config.streaming.enabled is True
        assert config.streaming.verbose is True

    def test_custom_values(self):
        """Test custom streaming config values."""
        config = StreamingConfig(
            enabled=False,
            verbose=False,
            debug="api,mcp",
            truncate_length=100,
        )
        assert config.enabled is False
        assert config.debug == "api,mcp"
        assert config.truncate_length == 100


class TestPhaseConfig:
    """Tests for phase configuration."""

    def test_phase_defaults(self):
        """Test that all phases have sensible defaults."""
        config = WorkflowConfig()

        # Check all phases exist
        phase_names = [
            "preflight",
            "setup",
            "research",
            "planning",
            "plan_review",
            "implementation",
            "test_writing",
            "test_execution",
            "code_review",
            "fix_review_issues",
            "lint_check",
            "documentation",
            "final_verification",
            "commit_prep",
            "conflict_check",
            "pr_creation",
            "pr_self_review",
        ]

        for name in phase_names:
            phase = config.get_phase_config(name)
            assert phase.timeout > 0
            assert phase.enabled is True

    def test_plan_review_approval_gate(self):
        """Test plan review approval gate is disabled by default."""
        config = WorkflowConfig()
        assert config.approvals.gates.plan_review is False


class TestRulesConfig:
    """Tests for RulesConfig."""

    def test_default_config(self):
        """Test RulesConfig defaults."""
        config = RulesConfig()
        assert config.enabled_rules == ["no-signature"]
        assert config.custom_rules == []

    def test_in_workflow_config(self):
        """Test RulesConfig in WorkflowConfig."""
        config = WorkflowConfig()
        assert config.rules.enabled_rules == ["no-signature"]
        assert config.rules.custom_rules == []

    def test_custom_enabled_rules(self):
        """Test custom enabled rules."""
        config = RulesConfig(enabled_rules=["no-emojis", "no-yapping"])
        assert config.enabled_rules == ["no-emojis", "no-yapping"]

    def test_custom_rules_list(self):
        """Test custom rules list."""
        custom = ["Custom rule 1", "Custom rule 2"]
        config = RulesConfig(custom_rules=custom)
        assert config.custom_rules == custom

    def test_empty_enabled_rules(self):
        """Test empty enabled rules list."""
        config = RulesConfig(enabled_rules=[])
        assert config.enabled_rules == []

    def test_rules_in_to_dict(self):
        """Test rules config appears in to_dict output."""
        config = WorkflowConfig()
        data = config.to_dict()
        assert "rules" in data
        assert "enabled_rules" in data["rules"]
        assert "custom_rules" in data["rules"]

    def test_save_and_load_rules(self):
        """Test saving and loading rules configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Create config with custom rules
            config = WorkflowConfig()
            config.rules.enabled_rules = ["no-emojis", "no-yapping"]
            config.rules.custom_rules = ["Custom rule here"]
            config.save(config_path)

            # Load and verify
            loaded = WorkflowConfig.load(config_path)
            assert loaded.rules.enabled_rules == ["no-emojis", "no-yapping"]
            assert loaded.rules.custom_rules == ["Custom rule here"]


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_default_config(self):
        """Test AgentConfig defaults."""
        config = AgentConfig()
        assert config.type == "claude"
        assert config.default_timeout == 600
        assert config.max_turns_default == 50
        assert config.dangerous_mode is False
        assert config.model is None

    def test_custom_values(self):
        """Test AgentConfig with custom values."""
        config = AgentConfig(
            type="codex",
            default_timeout=300,
            max_turns_default=100,
            dangerous_mode=True,
            model="gpt-4",
        )
        assert config.type == "codex"
        assert config.default_timeout == 300
        assert config.max_turns_default == 100
        assert config.dangerous_mode is True
        assert config.model == "gpt-4"

    def test_in_workflow_config(self):
        """Test AgentConfig in WorkflowConfig."""
        config = WorkflowConfig()
        assert config.agent.type == "claude"
        assert config.agent.default_timeout == 600

    def test_agent_in_to_dict(self):
        """Test agent config appears in to_dict output."""
        config = WorkflowConfig()
        data = config.to_dict()
        assert "agent" in data
        assert "type" in data["agent"]
        assert data["agent"]["type"] == "claude"

    def test_timeout_validation(self):
        """Test timeout validation (min 60, max 7200)."""
        import pytest
        from pydantic import ValidationError

        # Valid values
        AgentConfig(default_timeout=60)
        AgentConfig(default_timeout=7200)

        # Invalid values
        with pytest.raises(ValidationError):
            AgentConfig(default_timeout=59)
        with pytest.raises(ValidationError):
            AgentConfig(default_timeout=7201)

    def test_max_turns_validation(self):
        """Test max_turns_default validation (min 1, max 500)."""
        import pytest
        from pydantic import ValidationError

        # Valid values
        AgentConfig(max_turns_default=1)
        AgentConfig(max_turns_default=500)

        # Invalid values
        with pytest.raises(ValidationError):
            AgentConfig(max_turns_default=0)
        with pytest.raises(ValidationError):
            AgentConfig(max_turns_default=501)


class TestClaudeConfigBackwardCompatibility:
    """Tests for backward compatibility with ClaudeConfig."""

    def test_claude_config_exists(self):
        """Test ClaudeConfig still exists."""
        config = ClaudeConfig()
        assert config.default_timeout == 600
        assert config.max_turns_default == 50
        assert config.dangerous_mode is False

    def test_claude_config_in_workflow(self):
        """Test ClaudeConfig is still in WorkflowConfig."""
        config = WorkflowConfig()
        assert hasattr(config, "claude")
        assert isinstance(config.claude, ClaudeConfig)

    def test_both_agent_and_claude_exist(self):
        """Test both agent and claude configs exist in WorkflowConfig."""
        config = WorkflowConfig()
        assert hasattr(config, "agent")
        assert hasattr(config, "claude")


class TestGetEffectiveAgentConfig:
    """Tests for get_effective_agent_config method."""

    def test_default_returns_agent_config(self):
        """Test default returns agent config values."""
        config = WorkflowConfig()
        effective = config.get_effective_agent_config()

        assert effective.type == "claude"
        assert effective.default_timeout == 600
        assert effective.max_turns_default == 50

    def test_merges_legacy_claude_config(self):
        """Test legacy claude config is merged when using claude agent."""
        config = WorkflowConfig()
        config.claude.default_timeout = 900
        config.claude.max_turns_default = 75
        config.claude.dangerous_mode = True

        effective = config.get_effective_agent_config()

        # Legacy values should be merged
        assert effective.default_timeout == 900
        assert effective.max_turns_default == 75
        assert effective.dangerous_mode is True

    def test_agent_config_overrides_legacy(self):
        """Test agent config values take precedence over legacy."""
        config = WorkflowConfig()
        # Set agent config to non-default values
        config.agent.default_timeout = 1200
        config.claude.default_timeout = 900

        effective = config.get_effective_agent_config()

        # Agent config should take precedence
        assert effective.default_timeout == 1200

    def test_codex_agent_ignores_legacy(self):
        """Test codex agent doesn't merge legacy claude config."""
        config = WorkflowConfig()
        config.agent.type = "codex"
        config.claude.default_timeout = 900

        effective = config.get_effective_agent_config()

        # Should use agent config defaults, not legacy
        assert effective.type == "codex"
        assert effective.default_timeout == 600  # Default, not 900

    def test_returns_copy(self):
        """Test returns a copy, not the original."""
        config = WorkflowConfig()
        effective1 = config.get_effective_agent_config()
        effective2 = config.get_effective_agent_config()

        effective1.default_timeout = 999

        # Original should be unchanged
        assert config.agent.default_timeout == 600
        # Second call should return fresh copy
        assert effective2.default_timeout == 600

    def test_model_preserved(self):
        """Test model value is preserved."""
        config = WorkflowConfig()
        config.agent.model = "opus"

        effective = config.get_effective_agent_config()

        assert effective.model == "opus"


class TestGitConfig:
    """Tests for GitConfig including new auto_update option."""

    def test_default_config(self):
        """Test GitConfig defaults."""
        config = GitConfig()
        assert config.base_branch == "main"
        assert config.worktree_dir == "../.worktrees"
        assert config.branch_prefix == "feature/"
        assert config.cleanup_on_fail is False
        assert config.cleanup_remote_on_fail is False
        assert config.auto_update is True

    def test_auto_update_in_workflow(self):
        """Test auto_update is accessible in WorkflowConfig."""
        config = WorkflowConfig()
        assert config.git.auto_update is True

    def test_auto_update_can_be_disabled(self):
        """Test auto_update can be disabled."""
        config = GitConfig(auto_update=False)
        assert config.auto_update is False

    def test_git_config_in_to_dict(self):
        """Test git config appears in to_dict output."""
        config = WorkflowConfig()
        data = config.to_dict()
        assert "git" in data
        assert "auto_update" in data["git"]
        assert data["git"]["auto_update"] is True

    def test_save_and_load_git_config(self):
        """Test saving and loading git configuration with auto_update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Create config with auto_update disabled
            config = WorkflowConfig()
            config.git.auto_update = False
            config.git.base_branch = "master"
            config.save(config_path)

            # Load and verify
            loaded = WorkflowConfig.load(config_path)
            assert loaded.git.auto_update is False
            assert loaded.git.base_branch == "master"


class TestAgentConfigSaveLoad:
    """Tests for saving and loading AgentConfig."""

    def test_save_and_load_agent_config(self):
        """Test saving and loading agent configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Create config with custom agent settings
            config = WorkflowConfig()
            config.agent.type = "codex"
            config.agent.default_timeout = 300
            config.agent.model = "gpt-4"
            config.save(config_path)

            # Load and verify
            loaded = WorkflowConfig.load(config_path)
            assert loaded.agent.type == "codex"
            assert loaded.agent.default_timeout == 300
            assert loaded.agent.model == "gpt-4"

    def test_load_config_without_agent_section(self):
        """Test loading config that doesn't have agent section uses defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Write config without agent section
            config_path.write_text("budget_limit_usd: 20.0\n")

            # Load and verify defaults are used
            loaded = WorkflowConfig.load(config_path)
            assert loaded.agent.type == "claude"
            assert loaded.agent.default_timeout == 600
