"""Tests for executor factory and registry."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from selfassembler.executors import (
    EXECUTOR_REGISTRY,
    AgentExecutor,
    ClaudeExecutor,
    CodexExecutor,
    create_executor,
    get_executor_class,
    list_available_agents,
    register_executor,
)
from selfassembler.executors.base import ExecutionResult


class TestExecutorRegistry:
    """Tests for EXECUTOR_REGISTRY."""

    def test_registry_is_dict(self):
        """Test registry is a dictionary."""
        assert isinstance(EXECUTOR_REGISTRY, dict)

    def test_claude_registered(self):
        """Test Claude executor is registered."""
        assert "claude" in EXECUTOR_REGISTRY
        assert EXECUTOR_REGISTRY["claude"] is ClaudeExecutor

    def test_codex_registered(self):
        """Test Codex executor is registered."""
        assert "codex" in EXECUTOR_REGISTRY
        assert EXECUTOR_REGISTRY["codex"] is CodexExecutor

    def test_default_agents_available(self):
        """Test default agents are available."""
        agents = list(EXECUTOR_REGISTRY.keys())
        assert "claude" in agents
        assert "codex" in agents


class TestGetExecutorClass:
    """Tests for get_executor_class function."""

    def test_get_claude_class(self):
        """Test getting Claude executor class."""
        cls = get_executor_class("claude")
        assert cls is ClaudeExecutor

    def test_get_codex_class(self):
        """Test getting Codex executor class."""
        cls = get_executor_class("codex")
        assert cls is CodexExecutor

    def test_unknown_agent_raises(self):
        """Test unknown agent type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_executor_class("unknown_agent")

        error_msg = str(exc_info.value)
        assert "Unknown agent type" in error_msg
        assert "unknown_agent" in error_msg
        assert "claude" in error_msg  # Should list available types

    def test_case_sensitive(self):
        """Test agent type is case sensitive."""
        with pytest.raises(ValueError):
            get_executor_class("Claude")

        with pytest.raises(ValueError):
            get_executor_class("CODEX")


class TestRegisterExecutor:
    """Tests for register_executor function."""

    def test_register_new_executor(self):
        """Test registering a new executor type."""

        # Create a mock executor class
        class CustomExecutor(AgentExecutor):
            AGENT_TYPE = "custom"
            CLI_COMMAND = "custom-cli"

            def execute(self, prompt, **kwargs):
                return ExecutionResult(
                    session_id="",
                    output="",
                    cost_usd=0.0,
                    duration_ms=0,
                    num_turns=0,
                    is_error=False,
                    raw_output="",
                )

            def check_available(self):
                return True, "v1.0"

            def _build_command(self, prompt, **kwargs):
                return ["custom-cli", prompt]

        # Register it
        register_executor("custom", CustomExecutor)

        # Verify it's registered
        assert "custom" in EXECUTOR_REGISTRY
        assert EXECUTOR_REGISTRY["custom"] is CustomExecutor

        # Clean up
        del EXECUTOR_REGISTRY["custom"]

    def test_register_overwrites_existing(self):
        """Test registering overwrites existing registration."""
        original = EXECUTOR_REGISTRY.get("claude")

        class FakeClaudeExecutor(ClaudeExecutor):
            pass

        register_executor("claude", FakeClaudeExecutor)
        assert EXECUTOR_REGISTRY["claude"] is FakeClaudeExecutor

        # Restore original
        register_executor("claude", original)


class TestCreateExecutor:
    """Tests for create_executor function."""

    def test_create_claude_executor(self):
        """Test creating a Claude executor."""
        executor = create_executor(
            agent_type="claude",
            working_dir=Path("/test"),
        )

        assert isinstance(executor, ClaudeExecutor)
        assert executor.working_dir == Path("/test")

    def test_create_codex_executor(self):
        """Test creating a Codex executor."""
        executor = create_executor(
            agent_type="codex",
            working_dir=Path("/test"),
        )

        assert isinstance(executor, CodexExecutor)
        assert executor.working_dir == Path("/test")

    def test_create_with_all_params(self):
        """Test creating executor with all parameters."""
        callback = MagicMock()

        executor = create_executor(
            agent_type="claude",
            working_dir=Path("/test"),
            default_timeout=300,
            model="opus",
            stream=False,
            stream_callback=callback,
            verbose=False,
            debug="api",
        )

        assert executor.default_timeout == 300
        assert executor.model == "opus"
        assert executor.stream is False
        assert executor.stream_callback is callback
        assert executor.verbose is False
        assert executor.debug == "api"

    def test_create_unknown_agent_raises(self):
        """Test creating unknown agent type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            create_executor(
                agent_type="unknown",
                working_dir=Path("."),
            )

        assert "Unknown agent type" in str(exc_info.value)

    def test_create_passes_kwargs(self):
        """Test that additional kwargs are passed to executor."""
        # This tests the **kwargs behavior
        executor = create_executor(
            agent_type="claude",
            working_dir=Path("."),
            default_timeout=120,
        )

        assert executor.default_timeout == 120


class TestListAvailableAgents:
    """Tests for list_available_agents function."""

    def test_returns_list(self):
        """Test function returns a list."""
        agents = list_available_agents()
        assert isinstance(agents, list)

    def test_contains_default_agents(self):
        """Test list contains default agents."""
        agents = list_available_agents()
        assert "claude" in agents
        assert "codex" in agents

    def test_matches_registry_keys(self):
        """Test list matches registry keys."""
        agents = list_available_agents()
        registry_keys = list(EXECUTOR_REGISTRY.keys())
        assert sorted(agents) == sorted(registry_keys)


class TestExecutorsPackageExports:
    """Tests for executors package exports."""

    def test_import_agent_executor(self):
        """Test AgentExecutor can be imported from package."""
        from selfassembler.executors import AgentExecutor

        assert AgentExecutor is not None

    def test_import_execution_result(self):
        """Test ExecutionResult can be imported from package."""
        from selfassembler.executors import ExecutionResult

        assert ExecutionResult is not None

    def test_import_stream_event(self):
        """Test StreamEvent can be imported from package."""
        from selfassembler.executors import StreamEvent

        assert StreamEvent is not None

    def test_import_claude_executor(self):
        """Test ClaudeExecutor can be imported from package."""
        from selfassembler.executors import ClaudeExecutor

        assert ClaudeExecutor is not None

    def test_import_mock_claude_executor(self):
        """Test MockClaudeExecutor can be imported from package."""
        from selfassembler.executors import MockClaudeExecutor

        assert MockClaudeExecutor is not None

    def test_import_codex_executor(self):
        """Test CodexExecutor can be imported from package."""
        from selfassembler.executors import CodexExecutor

        assert CodexExecutor is not None

    def test_import_mock_codex_executor(self):
        """Test MockCodexExecutor can be imported from package."""
        from selfassembler.executors import MockCodexExecutor

        assert MockCodexExecutor is not None

    def test_import_factory_functions(self):
        """Test factory functions can be imported from package."""
        from selfassembler.executors import (
            EXECUTOR_REGISTRY,
            create_executor,
            get_executor_class,
            list_available_agents,
            register_executor,
        )

        assert create_executor is not None
        assert get_executor_class is not None
        assert register_executor is not None
        assert list_available_agents is not None
        assert EXECUTOR_REGISTRY is not None


class TestBackwardCompatibility:
    """Tests for backward compatibility with old import paths."""

    def test_import_from_executor_module(self):
        """Test importing from selfassembler.executor still works."""
        from selfassembler.executor import (
            ClaudeExecutor,
            ExecutionResult,
            MockClaudeExecutor,
            StreamEvent,
        )

        assert ClaudeExecutor is not None
        assert MockClaudeExecutor is not None
        assert ExecutionResult is not None
        assert StreamEvent is not None

    def test_executor_module_same_classes(self):
        """Test executor module exports same classes as executors package."""
        from selfassembler.executor import ClaudeExecutor as OldClaudeExecutor
        from selfassembler.executor import ExecutionResult as OldExecutionResult
        from selfassembler.executors import ClaudeExecutor as NewClaudeExecutor
        from selfassembler.executors import ExecutionResult as NewExecutionResult

        assert OldClaudeExecutor is NewClaudeExecutor
        assert OldExecutionResult is NewExecutionResult


class TestDetectInstalledAgents:
    """Tests for detect_installed_agents function."""

    def test_returns_dict(self):
        """Test function returns a dictionary."""
        from selfassembler.executors import detect_installed_agents

        result = detect_installed_agents()
        assert isinstance(result, dict)

    def test_contains_registered_agents(self):
        """Test result contains all registered agents."""
        from selfassembler.executors import detect_installed_agents, list_available_agents

        result = detect_installed_agents()
        for agent in list_available_agents():
            assert agent in result
            assert isinstance(result[agent], bool)


class TestGetAvailableAgents:
    """Tests for get_available_agents function."""

    def test_returns_list(self):
        """Test function returns a list."""
        from selfassembler.executors import get_available_agents

        result = get_available_agents()
        assert isinstance(result, list)

    def test_only_installed_agents(self):
        """Test only returns installed agents."""
        from selfassembler.executors import detect_installed_agents, get_available_agents

        available = get_available_agents()
        installed = detect_installed_agents()

        for agent in available:
            assert installed[agent] is True


class TestAutoConfigureAgents:
    """Tests for auto_configure_agents function."""

    def test_returns_tuple(self):
        """Test function returns a tuple."""
        from selfassembler.executors import auto_configure_agents

        result = auto_configure_agents()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_tuple_structure(self):
        """Test tuple has correct types."""
        from selfassembler.executors import auto_configure_agents

        primary, secondary, debate_enabled = auto_configure_agents()

        assert isinstance(primary, str)
        assert secondary is None or isinstance(secondary, str)
        assert isinstance(debate_enabled, bool)

    def test_primary_is_valid_agent(self):
        """Test primary agent is a valid registered type."""
        from selfassembler.executors import auto_configure_agents, list_available_agents

        primary, _, _ = auto_configure_agents()
        assert primary in list_available_agents()

    def test_debate_enabled_when_secondary_set(self):
        """Test debate is enabled only when secondary agent exists."""
        from selfassembler.executors import auto_configure_agents

        _, secondary, debate_enabled = auto_configure_agents()

        if secondary is not None:
            assert debate_enabled is True
        # Note: debate can be False even when secondary is None


class TestAutoDetectionPackageExports:
    """Tests for new auto-detection exports."""

    def test_import_detect_installed_agents(self):
        """Test detect_installed_agents can be imported."""
        from selfassembler.executors import detect_installed_agents

        assert detect_installed_agents is not None

    def test_import_get_available_agents(self):
        """Test get_available_agents can be imported."""
        from selfassembler.executors import get_available_agents

        assert get_available_agents is not None

    def test_import_auto_configure_agents(self):
        """Test auto_configure_agents can be imported."""
        from selfassembler.executors import auto_configure_agents

        assert auto_configure_agents is not None
