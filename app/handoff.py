from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.models import ControlOwner


class HandoffState(str, Enum):
    AUTOMATION = "automation"
    PAUSED_FOR_HUMAN = "paused_for_human"
    HUMAN_CONTROL = "human_control"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Intervention:
    run_id: str
    reason: str
    step_id: str | None
    evidence_path: str | None
    current_url: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HandoffController:
    def __init__(self) -> None:
        self.state = HandoffState.AUTOMATION
        self.owner = ControlOwner.AUTOMATION
        self.active: Intervention | None = None

    def request(self, intervention: Intervention) -> Intervention:
        if self.owner != ControlOwner.AUTOMATION:
            raise RuntimeError("Only automation may request a handoff")
        self.active = intervention
        self.state = HandoffState.PAUSED_FOR_HUMAN
        self.owner = ControlOwner.NONE
        return intervention

    def take_control(self) -> None:
        if self.state != HandoffState.PAUSED_FOR_HUMAN:
            raise RuntimeError("No paused intervention is available")
        self.state = HandoffState.HUMAN_CONTROL
        self.owner = ControlOwner.HUMAN

    def resume_automation(self) -> None:
        if self.state != HandoffState.HUMAN_CONTROL:
            raise RuntimeError("Human must own the session before returning control")
        self.state = HandoffState.AUTOMATION
        self.owner = ControlOwner.AUTOMATION
        self.active = None

    def complete(self) -> None:
        self.state = HandoffState.COMPLETED
        self.owner = ControlOwner.NONE

    def fail(self) -> None:
        self.state = HandoffState.FAILED
        self.owner = ControlOwner.NONE
