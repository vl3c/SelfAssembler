"""Tests for state management."""

import tempfile
from pathlib import Path

import pytest

from claudonomous.context import WorkflowContext
from claudonomous.errors import CheckpointError
from claudonomous.state import ApprovalStore, CheckpointManager, StateStore


class TestStateStore:
    """Tests for StateStore."""

    @pytest.fixture
    def store(self) -> StateStore:
        """Create a test store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield StateStore(Path(tmpdir))

    def test_save_and_load(self, store: StateStore):
        """Test saving and loading data."""
        data = {"key": "value", "number": 42}
        store.save("test_key", data)

        loaded = store.load("test_key")
        assert loaded == data

    def test_load_nonexistent(self, store: StateStore):
        """Test loading nonexistent key."""
        assert store.load("nonexistent") is None

    def test_delete(self, store: StateStore):
        """Test deleting data."""
        store.save("test_key", {"data": True})
        assert store.delete("test_key") is True
        assert store.load("test_key") is None
        assert store.delete("test_key") is False

    def test_list_keys(self, store: StateStore):
        """Test listing keys."""
        store.save("prefix_one", {})
        store.save("prefix_two", {})
        store.save("other", {})

        all_keys = store.list_keys()
        assert len(all_keys) == 3

        prefix_keys = store.list_keys("prefix_")
        assert len(prefix_keys) == 2


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    @pytest.fixture
    def manager(self) -> CheckpointManager:
        """Create a test manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir))
            yield CheckpointManager(store)

    @pytest.fixture
    def context(self) -> WorkflowContext:
        """Create a test context."""
        return WorkflowContext(
            task_description="Test task",
            task_name="test-task",
            repo_path=Path("/test/repo"),
            plans_dir=Path("/test/plans"),
        )

    def test_create_checkpoint(self, manager: CheckpointManager, context: WorkflowContext):
        """Test creating a checkpoint."""
        checkpoint_id = manager.create_checkpoint(context)
        assert checkpoint_id.startswith("checkpoint_")
        assert context.checkpoint_id == checkpoint_id

    def test_load_checkpoint(self, manager: CheckpointManager, context: WorkflowContext):
        """Test loading a checkpoint."""
        context.add_cost("phase1", 2.0)
        context.current_phase = "implementation"

        checkpoint_id = manager.create_checkpoint(context)
        loaded = manager.load_checkpoint(checkpoint_id)

        assert loaded.task_name == context.task_name
        assert loaded.total_cost_usd == context.total_cost_usd
        assert loaded.current_phase == context.current_phase
        assert loaded.resumed_from_checkpoint is True

    def test_load_nonexistent_checkpoint(self, manager: CheckpointManager):
        """Test loading nonexistent checkpoint."""
        with pytest.raises(CheckpointError):
            manager.load_checkpoint("nonexistent")

    def test_delete_checkpoint(self, manager: CheckpointManager, context: WorkflowContext):
        """Test deleting a checkpoint."""
        checkpoint_id = manager.create_checkpoint(context)
        assert manager.delete_checkpoint(checkpoint_id) is True
        assert manager.delete_checkpoint(checkpoint_id) is False

    def test_list_checkpoints(self, manager: CheckpointManager, context: WorkflowContext):
        """Test listing checkpoints."""
        manager.create_checkpoint(context)

        context2 = WorkflowContext(
            task_description="Another task",
            task_name="another-task",
            repo_path=Path("/test/repo"),
            plans_dir=Path("/test/plans"),
        )
        manager.create_checkpoint(context2)

        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 2


class TestApprovalStore:
    """Tests for ApprovalStore."""

    @pytest.fixture
    def store(self) -> ApprovalStore:
        """Create a test store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ApprovalStore(Path(tmpdir))

    def test_approval_flow(self, store: ApprovalStore):
        """Test approval flow."""
        assert not store.is_approved("planning")

        store.grant_approval("planning")
        assert store.is_approved("planning")

        store.revoke_approval("planning")
        assert not store.is_approved("planning")

    def test_list_approvals(self, store: ApprovalStore):
        """Test listing approvals."""
        store.grant_approval("planning")
        store.grant_approval("implementation")

        approvals = store.list_approvals()
        assert "planning" in approvals
        assert "implementation" in approvals
