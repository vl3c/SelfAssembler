"""Tests for DebateOrchestrator - covers feedback mode, full debate mode, and edge cases."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from selfassembler.config import DebateConfig
from selfassembler.context import WorkflowContext
from selfassembler.debate.files import DebateFileManager
from selfassembler.debate.orchestrator import DebateOrchestrator
from selfassembler.debate.prompts import ResearchDebatePrompts
from selfassembler.debate.results import Turn1Results, Turn2Results
from selfassembler.executors.base import ExecutionResult


def _make_exec_result(
    session_id: str = "sess-1",
    output: str = "mock output",
    cost: float = 0.1,
    is_error: bool = False,
) -> ExecutionResult:
    """Helper to build an ExecutionResult."""
    return ExecutionResult(
        session_id=session_id,
        output=output,
        cost_usd=cost,
        duration_ms=500,
        num_turns=3,
        is_error=is_error,
        raw_output="{}",
    )


@pytest.fixture
def tmp_plans(tmp_path):
    """Temporary plans directory."""
    plans = tmp_path / "plans"
    plans.mkdir()
    return plans


@pytest.fixture
def context(tmp_path, tmp_plans):
    """WorkflowContext pointing at tmp dirs."""
    return WorkflowContext(
        task_description="Implement fizzbuzz",
        task_name="fizzbuzz",
        repo_path=tmp_path,
        plans_dir=tmp_plans,
    )


@pytest.fixture
def file_manager(tmp_plans):
    """DebateFileManager backed by tmp dir."""
    return DebateFileManager(tmp_plans, "fizzbuzz")


@pytest.fixture
def prompt_gen(tmp_plans):
    """ResearchDebatePrompts for testing."""
    return ResearchDebatePrompts(
        task_description="Implement fizzbuzz",
        task_name="fizzbuzz",
        plans_dir=tmp_plans,
    )


def _mock_executor(name: str = "claude", results=None):
    """Create a mock AgentExecutor that returns sequential results."""
    mock = MagicMock()
    if results:
        mock.execute.side_effect = results
    else:
        mock.execute.return_value = _make_exec_result(session_id=f"{name}-sess")
    return mock


def _with_synthesis_write(results, file_manager, phase_file_name="research"):
    """Wrap a result list so the final (synthesis) call also writes the output file.

    ``_run_synthesis`` deletes any stale output file before calling the
    executor, so pre-creating the file doesn't work.  This wrapper makes the
    last mock call write the file — just like a real agent would.
    """
    final = file_manager.get_final_output_path(phase_file_name)
    call_idx = [0]

    def _side_effect(**_kwargs):
        i = call_idx[0]
        call_idx[0] += 1
        if i == len(results) - 1:
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_text("mock synthesis output")
        return results[i]

    return _side_effect


# ---------------------------------------------------------------------------
# Feedback mode tests
# ---------------------------------------------------------------------------


class TestFeedbackModeOrchestration:
    """Test the full feedback flow: primary generates → secondary reviews → synthesis."""

    def test_feedback_mode_calls_primary_then_secondary_then_synthesis(
        self, context, file_manager, prompt_gen
    ):
        """Verify the 3-step feedback flow calls the right executors."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_results = [
            _make_exec_result(session_id="primary-t1", output="primary analysis"),
            _make_exec_result(session_id="synthesis", output="final output"),
        ]
        primary_exec = MagicMock()
        primary_exec.execute.side_effect = _with_synthesis_write(primary_results, file_manager)
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="secondary-feedback", output="feedback notes"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is True
        assert result.phase_name == "research"

        # Primary called twice: Turn 1 + Synthesis
        assert primary_exec.execute.call_count == 2
        # Secondary called once: Feedback
        assert secondary_exec.execute.call_count == 1

    def test_feedback_mode_turn1_has_no_secondary(self, context, file_manager, prompt_gen):
        """Turn1Results should have None secondary in feedback mode."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="p-t1"),
            _make_exec_result(session_id="p-synth"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-fb"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.turn1 is not None
        assert result.turn1.secondary_result is None
        assert result.turn1.secondary_output_file is None

    def test_feedback_mode_turn2_has_single_secondary_message(
        self, context, file_manager, prompt_gen
    ):
        """Turn 2 should contain exactly one message from secondary."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(output="my feedback"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.turn2 is not None
        assert result.turn2.message_count == 1
        assert result.turn2.messages[0].role == "secondary"
        assert result.turn2.messages[0].content == "my feedback"

    def test_feedback_mode_stores_session_ids(self, context, file_manager, prompt_gen):
        """Session IDs from each step should be stored in context."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="t1-sess"),
            _make_exec_result(session_id="synth-sess"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="fb-sess"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # Turn 1 primary session stored
        assert context.get_debate_session_id("research", "primary", 1) == "t1-sess"
        # Feedback session stored
        assert context.get_debate_session_id("research", "secondary", 2, 1) == "fb-sess"
        # Synthesis session stored
        assert context.session_ids.get("research_synthesis") == "synth-sess"

    def test_feedback_mode_creates_debate_transcript(self, context, file_manager, prompt_gen):
        """A debate transcript file should be written with feedback content."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(output="looks good, minor issue with X"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        debate_path = file_manager.get_debate_path("research")
        assert debate_path.exists()
        content = debate_path.read_text()
        assert "looks good, minor issue with X" in content
        assert "Feedback" in content

    def test_feedback_mode_secondary_gets_dangerous_mode_when_different_agent(
        self, context, file_manager, prompt_gen
    ):
        """When primary != secondary agent, secondary should run with dangerous_mode=True."""
        config = DebateConfig(
            enabled=True, mode="feedback",
            primary_agent="claude", secondary_agent="codex",
        )

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen, dangerous_mode=False)

        # Secondary should have been called with dangerous_mode=True
        secondary_call = secondary_exec.execute.call_args
        assert secondary_call.kwargs.get("dangerous_mode") is True

    def test_feedback_mode_same_agent_respects_dangerous_mode(
        self, context, file_manager, prompt_gen
    ):
        """When primary == secondary agent, secondary should respect caller's dangerous_mode."""
        config = DebateConfig(
            enabled=True, mode="feedback",
            primary_agent="claude", secondary_agent="claude",
        )

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("claude", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen, dangerous_mode=False)

        secondary_call = secondary_exec.execute.call_args
        assert secondary_call.kwargs.get("dangerous_mode") is False

    def test_feedback_mode_cost_tracking(self, context, file_manager, prompt_gen):
        """Total cost should reflect primary T1 + secondary feedback + synthesis."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(cost=0.50),  # T1
            _make_exec_result(cost=0.40),  # Synthesis
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(cost=0.20),  # Feedback
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert abs(result.total_cost - 1.10) < 0.001
        assert abs(result.primary_cost - 0.90) < 0.001
        assert abs(result.secondary_cost - 0.20) < 0.001

    def test_feedback_synthesis_resumes_from_t1_session(
        self, context, file_manager, prompt_gen
    ):
        """In feedback mode, synthesis should resume from primary's T1 session."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="t1-primary-sess"),
            _make_exec_result(session_id="synth-sess"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # Synthesis call (second call to primary) should have resume_session=t1 session
        synth_call = primary_exec.execute.call_args_list[1]
        assert synth_call.kwargs.get("resume_session") == "t1-primary-sess"


# ---------------------------------------------------------------------------
# Full debate mode tests
# ---------------------------------------------------------------------------


class TestFullDebateModeOrchestration:
    """Test the full debate flow: both generate → exchange → synthesis."""

    def test_debate_low_calls_both_agents_and_exchanges_3_messages(
        self, context, file_manager, prompt_gen
    ):
        """Debate low (3 msgs): T1 primary + T1 secondary + 3 exchange msgs + synthesis."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        # T1 primary, exchange msg 1 (primary), exchange msg 3 (primary), synthesis
        primary_results = [
            _make_exec_result(session_id="p-t1"),
            _make_exec_result(session_id="p-msg1"),
            _make_exec_result(session_id="p-msg3"),
            _make_exec_result(session_id="p-synth"),
        ]
        primary_exec = MagicMock()
        primary_exec.execute.side_effect = _with_synthesis_write(primary_results, file_manager)
        # T1 secondary, exchange msg 2 (secondary)
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-t1"),
            _make_exec_result(session_id="s-msg2"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is True
        # Primary: T1 + msg1 + msg3 + synthesis = 4
        assert primary_exec.execute.call_count == 4
        # Secondary: T1 + msg2 = 2
        assert secondary_exec.execute.call_count == 2

    def test_debate_high_exchanges_5_messages(self, context, file_manager, prompt_gen):
        """Debate high (5 msgs): T1 x2 + 5 exchange msgs + synthesis = 8 total calls."""
        config = DebateConfig(enabled=True, mode="debate", intensity="high")

        # Primary: T1 + msg1 + msg3 + msg5 + synthesis = 5
        primary_results = [
            _make_exec_result(session_id=f"p-{i}") for i in range(5)
        ]
        primary_exec = MagicMock()
        primary_exec.execute.side_effect = _with_synthesis_write(primary_results, file_manager)
        # Secondary: T1 + msg2 + msg4 = 3
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id=f"s-{i}") for i in range(3)
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is True
        assert primary_exec.execute.call_count == 5
        assert secondary_exec.execute.call_count == 3

    def test_debate_turn2_alternates_speakers(self, context, file_manager, prompt_gen):
        """Turn 2 messages should alternate: primary → secondary → primary."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(),  # T1
            _make_exec_result(output="msg1-primary"),   # msg1
            _make_exec_result(output="msg3-primary"),   # msg3
            _make_exec_result(),  # synthesis
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),  # T1
            _make_exec_result(output="msg2-secondary"),  # msg2
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        msgs = result.turn2.messages
        assert len(msgs) == 3
        assert msgs[0].role == "primary"
        assert msgs[1].role == "secondary"
        assert msgs[2].role == "primary"
        assert msgs[0].content == "msg1-primary"
        assert msgs[1].content == "msg2-secondary"
        assert msgs[2].content == "msg3-primary"

    def test_debate_turn1_produces_both_outputs(self, context, file_manager, prompt_gen):
        """Turn 1 should produce results for both agents."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="p-t1"),
            _make_exec_result(), _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-t1"),
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.turn1.primary_result is not None
        assert result.turn1.secondary_result is not None
        assert result.turn1.primary_output_file is not None
        assert result.turn1.secondary_output_file is not None

    def test_debate_stores_all_session_ids(self, context, file_manager, prompt_gen):
        """All session IDs should be stored for potential resume."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="p-t1"),
            _make_exec_result(session_id="p-msg1"),
            _make_exec_result(session_id="p-msg3"),
            _make_exec_result(session_id="p-synth"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-t1"),
            _make_exec_result(session_id="s-msg2"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        assert context.get_debate_session_id("research", "primary", 1) == "p-t1"
        assert context.get_debate_session_id("research", "secondary", 1) == "s-t1"
        assert context.get_debate_session_id("research", "primary", 2, 1) == "p-msg1"
        assert context.get_debate_session_id("research", "secondary", 2, 2) == "s-msg2"
        assert context.get_debate_session_id("research", "primary", 2, 3) == "p-msg3"
        assert context.session_ids.get("research_synthesis") == "p-synth"

    def test_debate_synthesis_resumes_from_last_primary_t2_message(
        self, context, file_manager, prompt_gen
    ):
        """Synthesis should resume from primary's last Turn 2 message."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="p-t1"),
            _make_exec_result(session_id="p-msg1"),
            _make_exec_result(session_id="p-msg3"),
            _make_exec_result(session_id="p-synth"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-t1"),
            _make_exec_result(session_id="s-msg2"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # Synthesis call (4th call to primary) should resume from msg3 session
        synth_call = primary_exec.execute.call_args_list[3]
        assert synth_call.kwargs.get("resume_session") == "p-msg3"

    def test_debate_creates_transcript_with_all_messages(
        self, context, file_manager, prompt_gen
    ):
        """Debate transcript should contain all exchange messages."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(),
            _make_exec_result(output="I disagree with point A"),
            _make_exec_result(output="Final position: X"),
            _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
            _make_exec_result(output="Counter-argument on A"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        debate_path = file_manager.get_debate_path("research")
        assert debate_path.exists()
        content = debate_path.read_text()
        assert "I disagree with point A" in content
        assert "Counter-argument on A" in content
        assert "Final position: X" in content

    def test_debate_sequential_turn1(self, context, file_manager, prompt_gen):
        """When parallel_turn_1=False, Turn 1 should run sequentially."""
        config = DebateConfig(
            enabled=True, mode="debate", intensity="low", parallel_turn_1=False,
        )
        call_order = []

        def primary_execute(**kwargs):
            call_order.append("primary")
            return _make_exec_result(session_id="p")

        def secondary_execute(**kwargs):
            call_order.append("secondary")
            return _make_exec_result(session_id="s")

        primary_results = [
            _make_exec_result(session_id="p-t1"),   # T1
            _make_exec_result(session_id="p-msg1"),  # msg1
            _make_exec_result(session_id="p-msg3"),  # msg3
            _make_exec_result(session_id="p-synth"), # synthesis
        ]
        primary_exec = MagicMock()
        primary_exec.execute.side_effect = _with_synthesis_write(primary_results, file_manager)
        secondary_exec = MagicMock()
        secondary_exec.execute.side_effect = [
            _make_exec_result(session_id="s-t1"),   # T1
            _make_exec_result(session_id="s-msg2"),  # msg2
        ]

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is True
        # Both T1 calls should have happened (sequential, not parallel)
        assert primary_exec.execute.call_count == 4
        assert secondary_exec.execute.call_count == 2


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestDebateErrorHandling:
    """Test error handling in debate orchestration."""

    def test_executor_exception_returns_failed_result(
        self, context, file_manager, prompt_gen
    ):
        """If an executor raises, run_debate should return a failed DebateResult."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = MagicMock()
        primary_exec.execute.side_effect = RuntimeError("CLI crashed")
        secondary_exec = _mock_executor("codex")

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is False
        assert "CLI crashed" in result.error

    def test_synthesis_error_returns_failed_result(self, context, file_manager, prompt_gen):
        """If synthesis executor returns is_error, result should reflect failure."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="t1"),
            _make_exec_result(session_id="synth", is_error=True),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        # SynthesisResult.success is based on is_error
        assert result.success is False


# ---------------------------------------------------------------------------
# Phase file name mapping tests
# ---------------------------------------------------------------------------


class TestPhaseFileNameMapping:
    """Test _get_phase_file_name maps phase names correctly."""

    def test_all_phase_mappings(self, context, file_manager, prompt_gen):
        config = DebateConfig(enabled=True, mode="feedback")
        primary_exec = _mock_executor("claude")
        secondary_exec = _mock_executor("codex")

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)

        assert orch._get_phase_file_name("research") == "research"
        assert orch._get_phase_file_name("planning") == "plan"
        assert orch._get_phase_file_name("plan_review") == "plan-review"
        assert orch._get_phase_file_name("code_review") == "review"
        assert orch._get_phase_file_name("unknown") == "unknown"


# ---------------------------------------------------------------------------
# Prompt generation integration
# ---------------------------------------------------------------------------


class TestPromptIntegration:
    """Verify the orchestrator passes correct prompts to executors."""

    def test_feedback_mode_uses_feedback_prompt_for_secondary(
        self, context, file_manager, prompt_gen
    ):
        """Secondary should receive a feedback_prompt, not a turn1 prompt."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # Secondary's prompt should contain feedback-specific keywords
        secondary_prompt = secondary_exec.execute.call_args.kwargs["prompt"]
        assert "Feedback Review" in secondary_prompt
        assert "SECONDARY agent" in secondary_prompt

    def test_feedback_mode_uses_feedback_synthesis_prompt(
        self, context, file_manager, prompt_gen
    ):
        """Synthesis in feedback mode should use the feedback synthesis prompt."""
        config = DebateConfig(enabled=True, mode="feedback")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(), _make_exec_result(),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # Synthesis prompt (2nd call to primary) should be feedback-flavored
        synth_prompt = primary_exec.execute.call_args_list[1].kwargs["prompt"]
        assert "Incorporating Feedback" in synth_prompt
        assert "Issues Addressed" in synth_prompt

    def test_debate_mode_uses_debate_prompts(self, context, file_manager, prompt_gen):
        """Full debate mode should use opening/response/final prompts in Turn 2."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(),  # T1
            _make_exec_result(),  # msg1 (opening)
            _make_exec_result(),  # msg3 (final)
            _make_exec_result(),  # synthesis
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(),  # T1
            _make_exec_result(),  # msg2 (response)
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        orch.run_debate("research", prompt_gen)

        # msg1 (opening): 2nd primary call
        msg1_prompt = primary_exec.execute.call_args_list[1].kwargs["prompt"]
        assert "Message 1 of 3" in msg1_prompt
        assert "Points of Agreement" in msg1_prompt

        # msg3 (final): 3rd primary call
        msg3_prompt = primary_exec.execute.call_args_list[2].kwargs["prompt"]
        assert "FINAL" in msg3_prompt
        assert "Remaining Disagreements" in msg3_prompt

        # Synthesis (4th primary call) should be the full synthesis prompt
        synth_prompt = primary_exec.execute.call_args_list[3].kwargs["prompt"]
        assert "Synthesis" in synth_prompt


# ---------------------------------------------------------------------------
# Turn 1 reuse on resume tests
# ---------------------------------------------------------------------------


class TestTurn1Reuse:
    """Test that existing Turn 1 outputs are reused on resume."""

    def test_feedback_mode_reuses_existing_primary_t1(
        self, context, file_manager, prompt_gen
    ):
        """When primary T1 file already exists, Turn 1 should be skipped."""
        config = DebateConfig(enabled=True, mode="feedback")

        # Pre-create the primary T1 output file (simulates previous failed run)
        primary_t1_file = file_manager.get_role_output_path("research", "primary")
        primary_t1_file.parent.mkdir(parents=True, exist_ok=True)
        primary_t1_file.write_text("# Previous research output\nSome analysis...")

        # Primary only needs to be called once (synthesis), not twice (T1 + synthesis)
        primary_results = [
            _make_exec_result(session_id="synth-sess"),
        ]
        primary_exec = MagicMock()
        primary_exec.execute.side_effect = _with_synthesis_write(primary_results, file_manager)
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="fb-sess"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        assert result.success is True
        # Primary called only once (synthesis), Turn 1 was skipped
        assert primary_exec.execute.call_count == 1
        # Secondary still called once for feedback
        assert secondary_exec.execute.call_count == 1
        # Turn 1 result should have zero cost (reused)
        assert result.turn1.primary_result.cost_usd == 0.0

    def test_full_debate_reuses_existing_t1_files(
        self, context, file_manager, prompt_gen
    ):
        """When both T1 files exist, full debate Turn 1 should be skipped."""
        config = DebateConfig(enabled=True, mode="debate", intensity="low")

        # Pre-create both T1 output files
        primary_t1_file = file_manager.get_role_output_path("research", "primary")
        secondary_t1_file = file_manager.get_role_output_path("research", "secondary")
        primary_t1_file.parent.mkdir(parents=True, exist_ok=True)
        secondary_t1_file.parent.mkdir(parents=True, exist_ok=True)
        primary_t1_file.write_text("# Primary research\nAnalysis A")
        secondary_t1_file.write_text("# Secondary research\nAnalysis B")

        # Primary: msg1 + msg3 + synthesis = 3 (no T1)
        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="p-msg1"),
            _make_exec_result(session_id="p-msg3"),
            _make_exec_result(session_id="p-synth"),
        ])
        # Secondary: msg2 = 1 (no T1)
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="s-msg2"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        # Primary: 3 calls (msg1 + msg3 + synthesis), NOT 4 (T1 + msg1 + msg3 + synthesis)
        assert primary_exec.execute.call_count == 3
        # Secondary: 1 call (msg2), NOT 2 (T1 + msg2)
        assert secondary_exec.execute.call_count == 1
        # Turn 1 results should have zero cost (reused)
        assert result.turn1.primary_result.cost_usd == 0.0
        assert result.turn1.secondary_result.cost_usd == 0.0

    def test_feedback_mode_no_reuse_when_file_empty(
        self, context, file_manager, prompt_gen
    ):
        """An empty T1 file should NOT be reused — Turn 1 must still run."""
        config = DebateConfig(enabled=True, mode="feedback")

        # Pre-create an empty primary T1 file
        primary_t1_file = file_manager.get_role_output_path("research", "primary")
        primary_t1_file.parent.mkdir(parents=True, exist_ok=True)
        primary_t1_file.write_text("")

        # Primary called twice: Turn 1 (since file is empty) + synthesis
        primary_exec = _mock_executor("claude", results=[
            _make_exec_result(session_id="t1-sess"),
            _make_exec_result(session_id="synth-sess"),
        ])
        secondary_exec = _mock_executor("codex", results=[
            _make_exec_result(session_id="fb-sess"),
        ])

        orch = DebateOrchestrator(primary_exec, secondary_exec, config, context, file_manager)
        result = orch.run_debate("research", prompt_gen)

        # Primary called twice: T1 + synthesis (empty file was not reused)
        assert primary_exec.execute.call_count == 2


# ---------------------------------------------------------------------------
# SynthesisResult.success validation tests
# ---------------------------------------------------------------------------


class TestSynthesisResultSuccess:
    """Test SynthesisResult.success validates output file existence."""

    def test_synthesis_success_false_when_output_missing(self, tmp_path):
        """SynthesisResult.success should be False when output file doesn't exist."""
        from selfassembler.debate.results import SynthesisResult

        missing_file = tmp_path / "nonexistent_output.md"
        result = SynthesisResult(
            result=_make_exec_result(is_error=False),
            output_file=missing_file,
        )
        assert result.success is False

    def test_synthesis_success_true_when_output_exists(self, tmp_path):
        """SynthesisResult.success should be True when file exists and no error."""
        from selfassembler.debate.results import SynthesisResult

        output_file = tmp_path / "final_output.md"
        output_file.write_text("# Synthesized output\nContent here.")
        result = SynthesisResult(
            result=_make_exec_result(is_error=False),
            output_file=output_file,
        )
        assert result.success is True
