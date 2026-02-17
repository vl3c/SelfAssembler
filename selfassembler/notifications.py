"""Notification system for workflow events."""

from __future__ import annotations

import contextlib
import json
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from selfassembler.context import WorkflowContext
    from selfassembler.executor import StreamEvent
    from selfassembler.phases import PhaseResult


class NotificationChannel(ABC):
    """Base class for notification channels."""

    @abstractmethod
    def send(self, message: str, level: str = "info", data: dict | None = None) -> bool:
        """Send a notification message."""
        pass


class ConsoleChannel(NotificationChannel):
    """Console output notification channel."""

    def __init__(self, colors: bool = True):
        self.colors = colors
        self._level_colors = {
            "info": "\033[36m",  # Cyan
            "success": "\033[32m",  # Green
            "warning": "\033[33m",  # Yellow
            "error": "\033[31m",  # Red
        }
        self._reset = "\033[0m"

    def send(self, message: str, level: str = "info", data: dict | None = None) -> bool:
        """Print notification to console."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if self.colors:
            color = self._level_colors.get(level, "")
            prefix = f"{color}[{timestamp}]{self._reset}"
        else:
            prefix = f"[{timestamp}]"

        for line in message.strip().split("\n"):
            print(f"{prefix} {line}")

        return True


class WebhookChannel(NotificationChannel):
    """Webhook notification channel."""

    def __init__(self, url: str, events: list[str] | None = None):
        self.url = url
        self.events = events or ["workflow_complete", "workflow_failed", "approval_needed"]

    def send(
        self, message: str, level: str = "info", data: dict | None = None, event: str | None = None
    ) -> bool:
        """Send notification to webhook.

        Args:
            message: The notification message
            level: Severity level (info, success, warning, error)
            data: Additional structured data
            event: Event type for filtering (if None, always sends)

        Returns:
            True if sent successfully
        """
        # Filter by configured events if event type is provided
        if event is not None and event not in self.events:
            return True  # Silently skip filtered events

        payload = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "data": data or {},
        }

        try:
            request = urllib.request.Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False


class SlackChannel(NotificationChannel):
    """Slack notification channel using incoming webhooks."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._level_emojis = {
            "info": ":information_source:",
            "success": ":white_check_mark:",
            "warning": ":warning:",
            "error": ":x:",
        }

    def send(self, message: str, level: str = "info", data: dict | None = None) -> bool:
        """Send notification to Slack."""
        emoji = self._level_emojis.get(level, ":speech_balloon:")

        payload = {
            "text": f"{emoji} {message}",
            "unfurl_links": False,
        }

        if data:
            payload["attachments"] = [
                {"fields": [{"title": k, "value": str(v), "short": True} for k, v in data.items()]}
            ]

        try:
            request = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False


class Notifier:
    """
    Central notification dispatcher.

    Routes notifications to configured channels and provides
    convenience methods for common workflow events.
    """

    def __init__(self, channels: list[NotificationChannel] | None = None):
        self.channels = channels or []

    def add_channel(self, channel: NotificationChannel) -> None:
        """Add a notification channel."""
        self.channels.append(channel)

    def _send(
        self, message: str, level: str = "info", data: dict | None = None, event: str | None = None
    ) -> None:
        """Send a message to all channels."""
        for channel in self.channels:
            with contextlib.suppress(Exception):
                if isinstance(channel, WebhookChannel):
                    channel.send(message, level, data, event=event)
                else:
                    channel.send(message, level, data)

    def on_workflow_started(self, context: WorkflowContext) -> None:
        """Notify that workflow has started."""
        self._send(
            f"Starting workflow: {context.task_name}\n"
            f"Task: {context.task_description}\n"
            f"Budget: ${context.budget_limit_usd:.2f}",
            level="info",
            data={"task_name": context.task_name, "budget": context.budget_limit_usd},
            event="workflow_started",
        )

    def on_phase_started(self, phase: str) -> None:
        """Notify that a phase has started."""
        self._send(f"Starting phase: {phase}", level="info", event="phase_started")

    def on_phase_complete(self, phase: str, result: PhaseResult) -> None:
        """Notify that a phase completed successfully."""
        cost_str = f" (${result.cost_usd:.2f})" if result.cost_usd > 0 else ""
        self._send(f"Phase complete: {phase}{cost_str}", level="success", event="phase_complete")

    def on_phase_failed(self, phase: str, result: PhaseResult, will_retry: bool = False) -> None:
        """Notify that a phase failed."""
        if result.error:
            error_preview = result.error[:200]
        else:
            # Build a more informative message when error field is empty
            hints = []
            if result.artifacts:
                for key, val in result.artifacts.items():
                    hints.append(f"{key}={str(val)[:100]}")
            if hasattr(result, "failure_category") and result.failure_category:
                hints.append(f"category={result.failure_category}")
            if hints:
                error_preview = f"No error message (hints: {'; '.join(hints[:3])})"
            else:
                error_preview = (
                    "No error message — the agent may have crashed or produced no output. "
                    "Check the workflow log for details."
                )
        retry_msg = " (will retry)" if will_retry else ""
        level = "warning" if will_retry else "error"
        self._send(
            f"Phase failed: {phase}{retry_msg}\nError: {error_preview}",
            level=level,
            data={"phase": phase, "error": result.error, "will_retry": will_retry},
            event="phase_failed",
        )

    def on_phase_retry(self, phase: str, attempt: int, max_retries: int) -> None:
        """Notify that a phase is being retried."""
        self._send(
            f"Retrying phase: {phase} (attempt {attempt + 1}/{max_retries + 1})",
            level="info",
            data={"phase": phase, "attempt": attempt, "max_retries": max_retries},
            event="phase_retry",
        )

    def on_approval_needed(self, phase: str, artifacts: dict[str, Any]) -> None:
        """Notify that approval is needed for a phase."""
        artifact_info = ", ".join(f"{k}: {v}" for k, v in artifacts.items())
        self._send(
            f"Approval needed for phase: {phase}\n"
            f"Review artifacts and create .approved_{phase} file to continue.\n"
            f"Artifacts: {artifact_info}",
            level="warning",
            data={"phase": phase, "artifacts": artifacts},
            event="approval_needed",
        )

    def on_workflow_complete(self, context: WorkflowContext) -> None:
        """Notify that workflow completed successfully."""
        workflow_warnings = context.get_artifact("workflow_warnings", [])
        warnings_section = ""
        if workflow_warnings:
            warnings_section = "\nWarnings:\n" + "\n".join(f"  - {w}" for w in workflow_warnings) + "\n"

        message = f"""
Workflow complete: {context.task_name}

PR: {context.pr_url or "Not created"}
Branch: {context.branch_name or "N/A"}
Total cost: ${context.total_cost_usd:.2f}
Duration: {context.elapsed_time():.0f}s
{warnings_section}
Ready for human review.
"""
        self._send(
            message.strip(),
            level="success",
            data={
                "task_name": context.task_name,
                "pr_url": context.pr_url,
                "branch": context.branch_name,
                "cost_usd": context.total_cost_usd,
                "duration_s": context.elapsed_time(),
                "warnings": workflow_warnings or None,
            },
            event="workflow_complete",
        )

    def on_workflow_failed(self, context: WorkflowContext, error: Exception) -> None:
        """Notify that workflow failed."""
        message = f"""
Workflow failed: {context.task_name}

Phase: {context.current_phase}
Error: {error}
Cost so far: ${context.total_cost_usd:.2f}

Resume with: selfassembler --resume {context.checkpoint_id}
"""
        self._send(
            message.strip(),
            level="error",
            data={
                "task_name": context.task_name,
                "phase": context.current_phase,
                "error": str(error),
                "cost_usd": context.total_cost_usd,
                "checkpoint_id": context.checkpoint_id,
            },
            event="workflow_failed",
        )

    def on_budget_warning(self, context: WorkflowContext, threshold: float = 0.8) -> None:
        """Notify when budget usage exceeds threshold."""
        usage = context.total_cost_usd / context.budget_limit_usd
        if usage >= threshold:
            self._send(
                f"Budget warning: ${context.total_cost_usd:.2f} / ${context.budget_limit_usd:.2f} "
                f"({usage * 100:.0f}% used)",
                level="warning",
                data={
                    "current_cost": context.total_cost_usd,
                    "budget_limit": context.budget_limit_usd,
                    "usage_percent": usage * 100,
                },
                event="budget_warning",
            )

    def on_checkpoint_created(self, checkpoint_id: str) -> None:
        """Notify that a checkpoint was created."""
        self._send(f"Checkpoint created: {checkpoint_id}", level="info", event="checkpoint_created")

    def on_stream_event(
        self,
        event: StreamEvent,
        show_tool_calls: bool = True,
        truncate_length: int = 200,
    ) -> None:
        """Handle a streaming event from Claude CLI."""
        if event.event_type == "tool_use" and show_tool_calls:
            tool_name = event.data.get("name", "unknown")
            self._send(f"  Using tool: {tool_name}", level="info")
        elif event.event_type == "assistant":
            # Extract and show truncated text from assistant message
            content = event.data.get("content", "")
            if isinstance(content, list):
                # Handle content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = " ".join(text_parts)
            if content:
                preview = content[:truncate_length]
                if len(content) > truncate_length:
                    preview += "..."
                # Only show non-empty previews
                if preview.strip():
                    self._send(f"  {preview}", level="info")
        elif event.event_type == "system":
            # System messages like session start
            message = event.data.get("message", "")
            if message:
                self._send(f"  {message}", level="info")


def create_stream_callback(
    notifier: Notifier,
    show_tool_calls: bool = True,
    truncate_length: int = 200,
) -> Any:
    """Create a stream callback function from a notifier."""

    def callback(event: StreamEvent) -> None:
        notifier.on_stream_event(event, show_tool_calls, truncate_length)

    return callback


def create_notifier_from_config(config: dict[str, Any]) -> Notifier:
    """Create a Notifier from configuration."""
    channels: list[NotificationChannel] = []

    notifications_config = config.get("notifications", {})

    # Console channel
    console_config = notifications_config.get("console", {})
    if console_config.get("enabled", True):
        channels.append(ConsoleChannel(colors=console_config.get("colors", True)))

    # Webhook channel
    webhook_config = notifications_config.get("webhook", {})
    if webhook_config.get("enabled") and webhook_config.get("url"):
        channels.append(
            WebhookChannel(
                url=webhook_config["url"],
                events=webhook_config.get("events"),
            )
        )

    # Slack channel (if configured)
    slack_config = notifications_config.get("slack", {})
    if slack_config.get("enabled") and slack_config.get("webhook_url"):
        channels.append(SlackChannel(webhook_url=slack_config["webhook_url"]))

    return Notifier(channels)
