"""Debate transcript management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from selfassembler.debate.utils import display_name

if TYPE_CHECKING:
    from selfassembler.debate.results import Turn1Results


@dataclass
class DebateMessage:
    """Single message in a debate exchange."""

    speaker: str  # "claude" or "codex"
    message_number: int
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    role: str | None = None  # "primary" or "secondary" - supports same-agent debates

    def format_header(self, total_messages: int) -> str:
        """Format the message header for the transcript."""
        return (
            f"### [MESSAGE {self.message_number}/{total_messages}] "
            f"{display_name(self.speaker)} - {self.timestamp.strftime('%H:%M:%S')}"
        )


class DebateLog:
    """
    Manages debate transcript file for a phase.

    The transcript accumulates messages from the debate exchange,
    providing a complete record of the back-and-forth discussion.
    """

    def __init__(
        self,
        path: Path,
        total_messages: int = 3,
        primary_agent: str = "claude",
        secondary_agent: str = "codex",
    ):
        self.path = path
        self.messages: list[DebateMessage] = []
        self.total_messages = total_messages
        self.primary_agent = primary_agent
        self.secondary_agent = secondary_agent
        self._phase: str | None = None
        self._task: str | None = None

    def write_header(self, phase: str, task: str) -> None:
        """Initialize the debate log with header."""
        self._phase = phase
        self._task = task
        primary_name = display_name(self.primary_agent)
        secondary_name = display_name(self.secondary_agent)
        header = f"""# Debate Transcript: {phase}
Task: {task}
Date: {datetime.now().isoformat()}
Participants: {primary_name} (Primary), {secondary_name} (Secondary)

---
"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(header)

    def write_turn1_summary(self, t1_results: Turn1Results) -> None:
        """Write Turn 1 outputs summary section."""
        primary_name = display_name(t1_results.primary_agent)

        if t1_results.secondary_output_file is None:
            # Feedback-only mode: no secondary T1 output
            summary = f"""
## Turn 1 Output

### {primary_name}'s Analysis
[Link to: {t1_results.primary_output_file}]

---

## Feedback

"""
        else:
            secondary_name = display_name(t1_results.secondary_agent)
            summary = f"""
## Turn 1 Outputs

### {primary_name}'s Initial Analysis
[Link to: {t1_results.primary_output_file}]

### {secondary_name}'s Initial Analysis
[Link to: {t1_results.secondary_output_file}]

---

## Turn 2: Debate Exchange

"""
        with open(self.path, "a") as f:
            f.write(summary)

    def append_message(
        self,
        speaker: str,
        message_num: int,
        content: str,
        timestamp: datetime | None = None,
        role: str | None = None,
    ) -> None:
        """Append a message to the debate log.

        Args:
            speaker: Agent name (e.g., "claude", "codex")
            message_num: Message number in the exchange
            content: Message content
            timestamp: Message timestamp (defaults to now)
            role: Role in debate ("primary" or "secondary"). Required for
                  same-agent debates where speaker names are identical.
        """
        if timestamp is None:
            timestamp = datetime.now()

        msg = DebateMessage(
            speaker=speaker,
            message_number=message_num,
            content=content,
            timestamp=timestamp,
            role=role,
        )
        self.messages.append(msg)

        # Append to file
        with open(self.path, "a") as f:
            f.write(f"\n{msg.format_header(self.total_messages)}\n\n")
            f.write(content)
            f.write("\n\n---\n")

    def get_transcript(self) -> str:
        """Get the full transcript so far for context."""
        if self.path.exists():
            return self.path.read_text()
        return ""

    def get_messages_text(self) -> str:
        """Get just the messages portion of the transcript."""
        lines = []
        for msg in self.messages:
            lines.append(msg.format_header(self.total_messages))
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def write_synthesis_summary(self) -> None:
        """Append a summary section for the synthesis phase."""
        summary = self._generate_summary()
        with open(self.path, "a") as f:
            f.write("\n## Synthesis Input Summary\n\n")
            f.write(summary)

    def _generate_summary(self) -> str:
        """
        Generate a summary of the debate for synthesis.

        Extracts key points from the messages for the synthesis phase.
        """
        if not self.messages:
            return "No debate messages to summarize.\n"

        lines = [
            "**Messages Exchanged:** {count}\n".format(count=len(self.messages)),
            "",
        ]

        # Always include both agents so feedback mode (where only the
        # secondary speaks) still lists the primary.
        participants: dict[str, str] = {
            "primary": f"Primary ({display_name(self.primary_agent)})",
            "secondary": f"Secondary ({display_name(self.secondary_agent)})",
        }
        # Override with message-derived info when roles differ from defaults
        for msg in self.messages:
            key = msg.role or msg.speaker
            if key not in participants:
                name = display_name(msg.speaker)
                if msg.role:
                    participants[key] = f"{msg.role.title()} ({name})"
                else:
                    participants[key] = name
        lines.append(f"**Participants:** {', '.join(participants.values())}\n")
        lines.append("")

        # Note about unresolved items
        lines.append("**Note:** Review the full debate exchange above ")
        lines.append("to identify consensus points and remaining disagreements.\n")

        return "\n".join(lines)

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

    def get_final_positions(self) -> dict[str, str]:
        """Get the final message content from each participant.

        Keys by role (``msg.role``) when available, falling back to
        ``msg.speaker`` for backward compatibility. This avoids collisions
        when both agents have the same name.
        """
        positions = {}
        for msg in reversed(self.messages):
            key = msg.role or msg.speaker
            if key not in positions:
                positions[key] = msg.content
            if len(positions) == 2:
                break
        return positions
