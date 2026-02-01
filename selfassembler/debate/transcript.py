"""Debate transcript management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selfassembler.debate.results import Turn1Results


@dataclass
class DebateMessage:
    """Single message in a debate exchange."""

    speaker: str  # "claude" or "codex"
    message_number: int
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def format_header(self, total_messages: int) -> str:
        """Format the message header for the transcript."""
        return (
            f"### [MESSAGE {self.message_number}/{total_messages}] "
            f"{self.speaker.title()} - {self.timestamp.strftime('%H:%M:%S')}"
        )


class DebateLog:
    """
    Manages debate transcript file for a phase.

    The transcript accumulates messages from the debate exchange,
    providing a complete record of the back-and-forth discussion.
    """

    def __init__(self, path: Path, total_messages: int = 3):
        self.path = path
        self.messages: list[DebateMessage] = []
        self.total_messages = total_messages
        self._phase: str | None = None
        self._task: str | None = None

    def write_header(self, phase: str, task: str) -> None:
        """Initialize the debate log with header."""
        self._phase = phase
        self._task = task
        header = f"""# Debate Transcript: {phase}
Task: {task}
Date: {datetime.now().isoformat()}
Participants: Claude (Primary), Codex (Secondary)

---
"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(header)

    def write_turn1_summary(self, t1_results: Turn1Results) -> None:
        """Write Turn 1 outputs summary section."""
        summary = f"""
## Turn 1 Outputs

### Claude's Initial Analysis
[Link to: {t1_results.claude_output_file}]

### Codex's Initial Analysis
[Link to: {t1_results.codex_output_file}]

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
    ) -> None:
        """Append a message to the debate log."""
        if timestamp is None:
            timestamp = datetime.now()

        msg = DebateMessage(
            speaker=speaker,
            message_number=message_num,
            content=content,
            timestamp=timestamp,
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

        # Extract speakers
        speakers = set(msg.speaker for msg in self.messages)
        lines.append(f"**Participants:** {', '.join(s.title() for s in speakers)}\n")
        lines.append("")

        # Note about unresolved items
        lines.append("**Note:** Review the full debate exchange above ")
        lines.append("to identify consensus points and remaining disagreements.\n")

        return "\n".join(lines)

    def get_claude_messages(self) -> list[DebateMessage]:
        """Get all messages from Claude."""
        return [m for m in self.messages if m.speaker == "claude"]

    def get_codex_messages(self) -> list[DebateMessage]:
        """Get all messages from Codex."""
        return [m for m in self.messages if m.speaker == "codex"]

    def get_final_positions(self) -> dict[str, str]:
        """Get the final message content from each speaker."""
        positions = {}
        for msg in reversed(self.messages):
            if msg.speaker not in positions:
                positions[msg.speaker] = msg.content
            if len(positions) == 2:
                break
        return positions
