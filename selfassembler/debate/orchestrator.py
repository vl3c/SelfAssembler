"""Debate orchestrator for multi-agent collaboration."""

from __future__ import annotations

import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from selfassembler.debate.files import DebateFileManager
from selfassembler.debate.prompts import BaseDebatePromptGenerator
from selfassembler.debate.results import (
    DebateMessage,
    DebateResult,
    SynthesisResult,
    Turn1Results,
    Turn2Results,
)
from selfassembler.debate.transcript import DebateLog

if TYPE_CHECKING:
    from selfassembler.config import DebateConfig
    from selfassembler.context import WorkflowContext
    from selfassembler.executors import AgentExecutor


class DebateOrchestrator:
    """
    Orchestrates multi-agent debate within a phase.

    Supports two modes:
    - **Feedback** (default): Primary generates → Secondary reviews → Primary synthesizes
    - **Debate**: Both generate independently → Exchange critiques → Primary synthesizes
    """

    def __init__(
        self,
        primary_executor: AgentExecutor,
        secondary_executor: AgentExecutor,
        config: DebateConfig,
        context: WorkflowContext,
        file_manager: DebateFileManager,
    ):
        self.primary = primary_executor
        self.secondary = secondary_executor
        self.config = config
        self.context = context
        self.files = file_manager
        # Store agent names for dynamic role mapping
        self.primary_agent = config.primary_agent
        self.secondary_agent = config.secondary_agent
        # Set during run_debate() to use phase-specific limits
        self._max_turns: int = 50

    def run_debate(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        dangerous_mode: bool = False,
        max_turns: int = 50,
    ) -> DebateResult:
        """
        Execute the full 3-turn debate.

        Args:
            phase_name: Name of the phase (e.g., "research")
            prompt_generator: Prompt generator for this phase
            permission_mode: Permission mode for agent execution
            allowed_tools: List of allowed tools
            dangerous_mode: Whether to skip permission prompts

        Returns:
            DebateResult with all turn results and final output
        """
        # Store max_turns for use in internal methods
        self._max_turns = max_turns

        self.files.ensure_directories()

        # Determine file paths using roles (not agent names) to support same-agent debates
        phase_file_name = self._get_phase_file_name(phase_name)
        primary_t1_file = self.files.get_role_output_path(phase_file_name, "primary")
        secondary_t1_file = self.files.get_role_output_path(phase_file_name, "secondary")
        debate_file = self.files.get_debate_path(phase_file_name)
        final_file = self.files.get_final_output_path(phase_file_name)

        try:
            if self.config.is_feedback_only:
                return self._run_feedback_debate(
                    phase_name=phase_name,
                    prompt_generator=prompt_generator,
                    primary_t1_file=primary_t1_file,
                    debate_file=debate_file,
                    final_file=final_file,
                    permission_mode=permission_mode,
                    allowed_tools=allowed_tools,
                    dangerous_mode=dangerous_mode,
                )

            # Full debate: Turn 1 parallel independent generation
            t1_results = self._run_turn_1(
                phase_name=phase_name,
                prompt_generator=prompt_generator,
                primary_output_file=primary_t1_file,
                secondary_output_file=secondary_t1_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

            # Store Turn 1 session IDs using roles (not agent names) to avoid collisions
            self._store_session_id(phase_name, "primary", 1, t1_results.primary_result.session_id)
            if t1_results.secondary_result:
                self._store_session_id(phase_name, "secondary", 1, t1_results.secondary_result.session_id)

            # Turn 2: Interactive debate exchange
            t2_results = self._run_turn_2_exchange(
                phase_name=phase_name,
                prompt_generator=prompt_generator,
                t1_results=t1_results,
                debate_file=debate_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

            # Turn 3: Synthesis (primary agent only)
            synthesis = self._run_synthesis(
                phase_name=phase_name,
                prompt_generator=prompt_generator,
                t1_results=t1_results,
                debate_file=debate_file,
                final_output_file=final_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

            return DebateResult(
                success=synthesis.success,
                phase_name=phase_name,
                final_output_file=final_file,
                turn1=t1_results,
                turn2=t2_results,
                synthesis=synthesis,
            )

        except Exception as e:
            return DebateResult(
                success=False,
                phase_name=phase_name,
                final_output_file=final_file,
                error=str(e),
            )

    def _run_feedback_debate(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        primary_t1_file: Path,
        debate_file: Path,
        final_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> DebateResult:
        """Execute feedback-only debate (mode='feedback').

        Flow: primary generates → secondary reviews → primary synthesizes.
        """
        # Step 1: Primary-only Turn 1
        t1_results = self._run_turn_1_primary_only(
            phase_name=phase_name,
            prompt_generator=prompt_generator,
            primary_output_file=primary_t1_file,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            dangerous_mode=dangerous_mode,
        )

        self._store_session_id(phase_name, "primary", 1, t1_results.primary_result.session_id)

        # Step 2: Secondary feedback (single message)
        t2_results = self._run_feedback_turn_2(
            phase_name=phase_name,
            prompt_generator=prompt_generator,
            t1_results=t1_results,
            debate_file=debate_file,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            dangerous_mode=dangerous_mode,
        )

        # Step 3: Synthesis
        synthesis = self._run_synthesis(
            phase_name=phase_name,
            prompt_generator=prompt_generator,
            t1_results=t1_results,
            debate_file=debate_file,
            final_output_file=final_file,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            dangerous_mode=dangerous_mode,
        )

        return DebateResult(
            success=synthesis.success,
            phase_name=phase_name,
            final_output_file=final_file,
            turn1=t1_results,
            turn2=t2_results,
            synthesis=synthesis,
        )

    def _run_turn_1_primary_only(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        primary_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1 with only the primary agent (feedback-only mode)."""
        primary_prompt = prompt_generator.turn1_primary_prompt(primary_output_file)

        primary_result = self.primary.execute(
            prompt=primary_prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=self._max_turns,
            timeout=self.config.turn_timeout_seconds,
            dangerous_mode=dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        return Turn1Results(
            primary_result=primary_result,
            secondary_result=None,
            primary_output_file=primary_output_file,
            secondary_output_file=None,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )

    def _run_feedback_turn_2(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        t1_results: Turn1Results,
        debate_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn2Results:
        """Run Turn 2 as a single feedback message from secondary."""
        debate_log = DebateLog(
            debate_file,
            total_messages=1,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )
        debate_log.write_header(phase_name, self.context.task_description)
        debate_log.write_turn1_summary(t1_results)

        # Generate feedback prompt (secondary reviews primary's output)
        prompt = prompt_generator.feedback_prompt(
            reviewer=self.secondary_agent,
            primary_output=t1_results.primary_output_file,
        )

        # Secondary runs autonomous if it's a different agent type
        effective_dangerous_mode = (
            dangerous_mode
            if self.secondary_agent == self.primary_agent
            else True
        )

        result = self.secondary.execute(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=self._max_turns,
            timeout=self.config.message_timeout_seconds,
            dangerous_mode=effective_dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        message = DebateMessage(
            speaker=self.secondary_agent,
            message_number=1,
            content=result.output,
            result=result,
            role="secondary",
        )

        debate_log.append_message(
            speaker=self.secondary_agent,
            message_num=1,
            content=result.output,
            timestamp=datetime.now(),
            role="secondary",
        )
        debate_log.write_synthesis_summary()

        if result.session_id:
            self._store_session_id(phase_name, "secondary", 2, result.session_id, 1)

        return Turn2Results(
            messages=[message],
            debate_log_path=debate_file,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )

    def _run_turn_1(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        primary_output_file: Path,
        secondary_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1: Parallel independent generation."""
        primary_prompt = prompt_generator.turn1_primary_prompt(primary_output_file)
        secondary_prompt = prompt_generator.turn1_secondary_prompt(secondary_output_file)

        if self.config.parallel_turn_1:
            return self._run_turn_1_parallel(
                primary_prompt=primary_prompt,
                secondary_prompt=secondary_prompt,
                primary_output_file=primary_output_file,
                secondary_output_file=secondary_output_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )
        else:
            return self._run_turn_1_sequential(
                primary_prompt=primary_prompt,
                secondary_prompt=secondary_prompt,
                primary_output_file=primary_output_file,
                secondary_output_file=secondary_output_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

    def _run_turn_1_parallel(
        self,
        primary_prompt: str,
        secondary_prompt: str,
        primary_output_file: Path,
        secondary_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1 with parallel execution."""
        # Determine secondary's dangerous_mode based on agent configuration
        # Same-agent debates respect dangerous_mode; different agents force autonomous
        secondary_dangerous_mode = (
            dangerous_mode
            if self.secondary_agent == self.primary_agent
            else True
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            primary_future = executor.submit(
                self.primary.execute,
                prompt=primary_prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=self._max_turns,
                timeout=self.config.turn_timeout_seconds,
                dangerous_mode=dangerous_mode,
                working_dir=self.context.get_working_dir(),
            )

            secondary_future = executor.submit(
                self.secondary.execute,
                prompt=secondary_prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=self._max_turns,
                timeout=self.config.turn_timeout_seconds,
                dangerous_mode=secondary_dangerous_mode,
                working_dir=self.context.get_working_dir(),
            )

            primary_result = primary_future.result()
            secondary_result = secondary_future.result()

        return Turn1Results(
            primary_result=primary_result,
            secondary_result=secondary_result,
            primary_output_file=primary_output_file,
            secondary_output_file=secondary_output_file,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )

    def _run_turn_1_sequential(
        self,
        primary_prompt: str,
        secondary_prompt: str,
        primary_output_file: Path,
        secondary_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1 sequentially (primary first, then secondary)."""
        # Determine secondary's dangerous_mode based on agent configuration
        # Same-agent debates respect dangerous_mode; different agents force autonomous
        secondary_dangerous_mode = (
            dangerous_mode
            if self.secondary_agent == self.primary_agent
            else True
        )

        primary_result = self.primary.execute(
            prompt=primary_prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=self._max_turns,
            timeout=self.config.turn_timeout_seconds,
            dangerous_mode=dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        secondary_result = self.secondary.execute(
            prompt=secondary_prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=self._max_turns,
            timeout=self.config.turn_timeout_seconds,
            dangerous_mode=secondary_dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        return Turn1Results(
            primary_result=primary_result,
            secondary_result=secondary_result,
            primary_output_file=primary_output_file,
            secondary_output_file=secondary_output_file,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )

    def _run_turn_2_exchange(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        t1_results: Turn1Results,
        debate_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn2Results:
        """Run the interactive debate exchange (Turn 2)."""
        max_messages = self.config.max_exchange_messages

        # Initialize debate log with dynamic agent names
        debate_log = DebateLog(
            debate_file,
            total_messages=max_messages,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )
        debate_log.write_header(phase_name, self.context.task_description)
        debate_log.write_turn1_summary(t1_results)

        messages_exchanged: list[DebateMessage] = []
        current_speaker = self.primary_agent  # Primary agent opens the debate
        current_role = "primary"  # Track role for session storage

        for msg_num in range(1, max_messages + 1):
            is_final = msg_num == max_messages
            is_primary = current_role == "primary"

            # Build prompt with debate context so far
            # Use role-based file lookup to support same-agent debates
            other_role = "secondary" if current_role == "primary" else "primary"
            prompt = prompt_generator.debate_message_prompt(
                speaker=current_speaker,
                message_number=msg_num,
                total_messages=max_messages,
                transcript_so_far=debate_log.get_transcript(),
                own_t1_output=t1_results.get_output_file_by_role(current_role),
                other_t1_output=t1_results.get_output_file_by_role(other_role),
                is_final_message=is_final,
                role=current_role,
            )

            # Select executor based on role
            executor = self.primary if is_primary else self.secondary

            # Resume from previous message for primary agent to maintain context
            resume_session = None
            if is_primary and msg_num > 1:
                # Resume from primary agent's previous message (msg_num - 2 gives the last primary message)
                prev_primary_msg_num = msg_num - 2
                if prev_primary_msg_num >= 1:
                    resume_session = self.context.get_debate_session_id(
                        phase_name, "primary", 2, prev_primary_msg_num
                    )

            # Execute the message
            # Secondary agent runs in autonomous mode only if it's a different agent type
            # (e.g., Codex doesn't handle approval prompts well). For same-agent debates
            # (e.g., Claude vs Claude), respect the dangerous_mode setting to preserve
            # approval safety.
            if is_primary:
                effective_dangerous_mode = dangerous_mode
            elif self.secondary_agent == self.primary_agent:
                # Same-agent debate: respect dangerous_mode for both
                effective_dangerous_mode = dangerous_mode
            else:
                # Different agents: secondary (e.g., Codex) runs autonomous
                effective_dangerous_mode = True
            result = executor.execute(
                prompt=prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=self._max_turns,
                timeout=self.config.message_timeout_seconds,
                resume_session=resume_session,
                dangerous_mode=effective_dangerous_mode,
                working_dir=self.context.get_working_dir(),
            )

            # Create message record with role for same-agent debate support
            message = DebateMessage(
                speaker=current_speaker,
                message_number=msg_num,
                content=result.output,
                result=result,
                role=current_role,
            )
            messages_exchanged.append(message)

            # Append to debate log with role for same-agent debate support
            debate_log.append_message(
                speaker=current_speaker,
                message_num=msg_num,
                content=result.output,
                timestamp=datetime.now(),
                role=current_role,
            )

            # Store session using role (not agent name) to avoid collisions in same-agent debates
            if result.session_id:
                self._store_session_id(phase_name, current_role, 2, result.session_id, msg_num)

            # Alternate speakers and roles (Primary → Secondary → Primary → ...)
            current_speaker = self._other_agent(current_speaker)
            current_role = "secondary" if current_role == "primary" else "primary"

        # Write synthesis summary to debate log
        debate_log.write_synthesis_summary()

        return Turn2Results(
            messages=messages_exchanged,
            debate_log_path=debate_file,
            primary_agent=self.primary_agent,
            secondary_agent=self.secondary_agent,
        )

    def _run_synthesis(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        t1_results: Turn1Results,
        debate_file: Path,
        final_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> SynthesisResult:
        """Run Turn 3: Synthesis by primary agent."""
        # Read the debate transcript
        debate_transcript = debate_file.read_text() if debate_file.exists() else ""

        # Generate synthesis prompt
        prompt = prompt_generator.synthesis_prompt(
            t1_results=t1_results,
            debate_transcript=debate_transcript,
            final_output_file=final_output_file,
        )

        # Resume from appropriate session to carry context
        if self.config.is_feedback_only:
            # Feedback mode: resume from primary's Turn 1 (no primary T2 messages)
            resume_session = self.context.get_debate_session_id(
                phase_name, "primary", 1
            )
        else:
            # Full debate: resume from primary's final Turn 2 message
            # Use "primary" role (not agent name) for session lookup to support same-agent debates
            resume_session = self.context.get_debate_session_id(
                phase_name, "primary", 2, self.config.max_exchange_messages
            )
            # If no Turn 2 session (odd number of messages), try the previous one
            if not resume_session:
                for msg_num in range(self.config.max_exchange_messages, 0, -1):
                    resume_session = self.context.get_debate_session_id(
                        phase_name, "primary", 2, msg_num
                    )
                    if resume_session:
                        break

        # Execute synthesis
        result = self.primary.execute(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=self._max_turns,
            timeout=self.config.turn_timeout_seconds,
            resume_session=resume_session,
            dangerous_mode=dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        # Store synthesis session
        if result.session_id:
            self.context.set_session_id(f"{phase_name}_synthesis", result.session_id)

        return SynthesisResult(
            result=result,
            output_file=final_output_file,
        )

    def _other_agent(self, agent: str) -> str:
        """Get the other agent name (toggle between primary and secondary)."""
        if agent == self.primary_agent:
            return self.secondary_agent
        return self.primary_agent

    def _get_phase_file_name(self, phase_name: str) -> str:
        """
        Map phase name to file prefix.

        This handles the mapping between internal phase names
        and the file naming convention.
        """
        mapping = {
            "research": "research",
            "planning": "plan",
            "plan_review": "plan-review",
            "code_review": "review",
        }
        return mapping.get(phase_name, phase_name)

    def _store_session_id(
        self,
        phase: str,
        agent: str,
        turn: int,
        session_id: str | None,
        message_num: int | None = None,
    ) -> None:
        """Store a session ID for later resume."""
        if not session_id:
            return

        if message_num is not None:
            key = f"{phase}_{agent}_t{turn}_msg{message_num}"
        else:
            key = f"{phase}_{agent}_t{turn}"

        self.context.set_session_id(key, session_id)
