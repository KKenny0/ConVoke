import logging
import signal
import sys
import threading

from convoke.models import ConVokeConfig, FileEvent
from convoke.notifier import CLINotifier
from convoke.router import EventRouter
from convoke.watcher import WatchdogWatcher, parse_contract_file

logger = logging.getLogger(__name__)


class ConVokeDaemon:
    """Main daemon that orchestrates file watching, event routing, and notification."""

    def __init__(self, config: ConVokeConfig):
        self._config = config
        self.watcher = WatchdogWatcher(config.watch_path)
        self.router = EventRouter()
        self.notifier = CLINotifier(config)
        self._running = False
        self._stop_event = threading.Event()

    def run(self, foreground: bool = True) -> None:
        """Start the daemon. Blocks until stopped."""
        self._running = True

        self._seed_state()

        if foreground:
            self._register_signal_handlers()

        self.watcher.start(self._on_file_event)

        if foreground:
            try:
                self._stop_event.wait()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def _seed_state(self) -> None:
        """Scan existing contracts to build initial state cache."""
        watch_path = self._config.watch_path
        if not watch_path.exists():
            logger.info("Watch path does not exist yet: %s", watch_path)
            return

        for filepath in watch_path.rglob("*.json"):
            if "_archive" in str(filepath):
                continue
            info = parse_contract_file(filepath)
            if info:
                self.router._state[filepath] = {
                    "status": info.status,
                    "contract_info": info,
                }
        logger.info("Seeded state with %d existing contracts", len(self.router._state))

    def _on_file_event(self, event: FileEvent) -> None:
        """Handle a file system event: parse contract, route, notify."""
        contract_info = parse_contract_file(event.src_path)
        notifications = self.router.route(event, contract_info=contract_info)
        for notification in notifications:
            self.notifier.notify(notification)

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self.stop()

    def stop(self) -> None:
        """Gracefully stop the daemon."""
        self._running = False
        self._stop_event.set()
        self.watcher.stop()
        self.notifier.stop(timeout=5.0)
        logger.info("Daemon stopped")
