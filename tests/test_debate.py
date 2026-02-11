"""Tests for multi-agent debate system."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from selfassembler.config import DebateConfig, DebatePhasesConfig, WorkflowConfig
from selfassembler.context import WorkflowContext
from selfassembler.debate.files import DebateFileManager
from selfassembler.debate.prompts import (
    CodeReviewDebatePrompts,
    PlanningDebatePrompts,
    PlanReviewDebatePrompts,
    ResearchDebatePrompts,
    get_prompt_generator,
)
from selfassembler.debate.results import (
    DebateMessage,
    DebateResult,
    SynthesisResult,
    Turn1Results,
    Turn2Results,
)
from selfassembler.debate.transcript import DebateLog
from selfassembler.executors.base import ExecutionResult


class TestDebateConfig:
    """Tests for DebateConfig model."""

    def test_default_config(self):
        """Test DebateConfig defaults."""
        config = DebateConfig()
        assert config.enabled is False
        assert config.primary_agent == "claude"
        assert config.secondary_agent == "codex"
        assert config.mode == "feedback"
        assert config.intensity == "low"
        assert config.parallel_turn_1 is True
        assert config.max_exchange_messages == 1  # computed from mode
        assert config.keep_intermediate_files is True

    def test_phases_config(self):
        """Test DebatePhasesConfig defaults."""
        config = DebatePhasesConfig()
        assert config.research is True
        assert config.planning is True
        assert config.plan_review is True
        assert config.code_review is True

    def test_debate_in_workflow_config(self):
        """Test DebateConfig in WorkflowConfig."""
        config = WorkflowConfig()
        assert hasattr(config, "debate")
        assert isinstance(config.debate, DebateConfig)
        assert config.debate.enabled is False

    def test_debate_config_validation(self):
        """Test DebateConfig validation."""
        from pydantic import ValidationError

        # Valid mode/intensity combinations
        DebateConfig(mode="feedback")
        DebateConfig(mode="debate", intensity="low")
        DebateConfig(mode="debate", intensity="high")

        # Invalid values
        with pytest.raises(ValidationError):
            DebateConfig(mode="invalid")
        with pytest.raises(ValidationError):
            DebateConfig(intensity="medium")

    def test_mode_and_intensity(self):
        """Test mode/intensity map to correct max_exchange_messages."""
        # Feedback mode
        config = DebateConfig(mode="feedback")
        assert config.is_feedback_only is True
        assert config.max_exchange_messages == 1

        # Debate low
        config = DebateConfig(mode="debate", intensity="low")
        assert config.is_feedback_only is False
        assert config.max_exchange_messages == 3

        # Debate high
        config = DebateConfig(mode="debate", intensity="high")
        assert config.is_feedback_only is False
        assert config.max_exchange_messages == 5

    def test_debate_config_save_load(self):
        """Test saving and loading debate configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Create config with debate enabled
            config = WorkflowConfig()
            config.debate.enabled = True
            config.debate.mode = "debate"
            config.debate.intensity = "high"
            config.debate.phases.research = False
            config.save(config_path)

            # Load and verify
            loaded = WorkflowConfig.load(config_path)
            assert loaded.debate.enabled is True
            assert loaded.debate.mode == "debate"
            assert loaded.debate.intensity == "high"
            assert loaded.debate.max_exchange_messages == 5
            assert loaded.debate.phases.research is False


class TestDebateFileManager:
    """Tests for DebateFileManager."""

    def test_file_paths(self):
        """Test file path generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir) / "plans"
            plans_dir.mkdir()

            manager = DebateFileManager(plans_dir, "test-task")

            # Test Turn 1 paths
            assert manager.get_claude_t1_path("research").name == "research-test-task-claude.md"
            assert manager.get_codex_t1_path("research").name == "research-test-task-codex.md"

            # Test debate path
            assert manager.get_debate_path("research").name == "research-test-task-debate.md"
            assert "debates" in str(manager.get_debate_path("research"))

            # Test final output path
            assert manager.get_final_output_path("research").name == "research-test-task.md"

    def test_phase_specific_paths(self):
        """Test phase-specific path helpers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir) / "plans"
            plans_dir.mkdir()

            manager = DebateFileManager(plans_dir, "mytask")

            # Research paths - use role-based keys (not agent names)
            research = manager.get_research_paths()
            assert "primary_t1" in research
            assert "secondary_t1" in research
            assert "debate" in research
            assert "final" in research

            # Planning paths - verify role-based naming
            planning = manager.get_planning_paths()
            assert "plan-mytask-primary.md" in str(planning["primary_t1"])

    def test_ensure_directories(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir) / "plans"

            manager = DebateFileManager(plans_dir, "task")
            manager.ensure_directories()

            assert plans_dir.exists()
            assert (plans_dir / "debates").exists()


class TestDebateLog:
    """Tests for DebateLog transcript management."""

    def test_write_header(self):
        """Test writing debate header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            log = DebateLog(log_path)
            log.write_header("research", "Test task")

            content = log_path.read_text()
            assert "Debate Transcript: research" in content
            assert "Task: Test task" in content
            assert "Claude (Primary)" in content

    def test_append_message(self):
        """Test appending messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            log = DebateLog(log_path, total_messages=3)
            log.write_header("research", "Test task")
            log.append_message("claude", 1, "First message content")
            log.append_message("codex", 2, "Second message content")

            content = log.get_transcript()
            assert "[MESSAGE 1/3]" in content
            assert "Claude" in content
            assert "First message content" in content
            assert "[MESSAGE 2/3]" in content
            assert "Codex" in content

    def test_get_messages(self):
        """Test getting messages by speaker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            log = DebateLog(log_path, total_messages=3)
            log.write_header("research", "Test task")
            log.append_message("claude", 1, "Claude msg 1")
            log.append_message("codex", 2, "Codex msg")
            log.append_message("claude", 3, "Claude msg 2")

            claude_msgs = log.get_agent_messages("claude")
            codex_msgs = log.get_agent_messages("codex")

            assert len(claude_msgs) == 2
            assert len(codex_msgs) == 1
            assert claude_msgs[0].content == "Claude msg 1"
            assert codex_msgs[0].content == "Codex msg"

    def test_write_synthesis_summary(self):
        """Test synthesis summary generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            log = DebateLog(log_path, total_messages=3)
            log.write_header("research", "Test task")
            log.append_message("claude", 1, "Message 1")
            log.write_synthesis_summary()

            content = log_path.read_text()
            assert "Synthesis Input Summary" in content
            assert "Messages Exchanged" in content


class TestTurn1Results:
    """Tests for Turn1Results dataclass."""

    def test_total_cost(self):
        """Test total cost calculation."""
        result = Turn1Results(
            primary_result=ExecutionResult(
                session_id="s1",
                output="out",
                cost_usd=0.5,
                duration_ms=1000,
                num_turns=5,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=ExecutionResult(
                session_id="s2",
                output="out",
                cost_usd=0.3,
                duration_ms=800,
                num_turns=3,
                is_error=False,
                raw_output="{}",
            ),
            primary_output_file=Path("/tmp/claude.md"),
            secondary_output_file=Path("/tmp/codex.md"),
            primary_agent="claude",
            secondary_agent="codex",
        )

        assert result.total_cost == 0.8

    def test_get_agent_result(self):
        """Test getting result by agent name."""
        primary_result = ExecutionResult(
            session_id="claude-session",
            output="claude output",
            cost_usd=0.5,
            duration_ms=1000,
            num_turns=5,
            is_error=False,
            raw_output="{}",
        )
        secondary_result = ExecutionResult(
            session_id="codex-session",
            output="codex output",
            cost_usd=0.3,
            duration_ms=800,
            num_turns=3,
            is_error=False,
            raw_output="{}",
        )

        result = Turn1Results(
            primary_result=primary_result,
            secondary_result=secondary_result,
            primary_output_file=Path("/tmp/claude.md"),
            secondary_output_file=Path("/tmp/codex.md"),
            primary_agent="claude",
            secondary_agent="codex",
        )

        assert result.get("claude").session_id == "claude-session"
        assert result.get("codex").session_id == "codex-session"


class TestTurn2Results:
    """Tests for Turn2Results dataclass."""

    def test_message_tracking(self):
        """Test message tracking in Turn2Results."""
        msg1 = DebateMessage(
            speaker="claude",
            message_number=1,
            content="Message 1",
            role="primary",
            result=ExecutionResult(
                session_id="s1",
                output="m1",
                cost_usd=0.2,
                duration_ms=500,
                num_turns=2,
                is_error=False,
                raw_output="{}",
            ),
        )
        msg2 = DebateMessage(
            speaker="codex",
            message_number=2,
            content="Message 2",
            role="secondary",
            result=ExecutionResult(
                session_id="s2",
                output="m2",
                cost_usd=0.15,
                duration_ms=400,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
        )

        result = Turn2Results(messages=[msg1, msg2])

        assert result.message_count == 2
        assert result.total_cost == 0.35
        assert len(result.get_agent_messages("claude")) == 1
        assert len(result.get_agent_messages("codex")) == 1


class TestDebateResult:
    """Tests for DebateResult dataclass."""

    def test_cost_breakdown(self):
        """Test cost breakdown by agent."""
        turn1 = Turn1Results(
            primary_result=ExecutionResult(
                session_id="s1",
                output="out",
                cost_usd=0.5,
                duration_ms=1000,
                num_turns=5,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=ExecutionResult(
                session_id="s2",
                output="out",
                cost_usd=0.3,
                duration_ms=800,
                num_turns=3,
                is_error=False,
                raw_output="{}",
            ),
            primary_output_file=Path("/tmp/claude.md"),
            secondary_output_file=Path("/tmp/codex.md"),
            primary_agent="claude",
            secondary_agent="codex",
        )

        synthesis = SynthesisResult(
            result=ExecutionResult(
                session_id="synth",
                output="synthesis",
                cost_usd=0.4,
                duration_ms=600,
                num_turns=4,
                is_error=False,
                raw_output="{}",
            ),
            output_file=Path("/tmp/final.md"),
        )

        result = DebateResult(
            success=True,
            phase_name="research",
            final_output_file=Path("/tmp/final.md"),
            turn1=turn1,
            turn2=Turn2Results(messages=[]),
            synthesis=synthesis,
        )

        # Primary cost: Turn 1 (0.5) + Synthesis (0.4) = 0.9
        assert abs(result.primary_cost - 0.9) < 0.001
        # Secondary cost: Turn 1 (0.3) = 0.3
        assert abs(result.secondary_cost - 0.3) < 0.001
        # Total: 0.5 + 0.3 + 0.4 = 1.2
        assert abs(result.total_cost - 1.2) < 0.001


class TestPromptGenerators:
    """Tests for debate prompt generators."""

    def test_research_prompts(self):
        """Test ResearchDebatePrompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            generator = ResearchDebatePrompts(
                task_description="Implement feature X",
                task_name="feature-x",
                plans_dir=plans_dir,
            )

            # Test Turn 1 prompts
            t1_primary = generator.turn1_primary_prompt(plans_dir / "research-claude.md")
            assert "PRIMARY agent" in t1_primary
            assert "Implement feature X" in t1_primary

            t1_secondary = generator.turn1_secondary_prompt(plans_dir / "research-codex.md")
            assert "SECONDARY agent" in t1_secondary

    def test_code_review_prompts(self):
        """Test CodeReviewDebatePrompts with base_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            generator = CodeReviewDebatePrompts(
                task_description="Fix bug",
                task_name="bugfix",
                plans_dir=plans_dir,
                base_branch="develop",
            )

            prompt = generator.turn1_primary_prompt(plans_dir / "review.md")
            assert "develop" in prompt  # Should use custom base branch

    def test_get_prompt_generator_factory(self):
        """Test get_prompt_generator factory function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            gen = get_prompt_generator(
                phase_name="research",
                task_description="Test",
                task_name="test",
                plans_dir=plans_dir,
            )
            assert isinstance(gen, ResearchDebatePrompts)

            gen = get_prompt_generator(
                phase_name="planning",
                task_description="Test",
                task_name="test",
                plans_dir=plans_dir,
            )
            assert isinstance(gen, PlanningDebatePrompts)

            gen = get_prompt_generator(
                phase_name="code_review",
                task_description="Test",
                task_name="test",
                plans_dir=plans_dir,
                base_branch="main",
            )
            assert isinstance(gen, CodeReviewDebatePrompts)

    def test_invalid_phase_raises_error(self):
        """Test that invalid phase name raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            with pytest.raises(ValueError, match="No prompt generator"):
                get_prompt_generator(
                    phase_name="invalid_phase",
                    task_description="Test",
                    task_name="test",
                    plans_dir=plans_dir,
                )


class TestWorkflowContextDebateSessions:
    """Tests for debate session tracking in WorkflowContext."""

    def test_set_and_get_debate_session(self):
        """Test setting and getting debate session IDs."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )

        # Set Turn 1 sessions
        context.set_debate_session_id("research", "claude", 1, "session-1")
        context.set_debate_session_id("research", "codex", 1, "session-2")

        # Get Turn 1 sessions
        assert context.get_debate_session_id("research", "claude", 1) == "session-1"
        assert context.get_debate_session_id("research", "codex", 1) == "session-2"

    def test_turn2_message_sessions(self):
        """Test Turn 2 message session tracking."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )

        # Set Turn 2 message sessions
        context.set_debate_session_id("research", "claude", 2, "msg1-session", message_num=1)
        context.set_debate_session_id("research", "codex", 2, "msg2-session", message_num=2)
        context.set_debate_session_id("research", "claude", 2, "msg3-session", message_num=3)

        # Get Turn 2 message sessions
        assert context.get_debate_session_id("research", "claude", 2, 1) == "msg1-session"
        assert context.get_debate_session_id("research", "codex", 2, 2) == "msg2-session"
        assert context.get_debate_session_id("research", "claude", 2, 3) == "msg3-session"

    def test_get_synthesis_resume_session(self):
        """Test getting session for synthesis resume."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )

        # Set primary agent's Turn 2 messages (role-based keys)
        context.set_debate_session_id("research", "primary", 2, "msg1-session", message_num=1)
        context.set_debate_session_id("research", "primary", 2, "msg3-session", message_num=3)

        # Should return most recent primary session
        assert context.get_synthesis_resume_session("research") == "msg3-session"

    def test_synthesis_fallback_to_turn1(self):
        """Test synthesis resume falls back to Turn 1 when no Turn 2 sessions."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )

        # Only set Turn 1 session (role-based key)
        context.set_debate_session_id("research", "primary", 1, "t1-session")

        # Should fall back to Turn 1
        assert context.get_synthesis_resume_session("research") == "t1-session"


class TestDebatePhaseIntegration:
    """Integration tests for debate-enabled phases."""

    def test_debate_phase_should_debate_disabled(self):
        """Test _should_debate returns False when debate disabled."""
        from selfassembler.phases import ResearchPhase

        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )
        config = WorkflowConfig()
        config.debate.enabled = False

        mock_executor = MagicMock()
        phase = ResearchPhase(context, mock_executor, config)

        assert phase._should_debate() is False

    def test_debate_phase_should_debate_no_secondary(self):
        """Test _should_debate returns False when no secondary executor."""
        from selfassembler.phases import ResearchPhase

        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )
        config = WorkflowConfig()
        config.debate.enabled = True

        mock_executor = MagicMock()
        phase = ResearchPhase(context, mock_executor, config, secondary_executor=None)

        assert phase._should_debate() is False

    def test_debate_phase_should_debate_enabled(self):
        """Test _should_debate returns True when properly configured."""
        from selfassembler.phases import ResearchPhase

        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )
        config = WorkflowConfig()
        config.debate.enabled = True
        config.debate.phases.research = True

        mock_primary = MagicMock()
        mock_secondary = MagicMock()
        phase = ResearchPhase(context, mock_primary, config, secondary_executor=mock_secondary)

        assert phase._should_debate() is True

    def test_debate_phase_attributes(self):
        """Test debate phase has correct attributes."""
        from selfassembler.phases import (
            CodeReviewPhase,
            PlanningPhase,
            PlanReviewPhase,
            ResearchPhase,
        )

        # All debate-enabled phases should have these attributes
        for phase_class in [ResearchPhase, PlanningPhase, PlanReviewPhase, CodeReviewPhase]:
            assert hasattr(phase_class, "debate_supported")
            assert hasattr(phase_class, "debate_phase_name")
            assert phase_class.debate_supported is True


class TestSameAgentDebate:
    """Tests for same-agent debate support (e.g., Claude vs Claude)."""

    def test_file_manager_uses_roles_not_agent_names(self):
        """Test file paths use roles to avoid collisions in same-agent debates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir) / "plans"
            plans_dir.mkdir()

            manager = DebateFileManager(plans_dir, "task")

            # Get paths for same agent - should be different files
            primary_path = manager.get_role_output_path("research", "primary")
            secondary_path = manager.get_role_output_path("research", "secondary")

            # Paths should be different even if agents are the same
            assert primary_path != secondary_path
            assert "primary" in str(primary_path)
            assert "secondary" in str(secondary_path)

    def test_turn1_results_supports_same_agent(self):
        """Test Turn1Results works when both agents are the same type."""
        primary_result = ExecutionResult(
            session_id="claude-primary-session",
            output="primary output",
            cost_usd=0.5,
            duration_ms=1000,
            num_turns=5,
            is_error=False,
            raw_output="{}",
        )
        secondary_result = ExecutionResult(
            session_id="claude-secondary-session",
            output="secondary output",
            cost_usd=0.3,
            duration_ms=800,
            num_turns=3,
            is_error=False,
            raw_output="{}",
        )

        # Both agents are "claude"
        result = Turn1Results(
            primary_result=primary_result,
            secondary_result=secondary_result,
            primary_output_file=Path("/tmp/research-primary.md"),
            secondary_output_file=Path("/tmp/research-secondary.md"),
            primary_agent="claude",
            secondary_agent="claude",  # Same agent type
        )

        # Should be able to get both results using agent name
        assert result.get("claude").session_id in ["claude-primary-session", "claude-secondary-session"]
        # But primary/secondary should be distinct
        assert result.primary_result.session_id == "claude-primary-session"
        assert result.secondary_result.session_id == "claude-secondary-session"
        assert result.total_cost == 0.8

    def test_turn2_results_supports_same_agent(self):
        """Test Turn2Results works when both agents are the same type."""
        msg1 = DebateMessage(
            speaker="codex",  # Both speakers are codex
            message_number=1,
            content="Primary codex message",
            role="primary",  # Role distinguishes messages in same-agent debates
            result=ExecutionResult(
                session_id="s1",
                output="m1",
                cost_usd=0.2,
                duration_ms=500,
                num_turns=2,
                is_error=False,
                raw_output="{}",
            ),
        )
        msg2 = DebateMessage(
            speaker="codex",  # Both speakers are codex
            message_number=2,
            content="Secondary codex message",
            role="secondary",  # Role distinguishes messages in same-agent debates
            result=ExecutionResult(
                session_id="s2",
                output="m2",
                cost_usd=0.15,
                duration_ms=400,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
        )

        result = Turn2Results(
            messages=[msg1, msg2],
            primary_agent="codex",
            secondary_agent="codex",  # Same agent
        )

        # All messages are from "codex", so get_agent_messages returns all
        assert len(result.get_agent_messages("codex")) == 2
        # But we can distinguish by role
        assert len(result.get_primary_messages()) == 1
        assert len(result.get_secondary_messages()) == 1
        # Verify correct message is returned
        assert result.get_primary_messages()[0].content == "Primary codex message"
        assert result.get_secondary_messages()[0].content == "Secondary codex message"

    def test_prompt_generator_with_same_agent(self):
        """Test prompt generators work with same primary and secondary agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            # Both agents are Claude
            generator = ResearchDebatePrompts(
                task_description="Test task",
                task_name="test",
                plans_dir=plans_dir,
                primary_agent="claude",
                secondary_agent="claude",
            )

            # Both prompts should identify as Claude
            t1_primary = generator.turn1_primary_prompt(plans_dir / "primary.md")
            t1_secondary = generator.turn1_secondary_prompt(plans_dir / "secondary.md")

            assert "PRIMARY agent (Claude)" in t1_primary
            assert "SECONDARY agent (Claude)" in t1_secondary

    def test_debate_config_allows_same_agent(self):
        """Test DebateConfig accepts same agent for primary and secondary."""
        from selfassembler.config import DebateConfig

        # This should not raise an error
        config = DebateConfig(
            enabled=True,
            primary_agent="codex",
            secondary_agent="codex",
        )

        assert config.primary_agent == "codex"
        assert config.secondary_agent == "codex"

    def test_workflow_context_session_tracking_with_roles(self):
        """Test session tracking uses roles to avoid collisions in same-agent debates."""
        context = WorkflowContext(
            task_description="Test",
            task_name="test",
            repo_path=Path("/tmp"),
            plans_dir=Path("/tmp/plans"),
        )

        # Store sessions using roles (as the orchestrator now does)
        context.set_debate_session_id("research", "primary", 1, "primary-t1-session")
        context.set_debate_session_id("research", "secondary", 1, "secondary-t1-session")

        # Should retrieve distinct sessions
        assert context.get_debate_session_id("research", "primary", 1) == "primary-t1-session"
        assert context.get_debate_session_id("research", "secondary", 1) == "secondary-t1-session"

        # Turn 2 messages
        context.set_debate_session_id("research", "primary", 2, "primary-t2-msg1", message_num=1)
        context.set_debate_session_id("research", "secondary", 2, "secondary-t2-msg2", message_num=2)
        context.set_debate_session_id("research", "primary", 2, "primary-t2-msg3", message_num=3)

        assert context.get_debate_session_id("research", "primary", 2, 1) == "primary-t2-msg1"
        assert context.get_debate_session_id("research", "secondary", 2, 2) == "secondary-t2-msg2"
        assert context.get_debate_session_id("research", "primary", 2, 3) == "primary-t2-msg3"

    def test_turn1_results_get_output_file_by_role(self):
        """Test get_output_file_by_role works for same-agent debates."""
        result = Turn1Results(
            primary_result=ExecutionResult(
                session_id="s1",
                output="primary output",
                cost_usd=0.5,
                duration_ms=1000,
                num_turns=5,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=ExecutionResult(
                session_id="s2",
                output="secondary output",
                cost_usd=0.3,
                duration_ms=800,
                num_turns=3,
                is_error=False,
                raw_output="{}",
            ),
            primary_output_file=Path("/tmp/research-primary.md"),
            secondary_output_file=Path("/tmp/research-secondary.md"),
            primary_agent="claude",
            secondary_agent="claude",  # Same agent
        )

        # get_output_file_by_role always returns correct file regardless of agent names
        assert result.get_output_file_by_role("primary") == Path("/tmp/research-primary.md")
        assert result.get_output_file_by_role("secondary") == Path("/tmp/research-secondary.md")

        # Contrast with get_output_file which can't distinguish same-agent
        # (it returns primary for both since primary_agent matches first)
        assert result.get_output_file("claude") == Path("/tmp/research-primary.md")

    def test_debate_log_get_primary_messages_by_role(self):
        """Test DebateLog.get_primary_messages uses role field for same-agent debates."""
        from selfassembler.debate.transcript import DebateLog

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            # Create log for same-agent debate
            log = DebateLog(log_path, total_messages=3, primary_agent="claude", secondary_agent="claude")
            log.write_header("research", "test task")

            # Add messages with role field set
            log.append_message("claude", 1, "Primary message 1", datetime.now(), role="primary")
            log.append_message("claude", 2, "Secondary message", datetime.now(), role="secondary")
            log.append_message("claude", 3, "Primary message 2", datetime.now(), role="primary")

            # get_primary_messages should use role, not speaker name
            primary_msgs = log.get_primary_messages()
            assert len(primary_msgs) == 2
            assert primary_msgs[0].content == "Primary message 1"
            assert primary_msgs[1].content == "Primary message 2"

            secondary_msgs = log.get_secondary_messages()
            assert len(secondary_msgs) == 1
            assert secondary_msgs[0].content == "Secondary message"

    def test_prompt_generator_uses_explicit_role(self):
        """Test prompt generator uses explicit role parameter for same-agent debates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            # Both agents are Claude - same-agent debate
            generator = ResearchDebatePrompts(
                task_description="Test task",
                task_name="test",
                plans_dir=plans_dir,
                primary_agent="claude",
                secondary_agent="claude",
            )

            primary_file = plans_dir / "primary.md"
            secondary_file = plans_dir / "secondary.md"

            # Without explicit role, both would be labeled PRIMARY (bug)
            # With explicit role, correct labels are used
            prompt_primary = generator.debate_message_prompt(
                speaker="claude",
                message_number=1,
                total_messages=3,
                transcript_so_far="",
                own_t1_output=primary_file,
                other_t1_output=secondary_file,
                is_final_message=False,
                role="primary",  # Explicit role
            )
            assert "PRIMARY agent" in prompt_primary

            prompt_secondary = generator.debate_message_prompt(
                speaker="claude",  # Same speaker name
                message_number=2,
                total_messages=3,
                transcript_so_far="",
                own_t1_output=secondary_file,
                other_t1_output=primary_file,
                is_final_message=False,
                role="secondary",  # Explicit role
            )
            assert "SECONDARY agent" in prompt_secondary

    def test_same_agent_session_ids_no_collision(self):
        """get_session_ids() should produce distinct keys when primary == secondary."""
        turn1 = Turn1Results(
            primary_result=ExecutionResult(
                session_id="sess-p",
                output="out",
                cost_usd=0.1,
                duration_ms=100,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=ExecutionResult(
                session_id="sess-s",
                output="out",
                cost_usd=0.1,
                duration_ms=100,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
            primary_output_file=Path("/tmp/p.md"),
            secondary_output_file=Path("/tmp/s.md"),
            primary_agent="claude",
            secondary_agent="claude",
        )

        result = DebateResult(
            success=True,
            phase_name="research",
            final_output_file=Path("/tmp/final.md"),
            turn1=turn1,
            turn2=Turn2Results(messages=[]),
        )

        sessions = result.get_session_ids()
        assert sessions["turn1_primary"] == "sess-p"
        assert sessions["turn1_secondary"] == "sess-s"
        assert len(sessions) == 2  # Both preserved, no overwrite

    def test_same_agent_artifacts_no_collision(self):
        """to_phase_result_artifacts() should produce distinct keys when primary == secondary."""
        turn1 = Turn1Results(
            primary_result=ExecutionResult(
                session_id="sess-p",
                output="out",
                cost_usd=0.1,
                duration_ms=100,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=ExecutionResult(
                session_id="sess-s",
                output="out",
                cost_usd=0.1,
                duration_ms=100,
                num_turns=1,
                is_error=False,
                raw_output="{}",
            ),
            primary_output_file=Path("/tmp/p.md"),
            secondary_output_file=Path("/tmp/s.md"),
            primary_agent="claude",
            secondary_agent="claude",
        )

        result = DebateResult(
            success=True,
            phase_name="research",
            final_output_file=Path("/tmp/final.md"),
            turn1=turn1,
            turn2=Turn2Results(messages=[]),
        )

        artifacts = result.to_phase_result_artifacts()
        assert artifacts["primary_t1_file"] == "/tmp/p.md"
        assert artifacts["secondary_t1_file"] == "/tmp/s.md"
        assert artifacts["primary_agent"] == "claude"
        assert artifacts["secondary_agent"] == "claude"

    def test_same_agent_final_positions_no_collision(self):
        """get_final_positions() should return both positions in same-agent debates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"
            log = DebateLog(log_path, total_messages=2, primary_agent="claude", secondary_agent="claude")
            log.write_header("research", "test")
            log.append_message("claude", 1, "Primary position", role="primary")
            log.append_message("claude", 2, "Secondary position", role="secondary")

            positions = log.get_final_positions()
            assert len(positions) == 2
            assert positions["primary"] == "Primary position"
            assert positions["secondary"] == "Secondary position"


class TestDisplayName:
    """Tests for display_name utility."""

    def test_known_agents(self):
        from selfassembler.debate import display_name

        assert display_name("claude") == "Claude"
        assert display_name("codex") == "Codex"
        assert display_name("gpt-4o") == "GPT-4o"

    def test_unknown_agent_fallback(self):
        from selfassembler.debate import display_name

        assert display_name("my-custom-agent") == "My Custom Agent"


class TestFeedbackOnlyMode:
    """Tests for feedback debate mode (mode='feedback')."""

    def test_turn1_results_without_secondary(self):
        """Test Turn1Results with None secondary fields."""
        result = Turn1Results(
            primary_result=ExecutionResult(
                session_id="s1",
                output="primary output",
                cost_usd=0.5,
                duration_ms=1000,
                num_turns=5,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=None,
            primary_output_file=Path("/tmp/primary.md"),
            secondary_output_file=None,
            primary_agent="claude",
            secondary_agent="codex",
        )

        assert result.total_cost == 0.5
        assert result.secondary_result is None
        assert result.secondary_output_file is None
        assert result.get_output_file_by_role("primary") == Path("/tmp/primary.md")
        assert result.get_output_file_by_role("secondary") is None

    def test_feedback_prompt_generation(self):
        """Test feedback prompt for secondary reviewing primary's work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            generator = ResearchDebatePrompts(
                task_description="Implement feature X",
                task_name="feature-x",
                plans_dir=plans_dir,
            )

            prompt = generator.feedback_prompt(
                reviewer="codex",
                primary_output=plans_dir / "research-primary.md",
            )

            assert "SECONDARY agent" in prompt
            assert "Codex" in prompt
            assert "feedback" in prompt.lower()
            assert "Strengths" in prompt
            assert "Issues Found" in prompt
            assert "Suggestions" in prompt

    def test_feedback_synthesis_prompt(self):
        """Test synthesis prompt in feedback-only mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plans_dir = Path(tmpdir)

            generator = ResearchDebatePrompts(
                task_description="Implement feature X",
                task_name="feature-x",
                plans_dir=plans_dir,
            )

            t1_results = Turn1Results(
                primary_result=ExecutionResult(
                    session_id="s1",
                    output="out",
                    cost_usd=0.5,
                    duration_ms=1000,
                    num_turns=5,
                    is_error=False,
                    raw_output="{}",
                ),
                secondary_result=None,
                primary_output_file=Path("/tmp/primary.md"),
                secondary_output_file=None,
            )

            prompt = generator.synthesis_prompt(
                t1_results=t1_results,
                debate_transcript="Some feedback here",
                final_output_file=Path("/tmp/final.md"),
            )

            assert "Incorporating Feedback" in prompt
            assert "Issues Addressed" in prompt
            assert "Issues Declined" in prompt
            # Should NOT reference a secondary T1 output file
            assert "None" not in prompt

    def test_debate_log_primary_only_turn1(self):
        """Test DebateLog writes correctly with no secondary T1 output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "debate.md"

            log = DebateLog(log_path)
            log.write_header("research", "Test task")

            t1_results = Turn1Results(
                primary_result=ExecutionResult(
                    session_id="s1",
                    output="out",
                    cost_usd=0.5,
                    duration_ms=1000,
                    num_turns=5,
                    is_error=False,
                    raw_output="{}",
                ),
                secondary_result=None,
                primary_output_file=Path("/tmp/primary.md"),
                secondary_output_file=None,
            )

            log.write_turn1_summary(t1_results)

            content = log_path.read_text()
            assert "Turn 1 Output" in content
            assert "Feedback" in content
            # Should not mention secondary analysis
            assert "Secondary" not in content or "Initial Analysis" not in content

    def test_debate_result_cost_without_secondary_t1(self):
        """Test cost calculation when secondary didn't generate in Turn 1."""
        turn1 = Turn1Results(
            primary_result=ExecutionResult(
                session_id="s1",
                output="out",
                cost_usd=0.5,
                duration_ms=1000,
                num_turns=5,
                is_error=False,
                raw_output="{}",
            ),
            secondary_result=None,
            primary_output_file=Path("/tmp/primary.md"),
            secondary_output_file=None,
            primary_agent="claude",
            secondary_agent="codex",
        )

        # Secondary has a feedback message in Turn 2
        feedback_msg = DebateMessage(
            speaker="codex",
            message_number=1,
            content="Feedback",
            role="secondary",
            result=ExecutionResult(
                session_id="s2",
                output="feedback",
                cost_usd=0.2,
                duration_ms=500,
                num_turns=2,
                is_error=False,
                raw_output="{}",
            ),
        )

        synthesis = SynthesisResult(
            result=ExecutionResult(
                session_id="synth",
                output="synthesis",
                cost_usd=0.4,
                duration_ms=600,
                num_turns=4,
                is_error=False,
                raw_output="{}",
            ),
            output_file=Path("/tmp/final.md"),
        )

        result = DebateResult(
            success=True,
            phase_name="research",
            final_output_file=Path("/tmp/final.md"),
            turn1=turn1,
            turn2=Turn2Results(
                messages=[feedback_msg],
                primary_agent="claude",
                secondary_agent="codex",
            ),
            synthesis=synthesis,
        )

        # Primary cost: T1 (0.5) + Synthesis (0.4) = 0.9
        assert abs(result.primary_cost - 0.9) < 0.001
        # Secondary cost: T2 feedback (0.2), no T1
        assert abs(result.secondary_cost - 0.2) < 0.001
        # Total: 0.5 + 0.2 + 0.4 = 1.1
        assert abs(result.total_cost - 1.1) < 0.001
