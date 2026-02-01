"""File management for debate system outputs."""

from __future__ import annotations

from pathlib import Path


class DebateFileManager:
    """
    Manages file paths for debate outputs.

    Handles the organization of:
    - Agent-specific outputs (Turn 1)
    - Debate transcripts (Turn 2)
    - Final synthesized outputs (Turn 3)

    Note: File paths use roles ("primary"/"secondary") not agent names to support
    same-agent debates (e.g., Claude vs Claude or Codex vs Codex).
    """

    def __init__(self, plans_dir: Path, task_name: str, debate_subdir: str = "debates"):
        self.plans_dir = plans_dir
        self.task_name = task_name
        self.debate_subdir = debate_subdir
        self._debates_dir = plans_dir / debate_subdir

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self._debates_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Turn 1: Role-based output files
    # -------------------------------------------------------------------------

    def get_role_output_path(self, phase: str, role: str) -> Path:
        """
        Get the path for a role's Turn 1 output.

        Args:
            phase: Phase name (e.g., "research")
            role: Role identifier ("primary" or "secondary")

        Example: plans/research-mytask-primary.md

        Using roles instead of agent names allows same-agent debates
        (e.g., Claude vs Claude).
        """
        filename = f"{phase}-{self.task_name}-{role}.md"
        return self.plans_dir / filename

    def get_primary_t1_path(self, phase: str) -> Path:
        """Get primary agent's Turn 1 output path."""
        return self.get_role_output_path(phase, "primary")

    def get_secondary_t1_path(self, phase: str) -> Path:
        """Get secondary agent's Turn 1 output path."""
        return self.get_role_output_path(phase, "secondary")

    # Backward compatibility aliases
    def get_agent_output_path(self, phase: str, agent: str) -> Path:
        """
        Get the path for an agent's Turn 1 output.

        DEPRECATED: Use get_role_output_path() instead.
        This method is kept for backward compatibility.

        Example: plans/research-mytask-claude.md
        """
        filename = f"{phase}-{self.task_name}-{agent}.md"
        return self.plans_dir / filename

    def get_claude_t1_path(self, phase: str) -> Path:
        """Get Claude's Turn 1 output path (backward compatible)."""
        return self.get_agent_output_path(phase, "claude")

    def get_codex_t1_path(self, phase: str) -> Path:
        """Get Codex's Turn 1 output path (backward compatible)."""
        return self.get_agent_output_path(phase, "codex")

    # -------------------------------------------------------------------------
    # Turn 2: Debate transcript files
    # -------------------------------------------------------------------------

    def get_debate_path(self, phase: str) -> Path:
        """
        Get the path for the debate transcript.

        Example: plans/debates/research-mytask-debate.md
        """
        filename = f"{phase}-{self.task_name}-debate.md"
        return self._debates_dir / filename

    # -------------------------------------------------------------------------
    # Turn 3: Final synthesized output files
    # -------------------------------------------------------------------------

    def get_final_output_path(self, phase: str) -> Path:
        """
        Get the path for the final synthesized output.

        Example: plans/research-mytask.md

        This matches the standard single-agent output path for backward compatibility.
        """
        filename = f"{phase}-{self.task_name}.md"
        return self.plans_dir / filename

    # -------------------------------------------------------------------------
    # Phase-specific convenience methods
    # -------------------------------------------------------------------------

    def get_research_paths(self) -> dict[str, Path]:
        """Get all file paths for research phase debate."""
        return {
            "primary_t1": self.get_primary_t1_path("research"),
            "secondary_t1": self.get_secondary_t1_path("research"),
            "debate": self.get_debate_path("research"),
            "final": self.get_final_output_path("research"),
        }

    def get_planning_paths(self) -> dict[str, Path]:
        """Get all file paths for planning phase debate."""
        return {
            "primary_t1": self.get_primary_t1_path("plan"),
            "secondary_t1": self.get_secondary_t1_path("plan"),
            "debate": self.get_debate_path("plan"),
            "final": self.get_final_output_path("plan"),
        }

    def get_plan_review_paths(self) -> dict[str, Path]:
        """Get all file paths for plan review phase debate."""
        return {
            "primary_t1": self.get_primary_t1_path("plan-review"),
            "secondary_t1": self.get_secondary_t1_path("plan-review"),
            "debate": self.get_debate_path("plan-review"),
            "final": self.get_final_output_path("plan-review"),
        }

    def get_code_review_paths(self) -> dict[str, Path]:
        """Get all file paths for code review phase debate."""
        return {
            "primary_t1": self.get_primary_t1_path("review"),
            "secondary_t1": self.get_secondary_t1_path("review"),
            "debate": self.get_debate_path("review"),
            "final": self.get_final_output_path("review"),
        }

    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------

    def list_all_debate_files(self) -> list[Path]:
        """List all debate-related files for this task."""
        files = []

        # Role-based outputs
        for phase in ["research", "plan", "plan-review", "review"]:
            files.append(self.get_primary_t1_path(phase))
            files.append(self.get_secondary_t1_path(phase))
            files.append(self.get_debate_path(phase))
            files.append(self.get_final_output_path(phase))

        return [f for f in files if f.exists()]

    def cleanup_intermediate_files(self) -> list[Path]:
        """
        Remove intermediate debate files, keeping only final outputs.

        Returns list of removed files.
        """
        removed = []
        for phase in ["research", "plan", "plan-review", "review"]:
            # Remove role-specific files
            for role in ["primary", "secondary"]:
                path = self.get_role_output_path(phase, role)
                if path.exists():
                    path.unlink()
                    removed.append(path)

            # Remove debate transcript
            debate_path = self.get_debate_path(phase)
            if debate_path.exists():
                debate_path.unlink()
                removed.append(debate_path)

        return removed
