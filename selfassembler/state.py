"""State persistence and checkpoint management."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selfassembler.errors import CheckpointError

if TYPE_CHECKING:
    from selfassembler.context import WorkflowContext


class StateStore:
    """
    Persistent state storage for workflow data.

    Stores checkpoints and workflow state to disk for recovery.
    """

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or self._default_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _default_state_dir(self) -> Path:
        """Get the default state directory."""
        # Use XDG_STATE_HOME or fallback to ~/.local/state
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            base = Path(xdg_state)
        else:
            base = Path.home() / ".local" / "state"
        return base / "selfassembler"

    def save(self, key: str, data: dict[str, Any]) -> Path:
        """Save data to the state store."""
        # Ensure directory exists before saving
        self.state_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.state_dir / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return file_path

    def load(self, key: str) -> dict[str, Any] | None:
        """Load data from the state store."""
        file_path = self.state_dir / f"{key}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Corrupted file - return None
            return None
        except OSError:
            # File access error - return None
            return None

    def delete(self, key: str) -> bool:
        """Delete data from the state store."""
        file_path = self.state_dir / f"{key}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys in the state store."""
        keys = []
        for file_path in self.state_dir.glob("*.json"):
            key = file_path.stem
            if key.startswith(prefix):
                keys.append(key)
        return sorted(keys)


class CheckpointManager:
    """
    Manages workflow checkpoints for recovery and resume.

    Checkpoints allow resuming a workflow from a specific phase
    if it fails or is interrupted.
    """

    def __init__(self, state_store: StateStore | None = None):
        self.store = state_store or StateStore()
        self.checkpoint_prefix = "checkpoint_"

    def _generate_checkpoint_id(self, context: "WorkflowContext") -> str:
        """Generate a unique checkpoint ID."""
        # Create a hash from task name and timestamp
        data = f"{context.task_name}-{context.started_at.isoformat()}"
        hash_part = hashlib.sha256(data.encode()).hexdigest()[:8]
        return f"{self.checkpoint_prefix}{hash_part}"

    def create_checkpoint(self, context: "WorkflowContext") -> str:
        """
        Create a checkpoint for the current workflow state.

        Args:
            context: The workflow context to checkpoint

        Returns:
            The checkpoint ID

        Raises:
            CheckpointError: If checkpoint creation fails
        """
        try:
            checkpoint_id = context.checkpoint_id or self._generate_checkpoint_id(context)
            context.checkpoint_id = checkpoint_id

            checkpoint_data = {
                "id": checkpoint_id,
                "created_at": datetime.now().isoformat(),
                "context": context.to_dict(),
            }

            self.store.save(checkpoint_id, checkpoint_data)
            return checkpoint_id

        except Exception as e:
            raise CheckpointError(f"Failed to create checkpoint: {e}") from e

    def load_checkpoint(self, checkpoint_id: str) -> "WorkflowContext":
        """
        Load a checkpoint and restore workflow context.

        Args:
            checkpoint_id: The checkpoint ID to load

        Returns:
            The restored WorkflowContext

        Raises:
            CheckpointError: If checkpoint doesn't exist or is invalid
        """
        from selfassembler.context import WorkflowContext

        data = self.store.load(checkpoint_id)
        if data is None:
            raise CheckpointError(f"Checkpoint not found: {checkpoint_id}")

        try:
            context = WorkflowContext.from_dict(data["context"])
            context.checkpoint_id = checkpoint_id
            context.resumed_from_checkpoint = True
            return context
        except Exception as e:
            raise CheckpointError(f"Invalid checkpoint data: {e}") from e

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        return self.store.delete(checkpoint_id)

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """
        List all available checkpoints.

        Returns:
            List of checkpoint summaries
        """
        checkpoints = []
        for key in self.store.list_keys(self.checkpoint_prefix):
            data = self.store.load(key)
            if data:
                context = data.get("context", {})
                checkpoints.append(
                    {
                        "id": key,
                        "task_name": context.get("task_name", "Unknown"),
                        "current_phase": context.get("current_phase", "Unknown"),
                        "created_at": data.get("created_at", "Unknown"),
                        "cost_usd": context.get("total_cost_usd", 0.0),
                    }
                )
        return sorted(checkpoints, key=lambda x: x["created_at"], reverse=True)

    def cleanup_old_checkpoints(self, max_age_hours: float = 168) -> int:
        """
        Remove checkpoints older than max_age_hours (default: 7 days).

        Returns:
            Number of checkpoints deleted
        """
        deleted = 0
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

        for key in self.store.list_keys(self.checkpoint_prefix):
            data = self.store.load(key)
            if data:
                try:
                    created_at = datetime.fromisoformat(data["created_at"])
                    if created_at.timestamp() < cutoff:
                        self.delete_checkpoint(key)
                        deleted += 1
                except (KeyError, ValueError):
                    pass

        return deleted


class ApprovalStore:
    """
    Manages approval state for workflow phases.

    Approvals can be given via:
    - File-based: Creating a .approved_{phase} file
    - API-based: Through webhook callbacks (future)
    """

    def __init__(self, plans_dir: Path):
        self.plans_dir = plans_dir

    def is_approved(self, phase: str) -> bool:
        """Check if a phase has been approved."""
        approval_file = self.plans_dir / f".approved_{phase}"
        return approval_file.exists()

    def wait_for_approval(self, phase: str, timeout_hours: float = 24.0) -> bool:
        """
        Wait for approval of a phase.

        This is a blocking operation that checks periodically
        for the approval file.

        Args:
            phase: The phase name to wait for
            timeout_hours: Maximum hours to wait

        Returns:
            True if approved, False if timed out
        """
        import time

        approval_file = self.plans_dir / f".approved_{phase}"
        timeout_seconds = timeout_hours * 3600
        start_time = time.time()
        check_interval = 10  # Check every 10 seconds

        while (time.time() - start_time) < timeout_seconds:
            if approval_file.exists():
                return True
            time.sleep(check_interval)

        return False

    def grant_approval(self, phase: str) -> None:
        """Grant approval for a phase (creates approval file)."""
        approval_file = self.plans_dir / f".approved_{phase}"
        approval_file.touch()

    def revoke_approval(self, phase: str) -> None:
        """Revoke approval for a phase."""
        approval_file = self.plans_dir / f".approved_{phase}"
        if approval_file.exists():
            approval_file.unlink()

    def list_approvals(self) -> list[str]:
        """List all approved phases."""
        approvals = []
        for file_path in self.plans_dir.glob(".approved_*"):
            phase = file_path.name.replace(".approved_", "")
            approvals.append(phase)
        return approvals
