"""Error classification for agent-specific vs task-specific failures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ErrorOrigin(Enum):
    """Origin classification for errors."""

    AGENT = "agent"  # Agent-level failure (rate limit, auth, token exhaustion)
    TASK = "task"  # Task-level failure (code errors, test failures)
    UNKNOWN = "unknown"  # Cannot determine origin


@dataclass
class ErrorPattern:
    """A pattern that identifies an agent-specific error."""

    pattern: str  # Regex pattern
    origin: ErrorOrigin
    description: str
    agent_types: frozenset[str] | None = None  # None = applies to all agents

    def __post_init__(self) -> None:
        self._compiled = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, text: str, agent_type: str | None = None) -> bool:
        """Check if this pattern matches the error text."""
        if self.agent_types is not None and agent_type and agent_type not in self.agent_types:
            return False
        return bool(self._compiled.search(text))


# Patterns that identify agent-specific failures
AGENT_ERROR_PATTERNS: list[ErrorPattern] = [
    # Rate limiting
    ErrorPattern(
        pattern=r"\brate[_\s-]?limit",
        origin=ErrorOrigin.AGENT,
        description="Rate limit hit",
    ),
    ErrorPattern(
        pattern=r"\btoo many requests\b",
        origin=ErrorOrigin.AGENT,
        description="Too many requests",
    ),
    ErrorPattern(
        pattern=r"\bthrottl",
        origin=ErrorOrigin.AGENT,
        description="Request throttled",
    ),
    # Token/context limits
    ErrorPattern(
        pattern=r"\btoken[_\s-]?limit",
        origin=ErrorOrigin.AGENT,
        description="Token limit exceeded",
    ),
    ErrorPattern(
        pattern=r"\bcontext[_\s-]?window",
        origin=ErrorOrigin.AGENT,
        description="Context window exhausted",
    ),
    ErrorPattern(
        pattern=r"\bmax[_\s-]?tokens\b",
        origin=ErrorOrigin.AGENT,
        description="Max tokens reached",
    ),
    ErrorPattern(
        pattern=r"\bconversation[_\s-]?too[_\s-]?long\b",
        origin=ErrorOrigin.AGENT,
        description="Conversation too long",
    ),
    ErrorPattern(
        pattern=r"\bcontext[_\s-]?length\b",
        origin=ErrorOrigin.AGENT,
        description="Context length exceeded",
    ),
    # Auth/billing
    ErrorPattern(
        pattern=r"\bauth(?:entication|orization)?\s*(?:failed|error)\b",
        origin=ErrorOrigin.AGENT,
        description="Authentication/authorization failure",
    ),
    ErrorPattern(
        pattern=r"\bunauthorized\b",
        origin=ErrorOrigin.AGENT,
        description="Unauthorized request",
    ),
    ErrorPattern(
        pattern=r"\binvalid[_\s-]?api[_\s-]?key\b",
        origin=ErrorOrigin.AGENT,
        description="Invalid API key",
    ),
    ErrorPattern(
        pattern=r"\binsufficient[_\s-]?quota\b",
        origin=ErrorOrigin.AGENT,
        description="Insufficient quota",
    ),
    ErrorPattern(
        pattern=r"\bbilling\s*(?:error|issue|problem|suspended|disabled|account)\b",
        origin=ErrorOrigin.AGENT,
        description="Billing issue",
    ),
    ErrorPattern(
        pattern=r"\bpayment[_\s-]?required\b",
        origin=ErrorOrigin.AGENT,
        description="Payment required",
    ),
    # Service errors
    ErrorPattern(
        pattern=r"\boverloaded\b",
        origin=ErrorOrigin.AGENT,
        description="Service overloaded",
    ),
    ErrorPattern(
        pattern=r"\binternal[_\s-]?server[_\s-]?error\b",
        origin=ErrorOrigin.AGENT,
        description="Internal server error",
    ),
    # SA-specific strings (exact match on strings we emit)
    ErrorPattern(
        pattern=r"possible auth",
        origin=ErrorOrigin.AGENT,
        description="SA detected possible auth issue",
    ),
    ErrorPattern(
        pattern=r"No result event received",
        origin=ErrorOrigin.AGENT,
        description="Claude produced no result event",
        agent_types=frozenset({"claude"}),
    ),
    ErrorPattern(
        pattern=r"Agent produced no output",
        origin=ErrorOrigin.AGENT,
        description="Agent produced no output",
    ),
    ErrorPattern(
        pattern=r"No parseable output",
        origin=ErrorOrigin.AGENT,
        description="No parseable output from agent",
    ),
]


@dataclass
class ClassificationResult:
    """Result of error classification."""

    origin: ErrorOrigin
    matched_patterns: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 = unknown, 1.0 = certain


def classify_error(error_text: str | None, agent_type: str | None = None) -> ClassificationResult:
    """Classify an error as agent-specific or task-specific.

    Args:
        error_text: The error message to classify
        agent_type: The agent type that produced the error (e.g., "claude", "codex")

    Returns:
        ClassificationResult with origin, matched patterns, and confidence
    """
    if not error_text:
        return ClassificationResult(origin=ErrorOrigin.UNKNOWN)

    matched = []
    for pattern in AGENT_ERROR_PATTERNS:
        if pattern.matches(error_text, agent_type):
            matched.append(pattern.description)

    if matched:
        # More matches = higher confidence
        confidence = min(1.0, 0.5 + 0.15 * len(matched))
        return ClassificationResult(
            origin=ErrorOrigin.AGENT,
            matched_patterns=matched,
            confidence=confidence,
        )

    return ClassificationResult(origin=ErrorOrigin.TASK, confidence=0.5)


def is_agent_specific_error(error_text: str | None, agent_type: str | None = None) -> bool:
    """Check if an error is agent-specific (rate limit, auth, token exhaustion, etc.).

    Args:
        error_text: The error message to check
        agent_type: The agent type that produced the error

    Returns:
        True if the error is agent-specific
    """
    result = classify_error(error_text, agent_type)
    return result.origin == ErrorOrigin.AGENT
