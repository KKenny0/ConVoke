import json
import logging
import threading
from pathlib import Path
from typing import Callable, Protocol

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from convoke.models import ContractInfo, FileEvent, parse_contract_filename

logger = logging.getLogger(__name__)


class Watcher(Protocol):
    def start(self, callback: Callable[[FileEvent], None]) -> None: ...
    def stop(self) -> None: ...


def parse_contract_file(filepath: Path) -> ContractInfo | None:
    """Parse a ConPact contract JSON file into ContractInfo.

    Returns None if filename doesn't match pattern or JSON is invalid.
    """
    filename = filepath.name
    parsed = parse_contract_filename(filename)
    if parsed is None:
        return None

    assignee, contract_id = parsed

    try:
        with open(filepath) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read contract file: %s", filepath)
        return None

    try:
        return ContractInfo(
            assignee=assignee,
            contract_id=contract_id,
            status=data["status"],
            from_agent=data["from"],
            objective=data.get("delegation", {}).get("objective", ""),
            filepath=filepath,
        )
    except KeyError:
        logger.warning("Contract file missing required fields: %s", filepath)
        return None


_DEBOUNCE_MS = 500


class WatchdogWatcher:
    """Watches a directory for contract file changes using watchdog."""

    def __init__(self, watch_path: Path):
        self._watch_path = watch_path
        self._observer: Observer | None = None
        self._callback: Callable[[FileEvent], None] | None = None
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self, callback: Callable[[FileEvent], None]) -> None:
        self._callback = callback
        self._setup_observer()
        self._observer.start()
        logger.info("Watching: %s", self._watch_path)

    def _setup_observer(self) -> None:
        handler = _ContractEventHandler(self._on_raw_event)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._watch_path), recursive=True)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()

    def _on_raw_event(self, event: FileEvent) -> None:
        """Apply per-file-path debounce: dedup within 500ms window."""
        path_key = str(event.src_path)
        with self._lock:
            if path_key in self._debounce_timers:
                self._debounce_timers[path_key].cancel()

            def fire():
                with self._lock:
                    self._debounce_timers.pop(path_key, None)
                if self._callback:
                    self._callback(event)

            self._debounce_timers[path_key] = threading.Timer(_DEBOUNCE_MS / 1000.0, fire)
            self._debounce_timers[path_key].start()


class _ContractEventHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[FileEvent], None]):
        self._callback = callback

    def on_created(self, event):
        if not event.is_directory:
            self._callback(FileEvent(event_type="created", src_path=Path(event.src_path)))

    def on_modified(self, event):
        if not event.is_directory:
            self._callback(FileEvent(event_type="modified", src_path=Path(event.src_path)))

    def on_moved(self, event):
        if not event.is_directory:
            self._callback(
                FileEvent(
                    event_type="moved",
                    src_path=Path(event.src_path),
                    dest_path=Path(event.dest_path),
                )
            )
