"""Result dataclasses for debate system."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from selfassembler.executors.base import ExecutionResult


@dataclass
class DebateMessage:
    """A single message in the debate exchange."""

    speaker: str  # "claude" or "codex"
    message_number: int
    content: str
    result: ExecutionResult | None = None

    @property
    def cost_usd(self) -> float:
        """Get the cost of this message."""
        return self.result.cost_usd if self.result else 0.0

    @property
    def session_id(self) -> str | None:
        """Get the session ID from this message's execution."""
        return self.result.session_id if self.result else None


@dataclass
class Turn1Results:
    """Results from Turn 1 parallel generation."""

    claude_result: ExecutionResult
    codex_result: ExecutionResult
    claude_output_file: Path
    codex_output_file: Path

    @property
    def total_cost(self) -> float:
        """Get combined cost of Turn 1."""
        return self.claude_result.cost_usd + self.codex_result.cost_usd

    def get(self, agent: str) -> ExecutionResult:
        """Get result for a specific agent."""
        if agent == "claude":
            return self.claude_result
        elif agent == "codex":
            return self.codex_result
        else:
            raise ValueError(f"Unknown agent: {agent}")

    def get_output_file(self, agent: str) -> Path:
        """Get output file path for a specific agent."""
        if agent == "claude":
            return self.claude_output_file
        elif agent == "codex":
            return self.codex_output_file
        else:
            raise ValueError(f"Unknown agent: {agent}")


@dataclass
class Turn2Results:
    """Results from Turn 2 debate exchange."""

    messages: list[DebateMessage] = field(default_factory=list)
    debate_log_path: Path | None = None

    @property
    def total_cost(self) -> float:
        """Get combined cost of Turn 2."""
        return sum(msg.cost_usd for msg in self.messages)

    @property
    def message_count(self) -> int:
        """Get the number of messages exchanged."""
        return len(self.messages)

    def get_claude_messages(self) -> list[DebateMessage]:
        """Get all messages from Claude."""
        return [m for m in self.messages if m.speaker == "claude"]

    def get_codex_messages(self) -> list[DebateMessage]:
        """Get all messages from Codex."""
        return [m for m in self.messages if m.speaker == "codex"]

    def get_final_claude_session(self) -> str | None:
        """Get the session ID from Claude's final message."""
        claude_msgs = self.get_claude_messages()
        if claude_msgs:
            return claude_msgs[-1].session_id
        return None


@dataclass
class SynthesisResult:
    """Result from Turn 3 synthesis."""

    result: ExecutionResult
    output_file: Path

    @property
    def success(self) -> bool:
        """Check if synthesis succeeded."""
        return not self.result.is_error

    @property
    def cost_usd(self) -> float:
        """Get the cost of synthesis."""
        return self.result.cost_usd

    @property
    def session_id(self) -> str | None:
        """Get the session ID from synthesis."""
        return self.result.session_id


@dataclass
class DebateResult:
    """Complete result from a multi-agent debate."""

    success: bool
    phase_name: str
    final_output_file: Path

    # Turn results
    turn1: Turn1Results | None = None
    turn2: Turn2Results | None = None
    synthesis: SynthesisResult | None = None

    # Error handling
    error: str | None = None

    # Additional metadata
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        """Get combined cost of entire debate."""
        cost = 0.0
        if self.turn1:
            cost += self.turn1.total_cost
        if self.turn2:
            cost += self.turn2.total_cost
        if self.synthesis:
            cost += self.synthesis.cost_usd
        return cost

    @property
    def claude_cost(self) -> float:
        """Get cost attributed to Claude."""
        cost = 0.0
        if self.turn1:
            cost += self.turn1.claude_result.cost_usd
        if self.turn2:
            for msg in self.turn2.get_claude_messages():
                cost += msg.cost_usd
        if self.synthesis:
            cost += self.synthesis.cost_usd
        return cost

    @property
    def codex_cost(self) -> float:
        """Get cost attributed to Codex."""
        cost = 0.0
        if self.turn1:
            cost += self.turn1.codex_result.cost_usd
        if self.turn2:
            for msg in self.turn2.get_codex_messages():
                cost += msg.cost_usd
        return cost

    def get_session_ids(self) -> dict[str, str]:
        """Get all session IDs from the debate."""
        sessions = {}

        if self.turn1:
            if self.turn1.claude_result.session_id:
                sessions["turn1_claude"] = self.turn1.claude_result.session_id
            if self.turn1.codex_result.session_id:
                sessions["turn1_codex"] = self.turn1.codex_result.session_id

        if self.turn2:
            for msg in self.turn2.messages:
                if msg.session_id:
                    key = f"turn2_{msg.speaker}_msg{msg.message_number}"
                    sessions[key] = msg.session_id

        if self.synthesis and self.synthesis.session_id:
            sessions["synthesis"] = self.synthesis.session_id

        return sessions

    def to_phase_result_artifacts(self) -> dict[str, Any]:
        """Convert to artifacts dict compatible with PhaseResult."""
        artifacts = {
            "debate_enabled": True,
            "total_cost": self.total_cost,
            "claude_cost": self.claude_cost,
            "codex_cost": self.codex_cost,
        }

        if self.turn1:
            artifacts["claude_t1_file"] = str(self.turn1.claude_output_file)
            artifacts["codex_t1_file"] = str(self.turn1.codex_output_file)

        if self.turn2 and self.turn2.debate_log_path:
            artifacts["debate_log_file"] = str(self.turn2.debate_log_path)
            artifacts["message_count"] = self.turn2.message_count

        artifacts["final_output_file"] = str(self.final_output_file)
        artifacts.update(self.artifacts)

        return artifacts
