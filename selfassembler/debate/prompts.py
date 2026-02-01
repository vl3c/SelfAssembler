"""Prompt generators for multi-agent debate."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selfassembler.debate.results import Turn1Results


class BaseDebatePromptGenerator(ABC):
    """Base class for debate prompt generators."""

    phase_name: str = "base"

    def __init__(
        self,
        task_description: str,
        task_name: str,
        plans_dir: Path,
        primary_agent: str = "Claude",
        secondary_agent: str = "Codex",
    ):
        self.task_description = task_description
        self.task_name = task_name
        self.plans_dir = plans_dir
        self.primary_agent = primary_agent.title()  # Capitalize for display
        self.secondary_agent = secondary_agent.title()

    # -------------------------------------------------------------------------
    # Turn 1: Independent Generation Prompts
    # -------------------------------------------------------------------------

    @abstractmethod
    def turn1_primary_prompt(self, output_file: Path) -> str:
        """Generate Turn 1 prompt for primary agent (Claude)."""
        pass

    @abstractmethod
    def turn1_secondary_prompt(self, output_file: Path) -> str:
        """Generate Turn 1 prompt for secondary agent (Codex)."""
        pass

    # -------------------------------------------------------------------------
    # Turn 2: Debate Exchange Prompts
    # -------------------------------------------------------------------------

    def debate_message_prompt(
        self,
        speaker: str,
        message_number: int,
        total_messages: int,
        transcript_so_far: str,
        own_t1_output: Path,
        other_t1_output: Path,
        is_final_message: bool,
    ) -> str:
        """Generate prompt for a debate message.

        Args:
            speaker: "claude" or "codex" - the agent sending this message
            message_number: 1-indexed message number in the exchange
            total_messages: Total messages in the debate (should be odd)
            transcript_so_far: Debate transcript accumulated so far
            own_t1_output: Path to this speaker's Turn 1 output
            other_t1_output: Path to the other agent's Turn 1 output
            is_final_message: True if this is the last message in the debate
        """
        if is_final_message:
            # Final message is always Claude's closing rebuttal
            return self._final_message_prompt(
                speaker=speaker,
                transcript_so_far=transcript_so_far,
                own_t1_output=own_t1_output,
                message_number=message_number,
                total_messages=total_messages,
            )
        elif speaker == "claude":
            # Claude's opening or intermediate message
            return self._claude_message_prompt(
                transcript_so_far=transcript_so_far,
                own_t1_output=own_t1_output,
                other_t1_output=other_t1_output,
                message_number=message_number,
                total_messages=total_messages,
            )
        else:
            # Codex's response
            return self._codex_message_prompt(
                transcript_so_far=transcript_so_far,
                own_t1_output=own_t1_output,
                message_number=message_number,
                total_messages=total_messages,
            )

    def _claude_message_prompt(
        self,
        transcript_so_far: str,
        own_t1_output: Path,
        other_t1_output: Path,
        message_number: int,
        total_messages: int,
    ) -> str:
        """Generate primary agent's message prompt (opening or intermediate)."""
        context_section = f"""## Context
You are the PRIMARY agent ({self.primary_agent}) in a multi-agent debate.

- Your original analysis: {own_t1_output}
- {self.secondary_agent}'s analysis: {other_t1_output}
"""
        if message_number > 1:
            context_section = f"""## Previous Exchange
{transcript_so_far}

## Your Original Analysis
Reference: {own_t1_output}
"""

        return f"""# Debate: {self.phase_name} - Message {message_number} of {total_messages} ({self.primary_agent})

{context_section}
## Instructions
Read both analyses and provide your response:

### Points of Agreement
[What {self.secondary_agent} got right that aligns with your analysis]

### Points of Disagreement
[Where you believe {self.secondary_agent}'s analysis is incomplete/incorrect, with reasoning]

### Gaps {self.secondary_agent} Identified
[Valid points from {self.secondary_agent} that you missed - concede these openly]

### Your Revised Position
[Your updated analysis incorporating valid feedback]

---
NOTE: This is message {message_number} of {total_messages}. {self.secondary_agent} will respond next.
"""

    def _codex_message_prompt(
        self,
        transcript_so_far: str,
        own_t1_output: Path,
        message_number: int,
        total_messages: int,
    ) -> str:
        """Generate secondary agent's response prompt."""
        return f"""# Debate: {self.phase_name} - Message {message_number} of {total_messages} ({self.secondary_agent})

## Previous Exchange
{transcript_so_far}

## Your Original Analysis
Read: {own_t1_output}

## Instructions
Respond to {self.primary_agent}'s critique:

### Addressing {self.primary_agent}'s Disagreements
[For each point {self.primary_agent} disagreed with, provide counter-argument or concede]

### Additional Evidence
[New findings or reasoning that supports your original points]

### Revised Position
[Your updated analysis - what you now stand by and what you've revised]

---
NOTE: This is message {message_number} of {total_messages}. {self.primary_agent} will respond next.
"""

    def _final_message_prompt(
        self,
        speaker: str,
        transcript_so_far: str,
        own_t1_output: Path,
        message_number: int,
        total_messages: int,
    ) -> str:
        """Generate final message prompt (primary agent's closing rebuttal)."""
        return f"""# Debate: {self.phase_name} - Message {message_number} of {total_messages} ({self.primary_agent} - FINAL)

## Full Exchange
{transcript_so_far}

## Instructions
Provide your final position:

### Resolved Disagreements
[Points where you reached consensus with {self.secondary_agent}]

### Remaining Disagreements
[Points where you still differ - document both positions clearly]

### Your Final Analysis
[Your conclusive position going into synthesis, incorporating the full debate]

---
NOTE: This is the final debate message. Synthesis will follow.
"""

    # -------------------------------------------------------------------------
    # Turn 3: Synthesis Prompt
    # -------------------------------------------------------------------------

    def synthesis_prompt(
        self,
        t1_results: Turn1Results,
        debate_transcript: str,
        final_output_file: Path,
    ) -> str:
        """Generate the synthesis prompt for Turn 3."""
        return f"""# Synthesis: {self.phase_name} (Turn 3 of 3 - FINAL)

You are synthesizing outputs from a multi-agent debate.

## Available Inputs
1. Your original output: {t1_results.claude_output_file}
2. {self.secondary_agent} original output: {t1_results.codex_output_file}
3. Full debate transcript (contains revised positions):

{debate_transcript}

## Synthesis Criteria (Priority Order)
1. **Correctness**: Verified facts over claims
2. **Evidence**: Claims with code references preferred
3. **Completeness**: Include all valid findings from both agents
4. **Consensus**: Higher confidence for agreed points
5. **Primary preference**: When equivalent, prefer your analysis

## Handling Conflicts
- If both agents agree: Include with high confidence
- If complementary: Merge both perspectives
- If contradictory with evidence: Use evidenced version
- If contradictory without evidence: Document both in "## Open Questions"

## Output Structure
{self._get_output_structure()}

### Synthesis Notes
At the end, add:
- **Agreements**: Major points both agents agreed on
- **Resolved Conflicts**: Conflicts and how they were resolved
- **Open Questions**: Unresolved disagreements needing review

Write your final synthesized output to: {final_output_file}
"""

    @abstractmethod
    def _get_output_structure(self) -> str:
        """Get the expected output structure for this phase."""
        pass


class ResearchDebatePrompts(BaseDebatePromptGenerator):
    """Prompt generator for research phase debate."""

    phase_name = "research"

    def turn1_primary_prompt(self, output_file: Path) -> str:
        return f"""# Research Task: {self.task_description}

You are the PRIMARY agent ({self.primary_agent}) in a multi-agent workflow.

## Instructions

1. Read project conventions:
   - Look for: claude.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, .claude/*
   - Understand coding standards, patterns, and constraints

2. Find related code:
   - Search for files related to this feature
   - Understand existing patterns and conventions
   - Note reusable utilities or components

3. Identify dependencies:
   - External packages needed
   - Internal modules to import
   - API contracts to follow

## Guidelines
- Be thorough and detailed in your analysis
- Document your reasoning and alternatives considered
- Note uncertainties - another agent will also analyze this
- This is Turn 1 of 3 in a debate process

Write your findings to: {output_file}

Format the research as markdown with clear sections.
"""

    def turn1_secondary_prompt(self, output_file: Path) -> str:
        return f"""# Research Task: {self.task_description}

You are the SECONDARY agent ({self.secondary_agent}) in a multi-agent workflow.

## Instructions

1. Read project conventions:
   - Look for: claude.md, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, .claude/*
   - Understand coding standards, patterns, and constraints

2. Find related code:
   - Search for files related to this feature
   - Understand existing patterns and conventions
   - Note reusable utilities or components

3. Identify dependencies:
   - External packages needed
   - Internal modules to import
   - API contracts to follow

## Guidelines
- Provide an independent perspective
- Focus on areas the primary agent might miss
- Suggest alternative approaches where valid
- This is Turn 1 of 3 - your work will be compared with another agent

Write your findings to: {output_file}

Format the research as markdown with clear sections.
"""

    def _get_output_structure(self) -> str:
        return """Use standard research output format with sections:
- Project Conventions
- Related Code
- Dependencies
- Key Findings"""


class PlanningDebatePrompts(BaseDebatePromptGenerator):
    """Prompt generator for planning phase debate."""

    phase_name = "planning"

    def turn1_primary_prompt(self, output_file: Path) -> str:
        research_file = self.plans_dir / f"research-{self.task_name}.md"
        research_ref = ""
        if research_file.exists():
            research_ref = f"\nReference the research at: {research_file}\n"

        return f"""# Planning Task: {self.task_description}

You are the PRIMARY agent (Claude Code) in a multi-agent workflow.
{research_ref}
## Instructions

Create a detailed implementation plan:

```markdown
# Implementation Plan: {self.task_name}

## Summary
[1-2 sentence overview of what will be implemented]

## Files to Modify/Create
- [ ] path/to/file.ext - [brief description of changes]

## Implementation Steps
### Step 1: [Name]
- Description: What this step accomplishes
- Files involved: ...
- Acceptance criteria: How to verify this step is complete

### Step 2: ...

## Testing Strategy
- [ ] Unit tests for...
- [ ] Integration tests for...

## Risks/Blockers
- Any potential issues or dependencies
```

## Guidelines
- Be thorough and detailed
- Consider edge cases and error handling
- This is Turn 1 of 3 in a debate process

Write your plan to: {output_file}
"""

    def turn1_secondary_prompt(self, output_file: Path) -> str:
        research_file = self.plans_dir / f"research-{self.task_name}.md"
        research_ref = ""
        if research_file.exists():
            research_ref = f"\nReference the research at: {research_file}\n"

        return f"""# Planning Task: {self.task_description}

You are the SECONDARY agent ({self.secondary_agent}) in a multi-agent workflow.
{research_ref}
## Instructions

Create a detailed implementation plan with your independent perspective.

Use this format:
```markdown
# Implementation Plan: {self.task_name}

## Summary
## Files to Modify/Create
## Implementation Steps
## Testing Strategy
## Risks/Blockers
```

## Guidelines
- Provide an alternative perspective to the primary agent
- Consider different architectural approaches
- Focus on areas that might be overlooked
- This is Turn 1 of 3 - your work will be compared

Write your plan to: {output_file}
"""

    def _get_output_structure(self) -> str:
        return """Use standard plan format:
- Summary
- Files to Modify/Create
- Implementation Steps
- Testing Strategy
- Risks/Blockers"""


class PlanReviewDebatePrompts(BaseDebatePromptGenerator):
    """Prompt generator for plan review phase debate."""

    phase_name = "plan_review"

    def turn1_primary_prompt(self, output_file: Path) -> str:
        plan_file = self.plans_dir / f"plan-{self.task_name}.md"

        return f"""# Plan Review Task: {self.task_description}

You are the PRIMARY agent (Claude Code) in a multi-agent workflow.

## Instructions

1. Read the plan at: {plan_file}

2. Perform a SWOT analysis of the plan:
   - Strengths: What's well-planned and will likely succeed?
   - Weaknesses: What's missing, unclear, or poorly planned?
   - Opportunities: What could be improved or added?
   - Threats: What could go wrong? What are the risks?

3. Write your review to: {output_file}

Format:
```markdown
# Plan Review: {self.task_name}

## SWOT Analysis

### Strengths
- [What's well-planned]

### Weaknesses
- [What's missing or unclear]

### Opportunities
- [Improvements to consider]

### Threats
- [Risks and potential issues]

## Recommended Changes
- [Specific improvements to make]

## Verdict
[Overall assessment: Ready/Needs Revision/Major Concerns]
```

## Guidelines
- Be thorough but constructive
- This is Turn 1 of 3 in a debate process
"""

    def turn1_secondary_prompt(self, output_file: Path) -> str:
        plan_file = self.plans_dir / f"plan-{self.task_name}.md"

        return f"""# Plan Review Task: {self.task_description}

You are the SECONDARY agent ({self.secondary_agent}) in a multi-agent workflow.

## Instructions

1. Read the plan at: {plan_file}

2. Perform an independent SWOT analysis focusing on areas the primary reviewer might miss.

3. Write your review to: {output_file}

Use the same format:
- SWOT Analysis (Strengths, Weaknesses, Opportunities, Threats)
- Recommended Changes
- Verdict

## Guidelines
- Provide an independent critical perspective
- Focus on technical feasibility and edge cases
- This is Turn 1 of 3 - your review will be compared
"""

    def _get_output_structure(self) -> str:
        return """Use standard review format:
- SWOT Analysis
- Recommended Changes
- Verdict"""


class CodeReviewDebatePrompts(BaseDebatePromptGenerator):
    """Prompt generator for code review phase debate."""

    phase_name = "code_review"

    def __init__(
        self,
        task_description: str,
        task_name: str,
        plans_dir: Path,
        primary_agent: str = "Claude",
        secondary_agent: str = "Codex",
        base_branch: str = "main",
    ):
        super().__init__(
            task_description=task_description,
            task_name=task_name,
            plans_dir=plans_dir,
            primary_agent=primary_agent,
            secondary_agent=secondary_agent,
        )
        self.base_branch = base_branch

    def turn1_primary_prompt(self, output_file: Path) -> str:
        return f"""# Code Review Task: {self.task_description}

You are the PRIMARY agent ({self.primary_agent}) in a multi-agent workflow.

## Instructions

1. Get the diff: git diff {self.base_branch}...HEAD

2. Review for:
   - Logic errors or bugs
   - Security issues (injection, XSS, CSRF, etc.)
   - Performance problems
   - Missing edge cases
   - Code style violations
   - Incomplete implementations
   - TODOs or debug code left in
   - Hardcoded values that should be configurable
   - Missing error handling

3. Write your review findings to: {output_file}

Format:
```markdown
# Code Review: {self.task_name}

## Summary
[Overall assessment]

## Issues Found

### Critical
- [Issue description with file:line reference]

### Major
- [Issue description]

### Minor
- [Issue description]

## Suggestions
- [Optional improvements]
```

## Guidelines
- Be thorough and document specific locations
- This is Turn 1 of 3 in a debate process
"""

    def turn1_secondary_prompt(self, output_file: Path) -> str:
        return f"""# Code Review Task: {self.task_description}

You are the SECONDARY agent ({self.secondary_agent}) in a multi-agent workflow.

## Instructions

1. Get the diff: git diff {self.base_branch}...HEAD

2. Review independently for issues the primary reviewer might miss:
   - Logic errors or bugs
   - Security issues
   - Performance problems
   - Edge cases
   - Code quality

3. Write your review to: {output_file}

Use the same format:
- Summary
- Issues Found (Critical/Major/Minor)
- Suggestions

## Guidelines
- Focus on different aspects than a typical review
- Consider alternative implementations
- This is Turn 1 of 3 - your review will be compared
"""

    def _get_output_structure(self) -> str:
        return """Use standard code review format:
- Summary
- Issues Found (Critical/Major/Minor)
- Suggestions"""


def get_prompt_generator(
    phase_name: str,
    task_description: str,
    task_name: str,
    plans_dir: Path,
    primary_agent: str = "Claude",
    secondary_agent: str = "Codex",
    **kwargs,
) -> BaseDebatePromptGenerator:
    """Factory function to get the appropriate prompt generator for a phase.

    Args:
        phase_name: Name of the phase (research, planning, plan_review, code_review)
        task_description: Description of the task
        task_name: Short name for the task
        plans_dir: Path to plans directory
        primary_agent: Name of the primary agent (default: Claude)
        secondary_agent: Name of the secondary agent (default: Codex)
        **kwargs: Additional arguments passed to the generator
    """
    generators = {
        "research": ResearchDebatePrompts,
        "planning": PlanningDebatePrompts,
        "plan_review": PlanReviewDebatePrompts,
        "code_review": CodeReviewDebatePrompts,
    }

    generator_class = generators.get(phase_name)
    if generator_class is None:
        raise ValueError(f"No prompt generator for phase: {phase_name}")

    return generator_class(
        task_description=task_description,
        task_name=task_name,
        plans_dir=plans_dir,
        primary_agent=primary_agent,
        secondary_agent=secondary_agent,
        **kwargs,
    )
