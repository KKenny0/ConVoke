import logging
import subprocess
import time
from collections import defaultdict
from typing import Protocol

from convoke.models import ConVokeConfig, NotificationEvent

logger = logging.getLogger(__name__)

_RETRY_DELAY_S = 2


def render_prompt(template: str, event: NotificationEvent) -> str:
    """Render a prompt template with notification context.

    Uses defaultdict(str) so unknown placeholders become empty string.
    Falls back to a generic message on ValueError (malformed template).
    """
    context = defaultdict(str, {
        "from_agent": event.contract.from_agent,
        "assignee": event.contract.assignee,
        "contract_id": event.contract.contract_id,
        "objective": event.contract.objective,
        "status": event.contract.status,
        "event_type": event.event_type,
    })
    try:
        return template.format_map(context)
    except (ValueError, KeyError):
        logger.warning("Failed to render template: %s", template)
        return f"ConVoke notification: {event.event_type} for {event.target_agent}"


class Notifier(Protocol):
    def notify(self, event: NotificationEvent) -> None: ...


class CLINotifier:
    """Wakes agents by spawning their CLI with a notification prompt."""

    def __init__(self, config: ConVokeConfig):
        self._config = config
        self._active_subprocesses: list[subprocess.Popen] = []

    def notify(self, event: NotificationEvent) -> None:
        """Send a notification by invoking the target agent's CLI."""
        agent_config = self._config.agents.get(event.target_agent)
        if agent_config is None:
            logger.warning("Unknown agent: %s — skipping notification", event.target_agent)
            return

        self._cleanup_completed()

        prompt = render_prompt(agent_config.prompt_template, event)
        cmd = [agent_config.cli_command, *agent_config.args, prompt]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._active_subprocesses.append(proc)
            logger.info(
                "Launched %s for %s (event: %s)",
                agent_config.cli_command, event.target_agent, event.event_type,
            )
        except FileNotFoundError:
            logger.error("CLI not found: %s — notification failed", agent_config.cli_command)
        except OSError as e:
            logger.error("Failed to launch %s: %s", agent_config.cli_command, e)

    def stop(self, timeout: float = 5.0) -> None:
        """Wait for in-flight subprocesses to complete, then terminate."""
        self._cleanup_completed()
        deadline = time.monotonic() + timeout
        for proc in self._active_subprocesses:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                proc.wait(timeout=remaining)
            if proc.poll() is None:
                proc.terminate()
                logger.warning("Terminated subprocess (PID %s)", proc.pid)
        self._active_subprocesses.clear()

    def _cleanup_completed(self) -> None:
        """Remove completed subprocesses from tracking list."""
        still_running = []
        for proc in self._active_subprocesses:
            if proc.poll() is not None:
                pass
            else:
                still_running.append(proc)
        self._active_subprocesses = still_running
