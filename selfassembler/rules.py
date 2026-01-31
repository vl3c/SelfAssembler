"""Rules and guidelines module for SelfAssembler.

Provides structured rules that can be rendered into CLAUDE.md files
for controlling Claude's behavior in worktrees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Rule:
    """A single rule or guideline for Claude's behavior."""

    id: str
    description: str
    category: str = field(default="general")


BUILTIN_RULES: dict[str, Rule] = {
    "no-signature": Rule(
        id="no-signature",
        description=(
            "Do not add Co-Authored-By, signature lines, or AI attribution "
            "to commits, PRs, or code comments"
        ),
        category="commits",
    ),
    "no-emojis": Rule(
        id="no-emojis",
        description="Do not use emojis in code, commits, or documentation",
        category="style",
    ),
    "no-yapping": Rule(
        id="no-yapping",
        description="Be concise, avoid excessive explanations or verbose output",
        category="communication",
    ),
}


class RulesManager:
    """Manages rules and renders them to CLAUDE.md files."""

    def __init__(
        self,
        enabled_rules: list[str] | None = None,
        custom_rules: list[str] | None = None,
    ):
        """Initialize the RulesManager.

        Args:
            enabled_rules: List of builtin rule IDs to enable.
            custom_rules: List of custom rule description strings.
        """
        self.enabled_rules = enabled_rules or []
        self.custom_rules = custom_rules or []

    def get_active_rules(self) -> list[Rule]:
        """Get all active rules (enabled builtin + custom).

        Returns:
            List of Rule objects for all active rules.
        """
        rules: list[Rule] = []

        # Add enabled builtin rules
        for rule_id in self.enabled_rules:
            if rule_id in BUILTIN_RULES:
                rules.append(BUILTIN_RULES[rule_id])

        # Add custom rules
        for i, description in enumerate(self.custom_rules):
            rules.append(
                Rule(
                    id=f"custom-{i + 1}",
                    description=description,
                    category="custom",
                )
            )

        return rules

    def render_markdown(self) -> str:
        """Render active rules as markdown for CLAUDE.md file.

        Returns:
            Markdown string containing all active rules.
        """
        rules = self.get_active_rules()

        if not rules:
            return ""

        lines = [
            "# Project Rules",
            "",
            "The following rules MUST be followed:",
            "",
        ]

        for rule in rules:
            lines.append(f"- {rule.description}")

        lines.append("")

        return "\n".join(lines)

    def write_to_worktree(self, worktree_path: Path) -> None:
        """Write CLAUDE.md to the worktree.

        Args:
            worktree_path: Path to the worktree directory.
        """
        content = self.render_markdown()

        if not content:
            return

        claude_md_path = worktree_path / "CLAUDE.md"
        claude_md_path.write_text(content)
