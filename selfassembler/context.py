"""Workflow context and state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from selfassembler.errors import BudgetExceededError


@dataclass
class WorkflowContext:
    """
    Holds the state of a workflow execution.

    This context is passed through all phases and tracks:
    - Task information
    - Git state (worktree, branch)
    - Cost tracking
    - Artifacts from completed phases
    - Checkpointing info
    """

    task_description: str
    task_name: str
    repo_path: Path
    plans_dir: Path

    # Git state
    worktree_path: Path | None = None
    branch_name: str | None = None
    branch_pushed: bool = False

    # Workflow state
    current_phase: str = "idle"
    started_at: datetime = field(default_factory=datetime.now)
    completed_phases: list[str] = field(default_factory=list)

    # PR info
    pr_number: int | None = None
    pr_url: str | None = None

    # Checkpoint info
    checkpoint_id: str | None = None
    resumed_from_checkpoint: bool = False

    # Cost tracking
    total_cost_usd: float = 0.0
    budget_limit_usd: float = 15.0
    phase_costs: dict[str, float] = field(default_factory=dict)

    # Session tracking for Claude CLI
    session_ids: dict[str, str] = field(default_factory=dict)

    # Artifacts from phases
    artifacts: dict[str, Any] = field(default_factory=dict)

    def add_cost(self, phase: str, cost: float) -> None:
        """
        Add cost for a phase and check budget limit.

        Args:
            phase: The phase name
            cost: Cost in USD

        Raises:
            BudgetExceededError: If total cost exceeds budget limit
        """
        self.total_cost_usd += cost
        self.phase_costs[phase] = self.phase_costs.get(phase, 0.0) + cost

        if self.total_cost_usd > self.budget_limit_usd:
            raise BudgetExceededError(
                f"Budget exceeded: ${self.total_cost_usd:.2f} > ${self.budget_limit_usd:.2f}",
                current_cost=self.total_cost_usd,
                budget_limit=self.budget_limit_usd,
            )

    def budget_remaining(self) -> float:
        """Get remaining budget in USD."""
        return max(0.0, self.budget_limit_usd - self.total_cost_usd)

    def mark_phase_complete(self, phase: str) -> None:
        """Mark a phase as completed."""
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)

    def is_phase_completed(self, phase: str) -> bool:
        """Check if a phase has been completed."""
        return phase in self.completed_phases

    def set_artifact(self, key: str, value: Any) -> None:
        """Store an artifact from a phase."""
        self.artifacts[key] = value

    def get_artifact(self, key: str, default: Any = None) -> Any:
        """Retrieve an artifact."""
        return self.artifacts.get(key, default)

    def set_session_id(self, phase: str, session_id: str) -> None:
        """Store a Claude session ID for potential resume."""
        self.session_ids[phase] = session_id

    def get_session_id(self, phase: str) -> str | None:
        """Get a stored session ID."""
        return self.session_ids.get(phase)

    # -------------------------------------------------------------------------
    # Debate session tracking
    # -------------------------------------------------------------------------

    def set_debate_session_id(
        self,
        phase: str,
        agent: str,
        turn: int,
        session_id: str,
        message_num: int | None = None,
    ) -> None:
        """
        Store session ID for a debate turn.

        Args:
            phase: The phase name (e.g., "research")
            agent: The agent name ("claude" or "codex")
            turn: The turn number (1, 2, or 3)
            session_id: The session ID to store
            message_num: Optional message number for Turn 2 messages
        """
        if message_num is not None:
            key = f"{phase}_{agent}_t{turn}_msg{message_num}"
        else:
            key = f"{phase}_{agent}_t{turn}"
        self.session_ids[key] = session_id

    def get_debate_session_id(
        self,
        phase: str,
        agent: str,
        turn: int,
        message_num: int | None = None,
    ) -> str | None:
        """
        Get stored debate session ID.

        Args:
            phase: The phase name
            agent: The agent name
            turn: The turn number
            message_num: Optional message number for Turn 2 messages

        Returns:
            The session ID if found, None otherwise
        """
        if message_num is not None:
            key = f"{phase}_{agent}_t{turn}_msg{message_num}"
        else:
            key = f"{phase}_{agent}_t{turn}"
        return self.session_ids.get(key)

    def get_synthesis_resume_session(self, phase: str) -> str | None:
        """
        Get session to resume for synthesis (Turn 3).

        This returns the session from Claude's final Turn 2 message,
        allowing synthesis to carry the full debate context.

        Args:
            phase: The phase name

        Returns:
            The session ID to resume, or None
        """
        # Try to find Claude's last Turn 2 message session
        # Check messages 3, 2, 1 (typical max is 3)
        for msg_num in [3, 2, 1]:
            session = self.get_debate_session_id(phase, "claude", 2, msg_num)
            if session:
                return session

        # Fall back to Turn 1 session
        return self.get_debate_session_id(phase, "claude", 1)

    def get_working_dir(self) -> Path:
        """Get the current working directory (worktree or repo)."""
        return self.worktree_path or self.repo_path

    def elapsed_time(self) -> float:
        """Get elapsed time in seconds since workflow started."""
        return (datetime.now() - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert context to a serializable dictionary."""
        return {
            "task_description": self.task_description,
            "task_name": self.task_name,
            "repo_path": str(self.repo_path),
            "plans_dir": str(self.plans_dir),
            "worktree_path": str(self.worktree_path) if self.worktree_path else None,
            "branch_name": self.branch_name,
            "branch_pushed": self.branch_pushed,
            "current_phase": self.current_phase,
            "started_at": self.started_at.isoformat(),
            "completed_phases": self.completed_phases,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "checkpoint_id": self.checkpoint_id,
            "total_cost_usd": self.total_cost_usd,
            "budget_limit_usd": self.budget_limit_usd,
            "phase_costs": self.phase_costs,
            "session_ids": self.session_ids,
            "artifacts": {
                k: str(v) if isinstance(v, Path) else v for k, v in self.artifacts.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Create context from a serialized dictionary."""
        return cls(
            task_description=data["task_description"],
            task_name=data["task_name"],
            repo_path=Path(data["repo_path"]),
            plans_dir=Path(data["plans_dir"]),
            worktree_path=Path(data["worktree_path"]) if data.get("worktree_path") else None,
            branch_name=data.get("branch_name"),
            branch_pushed=data.get("branch_pushed", False),
            current_phase=data.get("current_phase", "idle"),
            started_at=datetime.fromisoformat(data["started_at"])
            if "started_at" in data
            else datetime.now(),
            completed_phases=data.get("completed_phases", []),
            pr_number=data.get("pr_number"),
            pr_url=data.get("pr_url"),
            checkpoint_id=data.get("checkpoint_id"),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            budget_limit_usd=data.get("budget_limit_usd", 15.0),
            phase_costs=data.get("phase_costs", {}),
            session_ids=data.get("session_ids", {}),
            artifacts=data.get("artifacts", {}),
        )

    def summary(self) -> str:
        """Get a summary of the current context state."""
        lines = [
            f"Task: {self.task_name}",
            f"Phase: {self.current_phase}",
            f"Cost: ${self.total_cost_usd:.2f} / ${self.budget_limit_usd:.2f}",
            f"Elapsed: {self.elapsed_time():.0f}s",
        ]
        if self.branch_name:
            lines.append(f"Branch: {self.branch_name}")
        if self.pr_url:
            lines.append(f"PR: {self.pr_url}")
        return "\n".join(lines)
