"""Tests for configuration module."""

import tempfile
from pathlib import Path

from selfassembler.config import RulesConfig, StreamingConfig, WorkflowConfig


class TestWorkflowConfig:
    """Tests for WorkflowConfig."""

    def test_default_config(self):
        """Test that default config loads correctly."""
        config = WorkflowConfig()
        assert config.budget_limit_usd == 15.0
        assert config.autonomous_mode is False
        assert config.git.base_branch == "main"
        assert config.approvals.enabled is True

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
