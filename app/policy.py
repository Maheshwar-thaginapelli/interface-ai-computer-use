from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.errors import PolicyViolation
from app.models import ActionType, AgentDecision, RiskLevel, StepSpec


@dataclass(frozen=True)
class Policy:
    allowed_hosts: set[str] = field(default_factory=lambda: {"127.0.0.1", "localhost"})
    allowed_actions: set[ActionType] = field(default_factory=lambda: set(ActionType))
    require_human_for: set[RiskLevel] = field(default_factory=lambda: {RiskLevel.RISKY, RiskLevel.IRREVERSIBLE})

    def validate_url(self, url: str) -> None:
        host = urlparse(url).hostname
        if host not in self.allowed_hosts:
            raise PolicyViolation(f"Host {host!r} is not allowlisted")

    def validate_decision(self, decision: AgentDecision) -> None:
        self._validate_action(decision.action)
        if decision.action == ActionType.NAVIGATE and decision.value:
            self.validate_url(decision.value)

    def validate_step(self, step: StepSpec) -> None:
        self._validate_action(step.action)
        if step.action == ActionType.NAVIGATE and step.value:
            self.validate_url(step.value)

    def requires_human(self, risk: RiskLevel) -> bool:
        return risk in self.require_human_for

    def _validate_action(self, action: ActionType) -> None:
        if action not in self.allowed_actions:
            raise PolicyViolation(f"Action {action.value!r} is not permitted")
