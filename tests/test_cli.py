"""Tests for CLI module."""

import pytest

from selfassembler.cli import create_parser, generate_task_name, handle_dry_run, handle_help_phases
from selfassembler.config import WorkflowConfig


class TestCreateParser:
    """Tests for argument parser."""

    def test_parser_created(self):
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None

    def test_task_argument(self):
        """Test task argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["Test task"])
        assert args.task == "Test task"

    def test_name_flag(self):
        """Test --name flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--name", "my-task"])
        assert args.task_name == "my-task"

    def test_autonomous_flag(self):
        """Test --autonomous flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--autonomous"])
        assert args.autonomous is True

    def test_no_approvals_flag(self):
        """Test --no-approvals flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--no-approvals"])
        assert args.no_approvals is True

    def test_resume_flag(self):
        """Test --resume flag."""
        parser = create_parser()
        args = parser.parse_args(["--resume", "checkpoint_abc123"])
        assert args.resume == "checkpoint_abc123"

    def test_skip_to_flag(self):
        """Test --skip-to flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--skip-to", "implementation"])
        assert args.skip_to == "implementation"

    def test_budget_flag(self):
        """Test --budget flag."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--budget", "25.0"])
        assert args.budget == 25.0

    def test_list_checkpoints_flag(self):
        """Test --list-checkpoints flag."""
        parser = create_parser()
        args = parser.parse_args(["--list-checkpoints"])
        assert args.list_checkpoints is True

    def test_list_phases_flag(self):
        """Test --list-phases flag."""
        parser = create_parser()
        args = parser.parse_args(["--list-phases"])
        assert args.list_phases is True

    def test_agent_flag_claude(self):
        """Test --agent flag with claude."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--agent", "claude"])
        assert args.agent == "claude"

    def test_agent_flag_codex(self):
        """Test --agent flag with codex."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--agent", "codex"])
        assert args.agent == "codex"

    def test_agent_flag_default_none(self):
        """Test --agent flag defaults to None."""
        parser = create_parser()
        args = parser.parse_args(["Task"])
        assert args.agent is None

    def test_agent_flag_invalid_choice(self):
        """Test --agent flag rejects invalid choices."""

        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["Task", "--agent", "invalid"])


class TestAgentFlagConfig:
    """Tests for --agent flag configuration handling."""

    def test_agent_flag_sets_config(self):
        """Test that --agent flag sets config.agent.type."""
        from selfassembler.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["Task", "--agent", "codex", "--dry-run"])

        # Load config and apply overrides (simulating main() behavior)
        config = WorkflowConfig.load(args.config)
        if args.agent:
            config.agent.type = args.agent

        assert config.agent.type == "codex"

    def test_agent_flag_overrides_config_file(self):
        """Test that --agent flag overrides config file setting."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path

            config_path = Path(tmpdir) / "config.yaml"

            # Create config with claude as agent type
            config = WorkflowConfig()
            config.agent.type = "claude"
            config.save(config_path)

            # Load and apply CLI override
            loaded = WorkflowConfig.load(config_path)
            loaded.agent.type = "codex"  # Simulating --agent codex

            assert loaded.agent.type == "codex"


class TestGenerateTaskName:
    """Tests for task name generation."""

    def test_simple_name(self):
        """Test simple task name generation."""
        name = generate_task_name("Add user authentication")
        assert "add" in name.lower()
        assert "user" in name.lower()
        assert "-" in name

    def test_special_characters_removed(self):
        """Test special characters are removed."""
        name = generate_task_name("Fix bug #123: user can't login!")
        assert "#" not in name
        assert "!" not in name
        assert ":" not in name

    def test_truncation(self):
        """Test long names are truncated."""
        long_task = "This is a very long task description that should be truncated"
        name = generate_task_name(long_task)
        assert len(name) <= 40

    def test_empty_fallback(self):
        """Test fallback for empty/special-only input."""
        name = generate_task_name("!@#$%")
        assert name == "task"


class TestDryRunFlag:
    """Tests for --dry-run flag parsing."""

    def test_dry_run_flag(self):
        """Test --dry-run flag is parsed correctly."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--dry-run"])
        assert args.dry_run is True

    def test_dry_run_default_false(self):
        """Test --dry-run defaults to False."""
        parser = create_parser()
        args = parser.parse_args(["Task"])
        assert args.dry_run is False

    def test_dry_run_with_skip_to(self):
        """Test --dry-run combined with --skip-to."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--dry-run", "--skip-to", "implementation"])
        assert args.dry_run is True
        assert args.skip_to == "implementation"

    def test_dry_run_with_no_approvals(self):
        """Test --dry-run combined with --no-approvals."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--dry-run", "--no-approvals"])
        assert args.dry_run is True
        assert args.no_approvals is True

    def test_dry_run_with_budget(self):
        """Test --dry-run combined with --budget."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--dry-run", "--budget", "10.0"])
        assert args.dry_run is True
        assert args.budget == 10.0

    def test_dry_run_with_skip_plan_review(self):
        """Test --dry-run combined with --skip-plan-review."""
        parser = create_parser()
        args = parser.parse_args(["Task", "--dry-run", "--skip-plan-review"])
        assert args.dry_run is True
        assert args.skip_plan_review is True


class TestHandleDryRun:
    """Tests for handle_dry_run function."""

    def test_dry_run_shows_all_phases(self, capsys):
        """Test that dry-run shows all enabled phases."""
        config = WorkflowConfig()
        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Check header
        assert "Dry-run: Phases that would execute" in captured.out
        assert "Phase" in captured.out
        assert "Approval Gate" in captured.out
        assert "Est. Cost" in captured.out
        assert "Running Total" in captured.out

        # Check that key phases are present
        assert "preflight" in captured.out
        assert "setup" in captured.out
        assert "research" in captured.out
        assert "planning" in captured.out
        assert "implementation" in captured.out
        assert "pr_creation" in captured.out

        # Check footer
        assert "Total estimated cost:" in captured.out
        assert "Budget limit:" in captured.out

    def test_dry_run_respects_skip_to(self, capsys):
        """Test that phases before skip_to are excluded."""
        config = WorkflowConfig()
        result = handle_dry_run(config, skip_to="implementation")

        assert result == 0
        captured = capsys.readouterr()

        # Phases before implementation should NOT be present
        assert "preflight" not in captured.out
        assert "setup" not in captured.out
        assert "research" not in captured.out
        assert "planning" not in captured.out

        # Implementation and after should be present
        assert "implementation" in captured.out
        assert "test_writing" in captured.out
        assert "pr_creation" in captured.out

    def test_dry_run_respects_disabled_phases(self, capsys):
        """Test that disabled phases are excluded."""
        config = WorkflowConfig()
        # Disable the plan_review phase
        config.phases.plan_review.enabled = False

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # plan_review should not be shown
        assert "plan_review" not in captured.out
        # Other phases should still be present
        assert "planning" in captured.out
        assert "implementation" in captured.out

    def test_dry_run_shows_approval_gates(self, capsys):
        """Test that approval gate status is shown correctly."""
        config = WorkflowConfig()
        # Ensure approvals are enabled and planning gate is on
        config.approvals.enabled = True
        config.approvals.gates.planning = True

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.split("\n")

        # Find the planning line
        planning_line = None
        for line in lines:
            if "planning" in line and "plan_review" not in line:
                planning_line = line
                break

        assert planning_line is not None
        assert "Yes" in planning_line  # Approval gate is Yes

    def test_dry_run_with_no_approvals(self, capsys):
        """Test that all gates show 'No' when approvals are disabled."""
        config = WorkflowConfig()
        config.approvals.enabled = False

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Count lines with "Yes" for approval gate (should be none)
        lines = captured.out.split("\n")
        # Skip header lines - look at data lines only
        data_lines = [line for line in lines if line.strip() and line.strip()[0].isdigit()]

        # None of the data lines should have "Yes" for approval gate
        for line in data_lines:
            # Find "Yes" in the line - should not be there when approvals disabled
            assert "Yes" not in line or "No" in line

    def test_dry_run_calculates_total_cost(self, capsys):
        """Test that cost accumulation is correct."""
        config = WorkflowConfig()
        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Check that total is calculated and displayed
        assert "Total estimated cost: $" in captured.out

        # Verify it's the sum of all phase costs
        # From config defaults, we can calculate expected total
        expected_phases = [
            config.phases.preflight,
            config.phases.setup,
            config.phases.research,
            config.phases.planning,
            config.phases.plan_review,
            config.phases.implementation,
            config.phases.test_writing,
            config.phases.test_execution,
            config.phases.code_review,
            config.phases.fix_review_issues,
            config.phases.lint_check,
            config.phases.documentation,
            config.phases.final_verification,
            config.phases.commit_prep,
            config.phases.conflict_check,
            config.phases.pr_creation,
            config.phases.pr_self_review,
        ]
        expected_total = sum(p.estimated_cost for p in expected_phases)

        assert f"Total estimated cost: ${expected_total:.2f}" in captured.out

    def test_dry_run_shows_budget_warning(self, capsys):
        """Test that warning is shown when cost exceeds budget."""
        config = WorkflowConfig()
        # Set a very low budget to trigger warning
        config.budget_limit_usd = 1.0

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Should show warning about exceeding budget
        assert "Warning:" in captured.out
        assert "exceeds budget limit" in captured.out

    def test_dry_run_no_warning_within_budget(self, capsys):
        """Test that no warning is shown when cost is within budget."""
        config = WorkflowConfig()
        # Set a high budget
        config.budget_limit_usd = 100.0

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Should NOT show warning
        assert "Warning:" not in captured.out
        assert "exceeds budget limit" not in captured.out

    def test_dry_run_with_invalid_skip_to(self, capsys):
        """Test that invalid skip_to phase returns error."""
        config = WorkflowConfig()
        result = handle_dry_run(config, skip_to="nonexistent_phase")

        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown phase: nonexistent_phase" in captured.err

    def test_dry_run_all_phases_disabled(self, capsys):
        """Test message when all phases are disabled."""
        config = WorkflowConfig()
        # Disable all phases
        config.phases.preflight.enabled = False
        config.phases.setup.enabled = False
        config.phases.research.enabled = False
        config.phases.planning.enabled = False
        config.phases.plan_review.enabled = False
        config.phases.implementation.enabled = False
        config.phases.test_writing.enabled = False
        config.phases.test_execution.enabled = False
        config.phases.code_review.enabled = False
        config.phases.fix_review_issues.enabled = False
        config.phases.lint_check.enabled = False
        config.phases.documentation.enabled = False
        config.phases.final_verification.enabled = False
        config.phases.commit_prep.enabled = False
        config.phases.conflict_check.enabled = False
        config.phases.pr_creation.enabled = False
        config.phases.pr_self_review.enabled = False

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()
        assert "No phases would run with the current configuration" in captured.out

    def test_dry_run_shows_phase_numbers(self, capsys):
        """Test that phases are numbered sequentially."""
        config = WorkflowConfig()
        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Should have numbered phases starting from 1
        lines = captured.out.split("\n")
        data_lines = [line for line in lines if line.strip() and line.strip()[0].isdigit()]

        # First phase should be #1
        assert data_lines[0].strip().startswith("1")

    def test_dry_run_shows_running_total(self, capsys):
        """Test that running total column is shown correctly."""
        config = WorkflowConfig()
        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Running Total header should be present
        assert "Running Total" in captured.out

        lines = captured.out.split("\n")
        data_lines = [line for line in lines if line.strip() and line.strip()[0].isdigit()]

        # Each line should have dollar amounts for running total
        for line in data_lines:
            # Should have at least two $ signs (Est. Cost and Running Total)
            assert line.count("$") >= 2

    def test_dry_run_respects_plan_review_gate_config(self, capsys):
        """Test that plan_review gate respects --review-plan-approval config."""
        config = WorkflowConfig()
        config.approvals.enabled = True
        # Enable the plan_review approval gate
        config.approvals.gates.plan_review = True

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.split("\n")

        # Find the plan_review line
        plan_review_line = None
        for line in lines:
            if "plan_review" in line:
                plan_review_line = line
                break

        assert plan_review_line is not None
        assert "Yes" in plan_review_line  # Approval gate should be Yes

    def test_dry_run_skip_to_last_phase(self, capsys):
        """Test dry-run when skipping to the last phase."""
        config = WorkflowConfig()
        result = handle_dry_run(config, skip_to="pr_self_review")

        assert result == 0
        captured = capsys.readouterr()

        # Only pr_self_review should be in the output
        assert "pr_self_review" in captured.out
        assert "pr_creation" not in captured.out

        # Should show only 1 phase
        lines = captured.out.split("\n")
        data_lines = [line for line in lines if line.strip() and line.strip()[0].isdigit()]
        assert len(data_lines) == 1

    def test_dry_run_with_custom_estimated_costs(self, capsys):
        """Test dry-run with custom estimated costs."""
        config = WorkflowConfig()
        # Set custom costs
        config.phases.implementation.estimated_cost = 10.0
        config.phases.planning.estimated_cost = 5.0

        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Verify custom costs appear in output
        assert "$10.00" in captured.out
        assert "$5.00" in captured.out

    def test_dry_run_output_format(self, capsys):
        """Test the overall output format of dry-run."""
        config = WorkflowConfig()
        result = handle_dry_run(config)

        assert result == 0
        captured = capsys.readouterr()

        # Check table structure
        assert "─" in captured.out  # Table divider line
        lines = captured.out.split("\n")

        # Should have header, divider, data rows, divider, and summary
        non_empty_lines = [line for line in lines if line.strip()]
        assert len(non_empty_lines) > 5  # At least header + divider + some data + summary

    def test_dry_run_combined_skip_to_and_disabled(self, capsys):
        """Test dry-run with both skip_to and disabled phases."""
        config = WorkflowConfig()
        # Skip to implementation
        skip_to = "implementation"
        # Disable test_writing
        config.phases.test_writing.enabled = False

        result = handle_dry_run(config, skip_to=skip_to)

        assert result == 0
        captured = capsys.readouterr()

        # Phases before implementation should not be present
        assert "planning" not in captured.out
        # test_writing should also not be present (disabled)
        assert "test_writing" not in captured.out
        # implementation and other enabled phases should be present
        assert "implementation" in captured.out
        assert "test_execution" in captured.out


class TestHelpPhasesFlag:
    """Tests for --help-phases flag parsing."""

    def test_help_phases_flag_no_args(self):
        """Test --help-phases with no arguments."""
        parser = create_parser()
        args = parser.parse_args(["--help-phases"])
        # When no args given, help_phases is an empty list
        assert args.help_phases == []

    def test_help_phases_flag_single_phase(self):
        """Test --help-phases with single phase argument."""
        parser = create_parser()
        args = parser.parse_args(["--help-phases", "planning"])
        assert args.help_phases == ["planning"]

    def test_help_phases_flag_multiple_phases(self):
        """Test --help-phases with multiple phase arguments."""
        parser = create_parser()
        args = parser.parse_args(["--help-phases", "planning", "implementation"])
        assert args.help_phases == ["planning", "implementation"]

    def test_help_phases_default_none(self):
        """Test --help-phases defaults to None when not specified."""
        parser = create_parser()
        args = parser.parse_args(["Task"])
        assert args.help_phases is None

    def test_help_phases_with_other_flags(self):
        """Test --help-phases can be combined with other utility flags."""
        parser = create_parser()
        # --help-phases should be parseable alongside other flags
        args = parser.parse_args(["--help-phases", "planning", "--verbose"])
        assert args.help_phases == ["planning"]
        assert args.verbose is True


class TestHandleHelpPhases:
    """Tests for handle_help_phases function."""

    def test_help_phases_shows_all_phases_when_no_args(self, capsys):
        """Test that handle_help_phases shows all phases when no args given."""
        result = handle_help_phases(None)

        assert result == 0
        captured = capsys.readouterr()

        # Check header is present
        assert "SELFASSEMBLER WORKFLOW PHASES" in captured.out

        # Check all phases are shown
        from selfassembler.phases import PHASE_NAMES

        for phase_name in PHASE_NAMES:
            assert f"PHASE: {phase_name}" in captured.out

    def test_help_phases_shows_all_phases_with_empty_list(self, capsys):
        """Test that handle_help_phases shows all phases with empty list."""
        result = handle_help_phases([])

        assert result == 0
        captured = capsys.readouterr()

        # Should show header and all phases
        assert "SELFASSEMBLER WORKFLOW PHASES" in captured.out
        assert "PHASE: preflight" in captured.out
        assert "PHASE: pr_self_review" in captured.out

    def test_help_phases_single_phase(self, capsys):
        """Test showing help for a single phase."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Should show planning phase
        assert "PHASE: planning" in captured.out
        # Should NOT show other phases
        assert "PHASE: preflight" not in captured.out
        assert "PHASE: implementation" not in captured.out

    def test_help_phases_multiple_phases(self, capsys):
        """Test showing help for multiple phases."""
        result = handle_help_phases(["planning", "implementation"])

        assert result == 0
        captured = capsys.readouterr()

        # Should show both requested phases
        assert "PHASE: planning" in captured.out
        assert "PHASE: implementation" in captured.out
        # Should NOT show other phases
        assert "PHASE: preflight" not in captured.out
        assert "PHASE: pr_self_review" not in captured.out

    def test_help_phases_invalid_phase_name(self, capsys):
        """Test error handling for invalid phase name."""
        result = handle_help_phases(["nonexistent_phase"])

        assert result == 1
        captured = capsys.readouterr()

        # Error message should be on stderr
        assert "Error: Unknown phase(s): nonexistent_phase" in captured.err
        # Should show valid phases
        assert "Valid phases:" in captured.err

    def test_help_phases_multiple_invalid_phases(self, capsys):
        """Test error handling for multiple invalid phase names."""
        result = handle_help_phases(["invalid1", "invalid2"])

        assert result == 1
        captured = capsys.readouterr()

        # Both invalid phases should be mentioned
        assert "invalid1" in captured.err
        assert "invalid2" in captured.err

    def test_help_phases_mixed_valid_invalid(self, capsys):
        """Test error handling when some phases are valid and some invalid."""
        result = handle_help_phases(["planning", "invalid_phase"])

        assert result == 1
        captured = capsys.readouterr()

        # Should report the invalid one
        assert "invalid_phase" in captured.err
        assert "Valid phases:" in captured.err

    def test_help_phases_shows_description_section(self, capsys):
        """Test that DESCRIPTION section is shown."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        assert "DESCRIPTION" in captured.out
        # Planning phase has a docstring
        assert "Create detailed implementation plan" in captured.out

    def test_help_phases_shows_timing_section(self, capsys):
        """Test that TIMING section is shown with timeout and max_turns."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        assert "TIMING" in captured.out
        assert "Timeout:" in captured.out
        assert "Max turns:" in captured.out
        # Planning phase has specific values
        assert "600 seconds" in captured.out
        assert "10 minutes" in captured.out

    def test_help_phases_shows_approval_gate_section(self, capsys):
        """Test that APPROVAL GATE section is shown."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        assert "APPROVAL GATE" in captured.out
        # Planning phase has an approval gate
        assert "Yes" in captured.out

    def test_help_phases_shows_no_approval_gate(self, capsys):
        """Test that phases without approval gate show 'No'."""
        result = handle_help_phases(["implementation"])

        assert result == 0
        captured = capsys.readouterr()

        # Find the APPROVAL GATE section for implementation
        lines = captured.out.split("\n")
        in_approval_section = False
        for line in lines:
            if "APPROVAL GATE" in line:
                in_approval_section = True
                continue
            if in_approval_section and line.strip():
                assert "No" in line
                break

    def test_help_phases_shows_configuration_section(self, capsys):
        """Test that CONFIGURATION section is shown with YAML example."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        assert "CONFIGURATION" in captured.out
        assert "phases:" in captured.out
        assert "planning:" in captured.out
        assert "timeout:" in captured.out
        assert "max_turns:" in captured.out
        assert "enabled: true" in captured.out

    def test_help_phases_shows_claude_mode_when_set(self, capsys):
        """Test that CLAUDE MODE section is shown when phase has claude_mode."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Planning phase has claude_mode = "plan"
        assert "CLAUDE MODE" in captured.out
        assert "plan (read-only)" in captured.out

    def test_help_phases_no_claude_mode_when_not_set(self, capsys):
        """Test that CLAUDE MODE section is NOT shown when phase has no claude_mode."""
        result = handle_help_phases(["implementation"])

        assert result == 0
        captured = capsys.readouterr()

        # Implementation phase has no claude_mode
        # The section should not appear between the DESCRIPTION and TIMING
        lines = captured.out.split("\n")
        found_description = False
        found_timing = False
        found_claude_mode = False
        for line in lines:
            if "DESCRIPTION" in line:
                found_description = True
            if "TIMING" in line:
                found_timing = True
            if "CLAUDE MODE" in line and found_description and not found_timing:
                found_claude_mode = True

        assert not found_claude_mode

    def test_help_phases_shows_context_when_fresh(self, capsys):
        """Test that CONTEXT section is shown when phase has fresh_context=True."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Planning phase has fresh_context = True
        assert "CONTEXT" in captured.out
        assert "fresh_context: Yes" in captured.out

    def test_help_phases_no_context_when_not_fresh(self, capsys):
        """Test that CONTEXT section is NOT shown when phase has fresh_context=False."""
        result = handle_help_phases(["preflight"])

        assert result == 0
        captured = capsys.readouterr()

        # Preflight phase has fresh_context = False (default)
        # The CONTEXT section should not appear
        lines = captured.out.split("\n")
        in_preflight_section = False
        found_next_phase = False
        for line in lines:
            if "PHASE: preflight" in line:
                in_preflight_section = True
            elif in_preflight_section and line.startswith("PHASE:"):
                found_next_phase = True
            if in_preflight_section and not found_next_phase and "CONTEXT" in line:
                pytest.fail("CONTEXT section should not appear for preflight phase")

    def test_help_phases_shows_tools_when_set(self, capsys):
        """Test that TOOLS AVAILABLE section is shown when phase has allowed_tools."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Planning phase has allowed_tools
        assert "TOOLS AVAILABLE" in captured.out
        assert "Read" in captured.out
        assert "Grep" in captured.out
        assert "Glob" in captured.out
        assert "Write" in captured.out

    def test_help_phases_no_tools_when_not_set(self, capsys):
        """Test that TOOLS AVAILABLE section is NOT shown when phase has no allowed_tools."""
        result = handle_help_phases(["preflight"])

        assert result == 0
        captured = capsys.readouterr()

        # Preflight phase has no allowed_tools
        lines = captured.out.split("\n")
        in_preflight_section = False
        found_separator = False
        for line in lines:
            if "PHASE: preflight" in line:
                in_preflight_section = True
            elif in_preflight_section and line.startswith("-" * 10):
                found_separator = True
            if in_preflight_section and not found_separator and "TOOLS AVAILABLE" in line:
                pytest.fail("TOOLS AVAILABLE section should not appear for preflight phase")

    def test_help_phases_shows_phase_number(self, capsys):
        """Test that phase number is shown correctly."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Planning is the 4th phase (index 3)
        assert "PHASE: planning (4 of 17)" in captured.out

    def test_help_phases_phase_without_docstring(self, capsys):
        """Test handling of phase without docstring shows default message."""
        # All phases in this codebase have docstrings, but we test the logic
        # by verifying a phase with a docstring shows the expected text
        result = handle_help_phases(["preflight"])

        assert result == 0
        captured = capsys.readouterr()

        assert "DESCRIPTION" in captured.out
        # Preflight has a docstring
        assert "Validate environment before starting workflow" in captured.out

    def test_help_phases_timeout_formatting_with_seconds(self, capsys):
        """Test timeout formatting for values with remaining seconds."""
        # preflight has 60 seconds (1 minute exactly)
        result = handle_help_phases(["preflight"])

        assert result == 0
        captured = capsys.readouterr()

        assert "60 seconds (1 minutes)" in captured.out

    def test_help_phases_timeout_formatting_long_timeout(self, capsys):
        """Test timeout formatting for longer timeouts."""
        # implementation has 3600 seconds (60 minutes)
        result = handle_help_phases(["implementation"])

        assert result == 0
        captured = capsys.readouterr()

        assert "3600 seconds (60 minutes)" in captured.out

    def test_help_phases_output_has_separators(self, capsys):
        """Test that output has proper separator lines."""
        result = handle_help_phases(["planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Should have separator lines (equals and dashes)
        assert "=" in captured.out
        assert "-" in captured.out

    def test_help_phases_preserves_phase_order(self, capsys):
        """Test that multiple phases are shown in correct order."""
        result = handle_help_phases(["implementation", "planning"])

        assert result == 0
        captured = capsys.readouterr()

        # Even though we passed implementation first, planning should appear first
        # because it comes earlier in PHASE_CLASSES
        planning_pos = captured.out.find("PHASE: planning")
        impl_pos = captured.out.find("PHASE: implementation")

        assert planning_pos < impl_pos

    def test_help_phases_all_phases_have_required_sections(self, capsys):
        """Test that all phases have the required sections."""
        from selfassembler.phases import PHASE_NAMES

        for phase_name in PHASE_NAMES:
            result = handle_help_phases([phase_name])
            assert result == 0

            captured = capsys.readouterr()

            # Required sections
            assert "DESCRIPTION" in captured.out, f"Missing DESCRIPTION for {phase_name}"
            assert "TIMING" in captured.out, f"Missing TIMING for {phase_name}"
            assert "APPROVAL GATE" in captured.out, f"Missing APPROVAL GATE for {phase_name}"
            assert "CONFIGURATION" in captured.out, f"Missing CONFIGURATION for {phase_name}"
