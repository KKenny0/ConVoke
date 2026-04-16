import logging
from datetime import datetime
from pathlib import Path

from convoke.models import ContractInfo, FileEvent, NotificationEvent

logger = logging.getLogger(__name__)


class EventRouter:
    """Routes contract file state changes to notification events.

    Maintains a cache of known contract states. Compares new state against
    cache to determine what notification events to emit.
    """

    def __init__(self):
        # filepath -> {status, contract_info}
        self._state: dict[Path, dict] = {}

    def route(
        self, event: FileEvent, contract_info: ContractInfo | None
    ) -> list[NotificationEvent]:
        """Determine notification events for a file event.

        Args:
            event: The raw file system event.
            contract_info: Parsed contract info, or None if file is not a contract.

        Returns:
            List of NotificationEvent to dispatch. Empty if no notification needed.
        """
        now = datetime.now()
        notifications: list[NotificationEvent] = []

        # Moved to archive -> contract_closed
        if event.event_type == "moved" and event.dest_path and "_archive" in str(event.dest_path):
            cached = self._state.pop(event.src_path, None)
            if cached:
                info = cached["contract_info"]
                notifications.append(
                    NotificationEvent(
                        event_type="contract_closed",
                        contract=info,
                        target_agent=info.from_agent,
                        timestamp=now,
                    )
                )
                notifications.append(
                    NotificationEvent(
                        event_type="contract_closed",
                        contract=info,
                        target_agent=info.assignee,
                        timestamp=now,
                    )
                )
            return notifications

        # Not a contract file -> skip
        if contract_info is None:
            return notifications

        cached = self._state.get(event.src_path)
        old_status = cached["status"] if cached else None

        # No state change -> skip
        if old_status == contract_info.status:
            return notifications

        # New contract
        if old_status is None:
            self._state[event.src_path] = {
                "status": contract_info.status,
                "contract_info": contract_info,
            }
            notifications.append(
                NotificationEvent(
                    event_type="contract_created",
                    contract=contract_info,
                    target_agent=contract_info.assignee,
                    timestamp=now,
                )
            )
            return notifications

        # State transition
        event_type = self._determine_event_type(old_status, contract_info.status)
        if event_type is None:
            self._state[event.src_path]["status"] = contract_info.status
            self._state[event.src_path]["contract_info"] = contract_info
            return notifications

        target = self._determine_target(event_type, contract_info)
        self._state[event.src_path]["status"] = contract_info.status
        self._state[event.src_path]["contract_info"] = contract_info

        notifications.append(
            NotificationEvent(
                event_type=event_type,
                contract=contract_info,
                target_agent=target,
                timestamp=now,
            )
        )
        return notifications

    @staticmethod
    def _determine_event_type(old_status: str, new_status: str) -> str | None:
        if new_status == "submitted":
            return "contract_submitted"
        if new_status == "revision_needed":
            return "revision_needed"
        return None

    @staticmethod
    def _determine_target(event_type: str, contract: ContractInfo) -> str:
        if event_type == "contract_submitted":
            return contract.from_agent
        return contract.assignee
