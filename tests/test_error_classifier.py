"""Tests for error classifier module."""

import pytest

from selfassembler.error_classifier import (
    AGENT_ERROR_PATTERNS,
    ClassificationResult,
    ErrorOrigin,
    ErrorPattern,
    classify_error,
    is_agent_specific_error,
)


class TestErrorOrigin:
    """Tests for ErrorOrigin enum."""

    def test_values(self):
        assert ErrorOrigin.AGENT.value == "agent"
        assert ErrorOrigin.TASK.value == "task"
        assert ErrorOrigin.UNKNOWN.value == "unknown"


class TestErrorPattern:
    """Tests for ErrorPattern matching."""

    def test_basic_match(self):
        pattern = ErrorPattern(
            pattern=r"\brate[_\s-]?limit",
            origin=ErrorOrigin.AGENT,
            description="Rate limit",
        )
        assert pattern.matches("Hit rate limit on API")
        assert pattern.matches("rate_limit exceeded")
        assert pattern.matches("rate-limit error")

    def test_no_match(self):
        pattern = ErrorPattern(
            pattern=r"\brate[_\s-]?limit",
            origin=ErrorOrigin.AGENT,
            description="Rate limit",
        )
        assert not pattern.matches("Test passed successfully")
        assert not pattern.matches("accurate_limiting function")

    def test_case_insensitive(self):
        pattern = ErrorPattern(
            pattern=r"\bRate[_\s-]?Limit",
            origin=ErrorOrigin.AGENT,
            description="Rate limit",
        )
        assert pattern.matches("RATE LIMIT exceeded")
        assert pattern.matches("rate limit hit")

    def test_agent_type_filtering(self):
        pattern = ErrorPattern(
            pattern=r"No result event received",
            origin=ErrorOrigin.AGENT,
            description="Claude-only pattern",
            agent_types=frozenset({"claude"}),
        )
        assert pattern.matches("No result event received", "claude")
        assert not pattern.matches("No result event received", "codex")
        # None agent_type matches (no filtering)
        assert pattern.matches("No result event received", None)

    def test_no_agent_types_restriction(self):
        pattern = ErrorPattern(
            pattern=r"\boverloaded\b",
            origin=ErrorOrigin.AGENT,
            description="Overloaded",
        )
        assert pattern.matches("Service overloaded", "claude")
        assert pattern.matches("Service overloaded", "codex")


class TestClassifyErrorRateLimiting:
    """Tests for rate limiting error classification."""

    def test_rate_limit(self):
        result = classify_error("Error: rate limit exceeded")
        assert result.origin == ErrorOrigin.AGENT
        assert len(result.matched_patterns) > 0

    def test_rate_limit_underscore(self):
        result = classify_error("rate_limit error from API")
        assert result.origin == ErrorOrigin.AGENT

    def test_too_many_requests(self):
        result = classify_error("HTTP 429: too many requests")
        assert result.origin == ErrorOrigin.AGENT

    def test_throttled(self):
        result = classify_error("Request was throttled by the API")
        assert result.origin == ErrorOrigin.AGENT


class TestClassifyErrorTokenLimits:
    """Tests for token/context limit error classification."""

    def test_token_limit(self):
        result = classify_error("token limit exceeded for this conversation")
        assert result.origin == ErrorOrigin.AGENT

    def test_context_window(self):
        result = classify_error("The context window has been exhausted")
        assert result.origin == ErrorOrigin.AGENT

    def test_max_tokens(self):
        result = classify_error("Reached max tokens for this request")
        assert result.origin == ErrorOrigin.AGENT

    def test_conversation_too_long(self):
        result = classify_error("conversation too long, please start a new one")
        assert result.origin == ErrorOrigin.AGENT

    def test_context_length(self):
        result = classify_error("context length exceeded for model")
        assert result.origin == ErrorOrigin.AGENT


class TestClassifyErrorAuth:
    """Tests for authentication/authorization error classification."""

    def test_auth_failed(self):
        result = classify_error("authentication failed: invalid credentials")
        assert result.origin == ErrorOrigin.AGENT

    def test_authorization_error(self):
        result = classify_error("authorization error: insufficient permissions")
        assert result.origin == ErrorOrigin.AGENT

    def test_unauthorized(self):
        result = classify_error("HTTP 401 unauthorized")
        assert result.origin == ErrorOrigin.AGENT

    def test_invalid_api_key(self):
        result = classify_error("invalid api key provided")
        assert result.origin == ErrorOrigin.AGENT

    def test_insufficient_quota(self):
        result = classify_error("insufficient quota for this operation")
        assert result.origin == ErrorOrigin.AGENT

    def test_billing_account(self):
        result = classify_error("billing account suspended")
        assert result.origin == ErrorOrigin.AGENT

    def test_billing_error(self):
        result = classify_error("billing error: payment declined")
        assert result.origin == ErrorOrigin.AGENT

    def test_payment_required(self):
        result = classify_error("payment required to continue")
        assert result.origin == ErrorOrigin.AGENT


class TestClassifyErrorService:
    """Tests for service error classification."""

    def test_overloaded(self):
        result = classify_error("The server is currently overloaded")
        assert result.origin == ErrorOrigin.AGENT

    def test_internal_server_error(self):
        result = classify_error("internal server error occurred")
        assert result.origin == ErrorOrigin.AGENT


class TestClassifyErrorSASpecific:
    """Tests for SA-specific error strings."""

    def test_possible_auth(self):
        result = classify_error("possible auth issue detected")
        assert result.origin == ErrorOrigin.AGENT

    def test_no_result_event_claude(self):
        result = classify_error("No result event received", "claude")
        assert result.origin == ErrorOrigin.AGENT

    def test_no_result_event_codex_not_matched(self):
        result = classify_error("No result event received", "codex")
        # The claude-only pattern should not match, but it may still match
        # on other generic patterns — check that the specific pattern doesn't fire
        for p in result.matched_patterns:
            assert p != "Claude produced no result event"

    def test_agent_produced_no_output(self):
        result = classify_error("Agent produced no output and reported zero cost")
        assert result.origin == ErrorOrigin.AGENT

    def test_no_parseable_output(self):
        result = classify_error("No parseable output from the agent CLI")
        assert result.origin == ErrorOrigin.AGENT


class TestClassifyErrorNegativeCases:
    """Tests that task errors are NOT classified as agent-specific."""

    def test_code_error(self):
        result = classify_error("TypeError: cannot read property 'foo' of undefined")
        assert result.origin == ErrorOrigin.TASK

    def test_test_failure(self):
        result = classify_error("FAILED tests/test_foo.py::test_bar - AssertionError")
        assert result.origin == ErrorOrigin.TASK

    def test_lint_error(self):
        result = classify_error("src/foo.py:42:10: E501 line too long (120 > 79)")
        assert result.origin == ErrorOrigin.TASK

    def test_http_status_in_test_output(self):
        """Bare HTTP status codes in test output should NOT trigger false positives."""
        result = classify_error("test_api_response: expected 429, got 200")
        assert result.origin == ErrorOrigin.TASK

    def test_status_code_503_in_test(self):
        result = classify_error("assert response.status_code == 503")
        assert result.origin == ErrorOrigin.TASK

    def test_billing_code_not_matched(self):
        """Bare 'billing' in code context should not trigger false positives."""
        result = classify_error("Updated billing module with new features")
        assert result.origin == ErrorOrigin.TASK

    def test_credit_word_not_matched(self):
        """Bare 'credit' should not trigger false positives."""
        result = classify_error("Added credit card form validation")
        assert result.origin == ErrorOrigin.TASK

    def test_import_error(self):
        result = classify_error("ImportError: No module named 'nonexistent'")
        assert result.origin == ErrorOrigin.TASK

    def test_syntax_error(self):
        result = classify_error("SyntaxError: unexpected token )")
        assert result.origin == ErrorOrigin.TASK

    def test_compilation_error(self):
        result = classify_error("error[E0308]: mismatched types")
        assert result.origin == ErrorOrigin.TASK


class TestClassifyErrorEdgeCases:
    """Tests for edge cases."""

    def test_empty_string(self):
        result = classify_error("")
        assert result.origin == ErrorOrigin.UNKNOWN

    def test_none_input(self):
        result = classify_error(None)
        assert result.origin == ErrorOrigin.UNKNOWN

    def test_multiple_patterns_match(self):
        error = "rate limit exceeded, token limit also hit, unauthorized access"
        result = classify_error(error)
        assert result.origin == ErrorOrigin.AGENT
        assert len(result.matched_patterns) >= 3
        assert result.confidence > 0.5

    def test_confidence_increases_with_matches(self):
        single = classify_error("rate limit hit")
        multi = classify_error("rate limit and token limit and unauthorized and billing error")
        assert multi.confidence >= single.confidence


class TestIsAgentSpecificError:
    """Tests for the convenience is_agent_specific_error function."""

    def test_agent_error(self):
        assert is_agent_specific_error("rate limit exceeded") is True

    def test_task_error(self):
        assert is_agent_specific_error("TypeError: undefined is not a function") is False

    def test_empty(self):
        assert is_agent_specific_error("") is False

    def test_none(self):
        assert is_agent_specific_error(None) is False

    def test_with_agent_type(self):
        assert is_agent_specific_error("No result event received", "claude") is True


class TestWordBoundaries:
    """Tests that word boundaries prevent false positives."""

    def test_rate_limit_word_boundary(self):
        """'rate limit' should match but 'accurate_limiting' should not."""
        assert is_agent_specific_error("rate limit exceeded") is True
        assert is_agent_specific_error("accurate_limiting function called") is False

    def test_overloaded_word_boundary(self):
        assert is_agent_specific_error("server overloaded") is True
        assert is_agent_specific_error("method overloaded in class") is True  # Still matches \boverloaded\b

    def test_unauthorized_word_boundary(self):
        assert is_agent_specific_error("401 unauthorized") is True
