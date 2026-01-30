"""Tests for workflow context."""

from datetime import datetime
from pathlib import Path

import pytest

from claudonomous.context import WorkflowContext
from claudonomous.errors import BudgetExceededError


class TestWorkflowContext:
    """Tests for WorkflowContext."""

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a test context."""
        return WorkflowContext(
            task_description="Test task description",
            task_name="test-task",
            repo_path=Path("/test/repo"),
            plans_dir=Path("/test/plans"),
            budget_limit_usd=10.0,
        )

    def test_init(self, context: WorkflowContext):
        """Test context initialization."""
        assert context.task_name == "test-task"
        assert context.budget_limit_usd == 10.0
        assert context.total_cost_usd == 0.0
        assert context.current_phase == "idle"

    def test_add_cost(self, context: WorkflowContext):
        """Test adding costs."""
        context.add_cost("phase1", 1.5)
        assert context.total_cost_usd == 1.5
        assert context.phase_costs["phase1"] == 1.5

        context.add_cost("phase2", 2.0)
        assert context.total_cost_usd == 3.5

        # Adding more to same phase
        context.add_cost("phase1", 0.5)
        assert context.phase_costs["phase1"] == 2.0

    def test_budget_exceeded(self, context: WorkflowContext):
        """Test budget exceeded error."""
        context.add_cost("phase1", 5.0)
        context.add_cost("phase2", 4.0)

        with pytest.raises(BudgetExceededError):
            context.add_cost("phase3", 2.0)

    def test_budget_remaining(self, context: WorkflowContext):
        """Test budget remaining calculation."""
        assert context.budget_remaining() == 10.0

        context.add_cost("phase1", 3.0)
        assert context.budget_remaining() == 7.0

    def test_mark_phase_complete(self, context: WorkflowContext):
        """Test marking phases complete."""
        assert not context.is_phase_completed("phase1")

        context.mark_phase_complete("phase1")
        assert context.is_phase_completed("phase1")

        # Adding again should not duplicate
        context.mark_phase_complete("phase1")
        assert context.completed_phases.count("phase1") == 1

    def test_artifacts(self, context: WorkflowContext):
        """Test artifact storage."""
        context.set_artifact("key1", "value1")
        assert context.get_artifact("key1") == "value1"
        assert context.get_artifact("nonexistent") is None
        assert context.get_artifact("nonexistent", "default") == "default"

    def test_session_ids(self, context: WorkflowContext):
        """Test session ID storage."""
        context.set_session_id("phase1", "session123")
        assert context.get_session_id("phase1") == "session123"
        assert context.get_session_id("phase2") is None

    def test_working_dir(self, context: WorkflowContext):
        """Test getting working directory."""
        # Without worktree
        assert context.get_working_dir() == Path("/test/repo")

        # With worktree
        context.worktree_path = Path("/test/worktree")
        assert context.get_working_dir() == Path("/test/worktree")

    def test_serialization(self, context: WorkflowContext):
        """Test serialization and deserialization."""
        context.add_cost("phase1", 2.5)
        context.mark_phase_complete("phase1")
        context.set_artifact("key", "value")

        data = context.to_dict()
        restored = WorkflowContext.from_dict(data)

        assert restored.task_name == context.task_name
        assert restored.total_cost_usd == context.total_cost_usd
        assert restored.completed_phases == context.completed_phases
        assert restored.artifacts == context.artifacts

    def test_summary(self, context: WorkflowContext):
        """Test summary generation."""
        context.add_cost("phase1", 2.0)
        context.current_phase = "implementation"

        summary = context.summary()
        assert "test-task" in summary
        assert "implementation" in summary
        assert "$2.00" in summary
