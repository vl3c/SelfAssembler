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

    Manages the three-turn debate process:
    - Turn 1: Parallel independent generation
    - Turn 2: Interactive message exchange
    - Turn 3: Synthesis by primary agent
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

    def run_debate(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        dangerous_mode: bool = False,
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
        self.files.ensure_directories()

        # Determine file paths
        phase_file_name = self._get_phase_file_name(phase_name)
        claude_t1_file = self.files.get_claude_t1_path(phase_file_name)
        codex_t1_file = self.files.get_codex_t1_path(phase_file_name)
        debate_file = self.files.get_debate_path(phase_file_name)
        final_file = self.files.get_final_output_path(phase_file_name)

        try:
            # Turn 1: Parallel independent generation
            t1_results = self._run_turn_1(
                phase_name=phase_name,
                prompt_generator=prompt_generator,
                claude_output_file=claude_t1_file,
                codex_output_file=codex_t1_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

            # Store Turn 1 session IDs
            self._store_session_id(phase_name, "claude", 1, t1_results.claude_result.session_id)
            self._store_session_id(phase_name, "codex", 1, t1_results.codex_result.session_id)

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

    def _run_turn_1(
        self,
        phase_name: str,
        prompt_generator: BaseDebatePromptGenerator,
        claude_output_file: Path,
        codex_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1: Parallel independent generation."""
        claude_prompt = prompt_generator.turn1_primary_prompt(claude_output_file)
        codex_prompt = prompt_generator.turn1_secondary_prompt(codex_output_file)

        if self.config.parallel_turn_1:
            return self._run_turn_1_parallel(
                claude_prompt=claude_prompt,
                codex_prompt=codex_prompt,
                claude_output_file=claude_output_file,
                codex_output_file=codex_output_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )
        else:
            return self._run_turn_1_sequential(
                claude_prompt=claude_prompt,
                codex_prompt=codex_prompt,
                claude_output_file=claude_output_file,
                codex_output_file=codex_output_file,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                dangerous_mode=dangerous_mode,
            )

    def _run_turn_1_parallel(
        self,
        claude_prompt: str,
        codex_prompt: str,
        claude_output_file: Path,
        codex_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1 with parallel execution."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            claude_future = executor.submit(
                self.primary.execute,
                prompt=claude_prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=50,
                timeout=self.config.turn_timeout_seconds,
                dangerous_mode=dangerous_mode,
                working_dir=self.context.get_working_dir(),
            )

            codex_future = executor.submit(
                self.secondary.execute,
                prompt=codex_prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=50,
                timeout=self.config.turn_timeout_seconds,
                dangerous_mode=True,  # Codex always runs in autonomous mode
                working_dir=self.context.get_working_dir(),
            )

            claude_result = claude_future.result()
            codex_result = codex_future.result()

        return Turn1Results(
            claude_result=claude_result,
            codex_result=codex_result,
            claude_output_file=claude_output_file,
            codex_output_file=codex_output_file,
        )

    def _run_turn_1_sequential(
        self,
        claude_prompt: str,
        codex_prompt: str,
        claude_output_file: Path,
        codex_output_file: Path,
        permission_mode: str | None,
        allowed_tools: list[str] | None,
        dangerous_mode: bool,
    ) -> Turn1Results:
        """Run Turn 1 sequentially (Claude first, then Codex)."""
        claude_result = self.primary.execute(
            prompt=claude_prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=50,
            timeout=self.config.turn_timeout_seconds,
            dangerous_mode=dangerous_mode,
            working_dir=self.context.get_working_dir(),
        )

        codex_result = self.secondary.execute(
            prompt=codex_prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=50,
            timeout=self.config.turn_timeout_seconds,
            dangerous_mode=True,  # Codex always runs in autonomous mode
            working_dir=self.context.get_working_dir(),
        )

        return Turn1Results(
            claude_result=claude_result,
            codex_result=codex_result,
            claude_output_file=claude_output_file,
            codex_output_file=codex_output_file,
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

        # Initialize debate log
        debate_log = DebateLog(debate_file, total_messages=max_messages)
        debate_log.write_header(phase_name, self.context.task_description)
        debate_log.write_turn1_summary(t1_results)

        messages_exchanged: list[DebateMessage] = []
        current_speaker = "claude"  # Claude opens the debate

        for msg_num in range(1, max_messages + 1):
            is_final = msg_num == max_messages

            # Build prompt with debate context so far
            prompt = prompt_generator.debate_message_prompt(
                speaker=current_speaker,
                message_number=msg_num,
                total_messages=max_messages,
                transcript_so_far=debate_log.get_transcript(),
                own_t1_output=t1_results.get_output_file(current_speaker),
                other_t1_output=t1_results.get_output_file(self._other_agent(current_speaker)),
                is_final_message=is_final,
            )

            # Select executor and determine if we should resume
            executor = self.primary if current_speaker == "claude" else self.secondary

            # Resume from previous message for Claude to maintain context
            resume_session = None
            if current_speaker == "claude" and msg_num > 1:
                # Resume from Claude's previous message (msg_num - 2 gives the last Claude message)
                prev_claude_msg_num = msg_num - 2
                if prev_claude_msg_num >= 1:
                    resume_session = self.context.get_debate_session_id(
                        phase_name, "claude", 2, prev_claude_msg_num
                    )

            # Execute the message
            # Codex always runs in autonomous mode (dangerous_mode=True)
            effective_dangerous_mode = True if current_speaker == "codex" else dangerous_mode
            result = executor.execute(
                prompt=prompt,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                max_turns=20,
                timeout=self.config.message_timeout_seconds,
                resume_session=resume_session,
                dangerous_mode=effective_dangerous_mode,
                working_dir=self.context.get_working_dir(),
            )

            # Create message record
            message = DebateMessage(
                speaker=current_speaker,
                message_number=msg_num,
                content=result.output,
                result=result,
            )
            messages_exchanged.append(message)

            # Append to debate log
            debate_log.append_message(
                speaker=current_speaker,
                message_num=msg_num,
                content=result.output,
                timestamp=datetime.now(),
            )

            # Store session for potential resume
            if result.session_id:
                self._store_session_id(phase_name, current_speaker, 2, result.session_id, msg_num)

            # Alternate speakers (Claude → Codex → Claude → ...)
            current_speaker = self._other_agent(current_speaker)

        # Write synthesis summary to debate log
        debate_log.write_synthesis_summary()

        return Turn2Results(
            messages=messages_exchanged,
            debate_log_path=debate_file,
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

        # Resume from Claude's final Turn 2 message to carry debate context
        resume_session = self.context.get_debate_session_id(
            phase_name, "claude", 2, self.config.max_exchange_messages
        )
        # If no Turn 2 session (odd number of messages), try the previous one
        if not resume_session:
            for msg_num in range(self.config.max_exchange_messages, 0, -1):
                resume_session = self.context.get_debate_session_id(
                    phase_name, "claude", 2, msg_num
                )
                if resume_session:
                    break

        # Execute synthesis
        result = self.primary.execute(
            prompt=prompt,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            max_turns=30,
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
        """Get the other agent name."""
        return "codex" if agent == "claude" else "claude"

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
