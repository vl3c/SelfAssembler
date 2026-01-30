"""Notification system for workflow events."""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from claudonomous.context import WorkflowContext
    from claudonomous.phases import PhaseResult


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

    def send(self, message: str, level: str = "info", data: dict | None = None) -> bool:
        """Send notification to webhook."""
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
                {
                    "fields": [
                        {"title": k, "value": str(v), "short": True} for k, v in data.items()
                    ]
                }
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

    def _send(self, message: str, level: str = "info", data: dict | None = None) -> None:
        """Send a message to all channels."""
        for channel in self.channels:
            try:
                channel.send(message, level, data)
            except Exception:
                pass  # Don't let notification failures break workflow

    def on_workflow_started(self, context: "WorkflowContext") -> None:
        """Notify that workflow has started."""
        self._send(
            f"Starting workflow: {context.task_name}\n"
            f"Task: {context.task_description}\n"
            f"Budget: ${context.budget_limit_usd:.2f}",
            level="info",
            data={"task_name": context.task_name, "budget": context.budget_limit_usd},
        )

    def on_phase_started(self, phase: str) -> None:
        """Notify that a phase has started."""
        self._send(f"Starting phase: {phase}", level="info")

    def on_phase_complete(self, phase: str, result: "PhaseResult") -> None:
        """Notify that a phase completed successfully."""
        cost_str = f" (${result.cost_usd:.2f})" if result.cost_usd > 0 else ""
        self._send(f"Phase complete: {phase}{cost_str}", level="success")

    def on_phase_failed(self, phase: str, result: "PhaseResult") -> None:
        """Notify that a phase failed."""
        error_preview = result.error[:200] if result.error else "Unknown error"
        self._send(
            f"Phase failed: {phase}\nError: {error_preview}",
            level="error",
            data={"phase": phase, "error": result.error},
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
        )

    def on_workflow_complete(self, context: "WorkflowContext") -> None:
        """Notify that workflow completed successfully."""
        message = f"""
Workflow complete: {context.task_name}

PR: {context.pr_url or 'Not created'}
Branch: {context.branch_name or 'N/A'}
Total cost: ${context.total_cost_usd:.2f}
Duration: {context.elapsed_time():.0f}s

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
            },
        )

    def on_workflow_failed(self, context: "WorkflowContext", error: Exception) -> None:
        """Notify that workflow failed."""
        message = f"""
Workflow failed: {context.task_name}

Phase: {context.current_phase}
Error: {error}
Cost so far: ${context.total_cost_usd:.2f}

Resume with: claudonomous --resume {context.checkpoint_id}
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
        )

    def on_budget_warning(self, context: "WorkflowContext", threshold: float = 0.8) -> None:
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
            )

    def on_checkpoint_created(self, checkpoint_id: str) -> None:
        """Notify that a checkpoint was created."""
        self._send(f"Checkpoint created: {checkpoint_id}", level="info")


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
