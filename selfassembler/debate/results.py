"""Result dataclasses for debate system."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from selfassembler.executors.base import ExecutionResult


@dataclass
class DebateMessage:
    """A single message in the debate exchange."""

    speaker: str  # Agent name (e.g., "claude" or "codex")
    message_number: int
    content: str
    result: ExecutionResult | None = None
    role: str | None = None  # "primary" or "secondary" - supports same-agent debates

    @property
    def cost_usd(self) -> float:
        """Get the cost of this message."""
        return self.result.cost_usd if self.result else 0.0

    @property
    def session_id(self) -> str | None:
        """Get the session ID from this message's execution."""
        return self.result.session_id if self.result else None

    @property
    def is_primary(self) -> bool:
        """Check if this message is from the primary agent."""
        return self.role == "primary"

    @property
    def is_secondary(self) -> bool:
        """Check if this message is from the secondary agent."""
        return self.role == "secondary"


@dataclass
class Turn1Results:
    """Results from Turn 1 parallel generation."""

    primary_result: ExecutionResult
    secondary_result: ExecutionResult
    primary_output_file: Path
    secondary_output_file: Path
    primary_agent: str = "claude"
    secondary_agent: str = "codex"

    # Backward compatibility aliases
    @property
    def claude_result(self) -> ExecutionResult:
        """Backward compatible alias for primary_result."""
        return self.primary_result

    @property
    def codex_result(self) -> ExecutionResult:
        """Backward compatible alias for secondary_result."""
        return self.secondary_result

    @property
    def claude_output_file(self) -> Path:
        """Backward compatible alias for primary_output_file."""
        return self.primary_output_file

    @property
    def codex_output_file(self) -> Path:
        """Backward compatible alias for secondary_output_file."""
        return self.secondary_output_file

    @property
    def total_cost(self) -> float:
        """Get combined cost of Turn 1."""
        return self.primary_result.cost_usd + self.secondary_result.cost_usd

    def get(self, agent: str) -> ExecutionResult:
        """Get result for a specific agent."""
        if agent == self.primary_agent:
            return self.primary_result
        elif agent == self.secondary_agent:
            return self.secondary_result
        else:
            raise ValueError(f"Unknown agent: {agent}")

    def get_output_file(self, agent: str) -> Path:
        """Get output file path for a specific agent."""
        if agent == self.primary_agent:
            return self.primary_output_file
        elif agent == self.secondary_agent:
            return self.secondary_output_file
        else:
            raise ValueError(f"Unknown agent: {agent}")

    def get_output_file_by_role(self, role: str) -> Path:
        """Get output file path by role (primary/secondary).

        This method should be preferred over get_output_file() when working
        with same-agent debates where primary_agent == secondary_agent.
        """
        if role == "primary":
            return self.primary_output_file
        elif role == "secondary":
            return self.secondary_output_file
        else:
            raise ValueError(f"Unknown role: {role}. Must be 'primary' or 'secondary'")


@dataclass
class Turn2Results:
    """Results from Turn 2 debate exchange."""

    messages: list[DebateMessage] = field(default_factory=list)
    debate_log_path: Path | None = None
    primary_agent: str = "claude"
    secondary_agent: str = "codex"

    @property
    def total_cost(self) -> float:
        """Get combined cost of Turn 2."""
        return sum(msg.cost_usd for msg in self.messages)

    @property
    def message_count(self) -> int:
        """Get the number of messages exchanged."""
        return len(self.messages)

    def get_agent_messages(self, agent: str) -> list[DebateMessage]:
        """Get all messages from a specific agent."""
        return [m for m in self.messages if m.speaker == agent]

    def get_role_messages(self, role: str) -> list[DebateMessage]:
        """Get all messages from a specific role ("primary" or "secondary")."""
        return [m for m in self.messages if m.role == role]

    def get_primary_messages(self) -> list[DebateMessage]:
        """Get all messages from the primary agent.

        Uses the role field to correctly handle same-agent debates.
        """
        # Use role field if available (supports same-agent debates)
        role_msgs = self.get_role_messages("primary")
        if role_msgs:
            return role_msgs
        # Fallback to agent name for backward compatibility
        return self.get_agent_messages(self.primary_agent)

    def get_secondary_messages(self) -> list[DebateMessage]:
        """Get all messages from the secondary agent.

        Uses the role field to correctly handle same-agent debates.
        """
        # Use role field if available (supports same-agent debates)
        role_msgs = self.get_role_messages("secondary")
        if role_msgs:
            return role_msgs
        # Fallback to agent name for backward compatibility
        return self.get_agent_messages(self.secondary_agent)

    # Backward compatibility
    def get_claude_messages(self) -> list[DebateMessage]:
        """Get all messages from Claude (backward compatible)."""
        return [m for m in self.messages if m.speaker == "claude"]

    def get_codex_messages(self) -> list[DebateMessage]:
        """Get all messages from Codex (backward compatible)."""
        return [m for m in self.messages if m.speaker == "codex"]

    def get_final_primary_session(self) -> str | None:
        """Get the session ID from primary agent's final message."""
        primary_msgs = self.get_primary_messages()
        if primary_msgs:
            return primary_msgs[-1].session_id
        return None

    def get_final_claude_session(self) -> str | None:
        """Get the session ID from Claude's final message (backward compatible)."""
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
    def primary_cost(self) -> float:
        """Get cost attributed to primary agent."""
        cost = 0.0
        if self.turn1:
            cost += self.turn1.primary_result.cost_usd
        if self.turn2:
            for msg in self.turn2.get_primary_messages():
                cost += msg.cost_usd
        if self.synthesis:
            cost += self.synthesis.cost_usd
        return cost

    @property
    def secondary_cost(self) -> float:
        """Get cost attributed to secondary agent."""
        cost = 0.0
        if self.turn1:
            cost += self.turn1.secondary_result.cost_usd
        if self.turn2:
            for msg in self.turn2.get_secondary_messages():
                cost += msg.cost_usd
        return cost

    # Backward compatibility aliases
    @property
    def claude_cost(self) -> float:
        """Get cost attributed to Claude (backward compatible)."""
        return self.primary_cost

    @property
    def codex_cost(self) -> float:
        """Get cost attributed to Codex (backward compatible)."""
        return self.secondary_cost

    def get_session_ids(self) -> dict[str, str]:
        """Get all session IDs from the debate."""
        sessions = {}

        if self.turn1:
            primary = self.turn1.primary_agent
            secondary = self.turn1.secondary_agent
            if self.turn1.primary_result.session_id:
                sessions[f"turn1_{primary}"] = self.turn1.primary_result.session_id
            if self.turn1.secondary_result.session_id:
                sessions[f"turn1_{secondary}"] = self.turn1.secondary_result.session_id

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
            "primary_cost": self.primary_cost,
            "secondary_cost": self.secondary_cost,
        }

        if self.turn1:
            primary = self.turn1.primary_agent
            secondary = self.turn1.secondary_agent
            artifacts["primary_agent"] = primary
            artifacts["secondary_agent"] = secondary
            artifacts[f"{primary}_t1_file"] = str(self.turn1.primary_output_file)
            artifacts[f"{secondary}_t1_file"] = str(self.turn1.secondary_output_file)

        if self.turn2 and self.turn2.debate_log_path:
            artifacts["debate_log_file"] = str(self.turn2.debate_log_path)
            artifacts["message_count"] = self.turn2.message_count

        artifacts["final_output_file"] = str(self.final_output_file)
        artifacts.update(self.artifacts)

        return artifacts
