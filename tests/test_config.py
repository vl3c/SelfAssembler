"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest

from selfassembler.config import WorkflowConfig


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
