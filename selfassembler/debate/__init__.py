"""Multi-agent debate system for SelfAssembler."""

from selfassembler.debate.files import DebateFileManager
from selfassembler.debate.orchestrator import DebateOrchestrator
from selfassembler.debate.prompts import (
    BaseDebatePromptGenerator,
    CodeReviewDebatePrompts,
    PlanningDebatePrompts,
    PlanReviewDebatePrompts,
    ResearchDebatePrompts,
)
from selfassembler.debate.results import (
    DebateMessage,
    DebateResult,
    Turn1Results,
    Turn2Results,
)
from selfassembler.debate.transcript import DebateLog
from selfassembler.debate.utils import display_name

__all__ = [
    # Core orchestration
    "DebateOrchestrator",
    "DebateLog",
    "DebateFileManager",
    # Result types
    "DebateResult",
    "DebateMessage",
    "Turn1Results",
    "Turn2Results",
    # Prompt generators
    "BaseDebatePromptGenerator",
    "ResearchDebatePrompts",
    "PlanningDebatePrompts",
    "PlanReviewDebatePrompts",
    "CodeReviewDebatePrompts",
    # Utilities
    "display_name",
]
