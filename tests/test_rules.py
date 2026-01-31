"""Tests for rules module."""

import tempfile
from pathlib import Path

from selfassembler.rules import BUILTIN_RULES, Rule, RulesManager


class TestRule:
    """Tests for Rule dataclass."""

    def test_rule_creation(self):
        """Test creating a Rule with all fields."""
        rule = Rule(
            id="test-rule",
            description="Test rule description",
            category="testing",
        )
        assert rule.id == "test-rule"
        assert rule.description == "Test rule description"
        assert rule.category == "testing"

    def test_rule_default_category(self):
        """Test that Rule has default category of 'general'."""
        rule = Rule(id="test", description="Test")
        assert rule.category == "general"

    def test_rule_equality(self):
        """Test Rule equality comparison."""
        rule1 = Rule(id="test", description="Test", category="cat")
        rule2 = Rule(id="test", description="Test", category="cat")
        assert rule1 == rule2

    def test_rule_inequality(self):
        """Test Rule inequality comparison."""
        rule1 = Rule(id="test1", description="Test")
        rule2 = Rule(id="test2", description="Test")
        assert rule1 != rule2


class TestBuiltinRules:
    """Tests for BUILTIN_RULES."""

    def test_builtin_rules_exist(self):
        """Test that expected builtin rules exist."""
        assert "no-signature" in BUILTIN_RULES
        assert "no-emojis" in BUILTIN_RULES
        assert "no-yapping" in BUILTIN_RULES

    def test_builtin_rules_are_valid(self):
        """Test that all builtin rules are valid Rule instances."""
        for rule_id, rule in BUILTIN_RULES.items():
            assert isinstance(rule, Rule)
            assert rule.id == rule_id
            assert rule.description
            assert rule.category

    def test_no_signature_rule(self):
        """Test no-signature rule content."""
        rule = BUILTIN_RULES["no-signature"]
        assert rule.id == "no-signature"
        assert "Co-Authored-By" in rule.description
        assert "signature" in rule.description.lower()
        assert rule.category == "commits"

    def test_no_emojis_rule(self):
        """Test no-emojis rule content."""
        rule = BUILTIN_RULES["no-emojis"]
        assert rule.id == "no-emojis"
        assert "emoji" in rule.description.lower()
        assert rule.category == "style"

    def test_no_yapping_rule(self):
        """Test no-yapping rule content."""
        rule = BUILTIN_RULES["no-yapping"]
        assert rule.id == "no-yapping"
        assert "concise" in rule.description.lower()
        assert rule.category == "communication"


class TestRulesManager:
    """Tests for RulesManager class."""

    def test_init_defaults(self):
        """Test RulesManager with default arguments."""
        manager = RulesManager()
        assert manager.enabled_rules == []
        assert manager.custom_rules == []

    def test_init_with_enabled_rules(self):
        """Test RulesManager with enabled rules."""
        manager = RulesManager(enabled_rules=["no-signature", "no-emojis"])
        assert manager.enabled_rules == ["no-signature", "no-emojis"]

    def test_init_with_custom_rules(self):
        """Test RulesManager with custom rules."""
        custom = ["Always test your code", "Use type hints"]
        manager = RulesManager(custom_rules=custom)
        assert manager.custom_rules == custom

    def test_init_with_none_values(self):
        """Test RulesManager handles None values gracefully."""
        manager = RulesManager(enabled_rules=None, custom_rules=None)
        assert manager.enabled_rules == []
        assert manager.custom_rules == []

    def test_get_active_rules_empty(self):
        """Test get_active_rules with no rules."""
        manager = RulesManager()
        assert manager.get_active_rules() == []

    def test_get_active_rules_builtin_only(self):
        """Test get_active_rules with only builtin rules."""
        manager = RulesManager(enabled_rules=["no-signature"])
        rules = manager.get_active_rules()
        assert len(rules) == 1
        assert rules[0].id == "no-signature"
        assert rules[0] == BUILTIN_RULES["no-signature"]

    def test_get_active_rules_multiple_builtin(self):
        """Test get_active_rules with multiple builtin rules."""
        manager = RulesManager(enabled_rules=["no-signature", "no-emojis", "no-yapping"])
        rules = manager.get_active_rules()
        assert len(rules) == 3
        rule_ids = [r.id for r in rules]
        assert "no-signature" in rule_ids
        assert "no-emojis" in rule_ids
        assert "no-yapping" in rule_ids

    def test_get_active_rules_custom_only(self):
        """Test get_active_rules with only custom rules."""
        custom = ["Always write tests", "Use descriptive names"]
        manager = RulesManager(custom_rules=custom)
        rules = manager.get_active_rules()
        assert len(rules) == 2
        assert rules[0].id == "custom-1"
        assert rules[0].description == "Always write tests"
        assert rules[0].category == "custom"
        assert rules[1].id == "custom-2"
        assert rules[1].description == "Use descriptive names"

    def test_get_active_rules_mixed(self):
        """Test get_active_rules with builtin and custom rules."""
        manager = RulesManager(
            enabled_rules=["no-signature"],
            custom_rules=["Custom rule here"],
        )
        rules = manager.get_active_rules()
        assert len(rules) == 2
        # Builtin first
        assert rules[0].id == "no-signature"
        # Then custom
        assert rules[1].id == "custom-1"
        assert rules[1].description == "Custom rule here"

    def test_get_active_rules_ignores_invalid_ids(self):
        """Test that invalid builtin rule IDs are ignored."""
        manager = RulesManager(enabled_rules=["no-signature", "invalid-rule", "no-emojis"])
        rules = manager.get_active_rules()
        assert len(rules) == 2
        rule_ids = [r.id for r in rules]
        assert "no-signature" in rule_ids
        assert "no-emojis" in rule_ids

    def test_get_active_rules_preserves_order(self):
        """Test that rules are returned in insertion order."""
        manager = RulesManager(enabled_rules=["no-emojis", "no-signature", "no-yapping"])
        rules = manager.get_active_rules()
        assert rules[0].id == "no-emojis"
        assert rules[1].id == "no-signature"
        assert rules[2].id == "no-yapping"

    def test_render_markdown_empty(self):
        """Test render_markdown with no rules."""
        manager = RulesManager()
        assert manager.render_markdown() == ""

    def test_render_markdown_structure(self):
        """Test render_markdown output structure."""
        manager = RulesManager(enabled_rules=["no-signature"])
        markdown = manager.render_markdown()

        assert "# Project Rules" in markdown
        assert "MUST be followed" in markdown
        assert BUILTIN_RULES["no-signature"].description in markdown

    def test_render_markdown_multiple_rules(self):
        """Test render_markdown with multiple rules."""
        manager = RulesManager(
            enabled_rules=["no-signature", "no-emojis"],
            custom_rules=["Custom rule"],
        )
        markdown = manager.render_markdown()

        lines = markdown.strip().split("\n")
        # Should have header, blank line, intro, blank line, rule lines, trailing blank
        assert "# Project Rules" in lines[0]
        assert any("- " + BUILTIN_RULES["no-signature"].description in line for line in lines)
        assert any("- " + BUILTIN_RULES["no-emojis"].description in line for line in lines)
        assert any("- Custom rule" in line for line in lines)

    def test_render_markdown_format(self):
        """Test render_markdown has correct format."""
        manager = RulesManager(enabled_rules=["no-signature"])
        markdown = manager.render_markdown()

        # Check structure
        assert markdown.startswith("# Project Rules\n\n")
        assert "The following rules MUST be followed:\n\n" in markdown
        assert markdown.count("- ") == 1  # One rule bullet

    def test_write_to_worktree(self):
        """Test write_to_worktree creates CLAUDE.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            manager = RulesManager(enabled_rules=["no-signature"])

            manager.write_to_worktree(worktree_path)

            claude_md = worktree_path / "CLAUDE.md"
            assert claude_md.exists()

            content = claude_md.read_text()
            assert "# Project Rules" in content
            assert BUILTIN_RULES["no-signature"].description in content

    def test_write_to_worktree_empty(self):
        """Test write_to_worktree does nothing when no rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            manager = RulesManager()

            manager.write_to_worktree(worktree_path)

            claude_md = worktree_path / "CLAUDE.md"
            assert not claude_md.exists()

    def test_write_to_worktree_overwrites(self):
        """Test write_to_worktree overwrites existing CLAUDE.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            claude_md = worktree_path / "CLAUDE.md"

            # Pre-existing content
            claude_md.write_text("Old content")

            manager = RulesManager(enabled_rules=["no-signature"])
            manager.write_to_worktree(worktree_path)

            content = claude_md.read_text()
            assert "Old content" not in content
            assert "# Project Rules" in content

    def test_write_to_worktree_with_custom_rules(self):
        """Test write_to_worktree with custom rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            manager = RulesManager(
                enabled_rules=["no-emojis"],
                custom_rules=["Always use pytest fixtures"],
            )

            manager.write_to_worktree(worktree_path)

            content = (worktree_path / "CLAUDE.md").read_text()
            assert BUILTIN_RULES["no-emojis"].description in content
            assert "Always use pytest fixtures" in content


class TestRulesManagerEdgeCases:
    """Edge case tests for RulesManager."""

    def test_duplicate_enabled_rules(self):
        """Test handling of duplicate enabled rule IDs."""
        manager = RulesManager(enabled_rules=["no-signature", "no-signature"])
        rules = manager.get_active_rules()
        # Should include duplicates as-is (implementation allows this)
        assert len(rules) == 2

    def test_empty_custom_rule(self):
        """Test handling of empty custom rule string."""
        manager = RulesManager(custom_rules=[""])
        rules = manager.get_active_rules()
        assert len(rules) == 1
        assert rules[0].description == ""

    def test_very_long_custom_rule(self):
        """Test handling of very long custom rule description."""
        long_rule = "x" * 10000
        manager = RulesManager(custom_rules=[long_rule])
        rules = manager.get_active_rules()
        assert rules[0].description == long_rule

    def test_special_characters_in_custom_rule(self):
        """Test handling of special characters in custom rules."""
        special_rule = "Don't use `backticks` or **markdown** or <html>"
        manager = RulesManager(custom_rules=[special_rule])
        rules = manager.get_active_rules()
        assert rules[0].description == special_rule

        markdown = manager.render_markdown()
        assert special_rule in markdown

    def test_unicode_in_custom_rule(self):
        """Test handling of unicode in custom rules."""
        unicode_rule = "No emojis 🚫 or special chars: àéïõü"
        manager = RulesManager(custom_rules=[unicode_rule])
        rules = manager.get_active_rules()
        assert rules[0].description == unicode_rule

    def test_newlines_in_custom_rule(self):
        """Test handling of newlines in custom rule description."""
        multiline_rule = "Rule line 1\nRule line 2\nRule line 3"
        manager = RulesManager(custom_rules=[multiline_rule])
        rules = manager.get_active_rules()
        assert rules[0].description == multiline_rule

    def test_many_custom_rules(self):
        """Test handling of many custom rules."""
        many_rules = [f"Custom rule {i}" for i in range(100)]
        manager = RulesManager(custom_rules=many_rules)
        rules = manager.get_active_rules()
        assert len(rules) == 100
        assert rules[99].id == "custom-100"


class TestRulesIntegration:
    """Integration tests for rules with config and orchestrator."""

    def test_rules_manager_from_config(self):
        """Test creating RulesManager from WorkflowConfig."""
        from selfassembler.config import WorkflowConfig

        config = WorkflowConfig()
        config.rules.enabled_rules = ["no-signature", "no-emojis"]
        config.rules.custom_rules = ["Always write tests"]

        manager = RulesManager(
            enabled_rules=config.rules.enabled_rules,
            custom_rules=config.rules.custom_rules,
        )

        rules = manager.get_active_rules()
        assert len(rules) == 3
        assert rules[0].id == "no-signature"
        assert rules[1].id == "no-emojis"
        assert rules[2].id == "custom-1"

    def test_rules_manager_with_default_config(self):
        """Test RulesManager works with default config (no-signature enabled)."""
        from selfassembler.config import WorkflowConfig

        config = WorkflowConfig()
        manager = RulesManager(
            enabled_rules=config.rules.enabled_rules,
            custom_rules=config.rules.custom_rules,
        )

        rules = manager.get_active_rules()
        assert len(rules) == 1
        assert rules[0].id == "no-signature"

    def test_write_rules_to_worktree_integration(self):
        """Test full workflow of writing rules from config to worktree."""
        from selfassembler.config import WorkflowConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)

            config = WorkflowConfig()
            config.rules.enabled_rules = ["no-signature", "no-yapping"]
            config.rules.custom_rules = ["Use pytest fixtures"]

            manager = RulesManager(
                enabled_rules=config.rules.enabled_rules,
                custom_rules=config.rules.custom_rules,
            )
            manager.write_to_worktree(worktree_path)

            claude_md = worktree_path / "CLAUDE.md"
            assert claude_md.exists()

            content = claude_md.read_text()
            assert "# Project Rules" in content
            assert BUILTIN_RULES["no-signature"].description in content
            assert BUILTIN_RULES["no-yapping"].description in content
            assert "Use pytest fixtures" in content

    def test_rules_config_empty_disables_rules(self):
        """Test that empty rules config results in no CLAUDE.md written."""
        from selfassembler.config import WorkflowConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)

            config = WorkflowConfig()
            config.rules.enabled_rules = []
            config.rules.custom_rules = []

            manager = RulesManager(
                enabled_rules=config.rules.enabled_rules,
                custom_rules=config.rules.custom_rules,
            )
            manager.write_to_worktree(worktree_path)

            claude_md = worktree_path / "CLAUDE.md"
            assert not claude_md.exists()
