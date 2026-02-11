"""Shared utilities for the debate system."""

# Known agent display names — avoids .title() mangling hyphenated/numeric names
_KNOWN_AGENTS: dict[str, str] = {
    "claude": "Claude",
    "codex": "Codex",
    "gpt-4o": "GPT-4o",
    "gpt-4": "GPT-4",
    "gpt-4o-mini": "GPT-4o Mini",
}


def display_name(agent: str) -> str:
    """Return a human-readable display name for an agent identifier.

    Known agents get proper casing (e.g. "gpt-4o" → "GPT-4o").
    Unknown agents fall back to replacing hyphens with spaces and title-casing.
    """
    return _KNOWN_AGENTS.get(agent, agent.replace("-", " ").title())
