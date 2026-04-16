import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

_FILENAME_RE = re.compile(r"^@([^.]+)\.(\d+)\.json$")

_VALID_STATUSES = Literal["assigned", "in_progress", "submitted", "revision_needed", "closed"]

_VALID_EVENT_TYPES = Literal[
    "contract_created", "contract_submitted", "revision_needed", "contract_closed"
]

_VALID_FILE_EVENT_TYPES = Literal["created", "modified", "moved"]


def parse_contract_filename(filename: str) -> tuple[str, str] | None:
    """Parse '@<assignee>.<id>.json' filename. Returns (assignee, id) or None."""
    m = _FILENAME_RE.match(filename)
    if m:
        return m.group(1), m.group(2)
    return None


class FileEvent(BaseModel):
    """Emitted by Watcher when a contract file changes."""

    event_type: _VALID_FILE_EVENT_TYPES
    src_path: Path
    dest_path: Path | None = None


class ContractInfo(BaseModel):
    """Parsed from a ConPact contract file."""

    assignee: str
    contract_id: str
    status: _VALID_STATUSES
    from_agent: str
    objective: str
    filepath: Path


class NotificationEvent(BaseModel):
    """Produced by EventRouter after state change analysis."""

    event_type: _VALID_EVENT_TYPES
    contract: ContractInfo
    target_agent: str
    timestamp: datetime


class AgentConfig(BaseModel):
    """Per-agent config from convoke.yaml."""

    name: str
    cli_command: str
    args: list[str] = []
    prompt_template: str


class ConVokeConfig(BaseModel):
    """Full .agents/convoke.yaml configuration."""

    agents: dict[str, AgentConfig]
    watch_path: Path
    log_level: str = "INFO"
