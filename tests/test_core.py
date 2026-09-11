from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.capability import interpolate, parameterize, validate_inputs
from app.errors import PolicyViolation
from app.handoff import HandoffController, HandoffState, Intervention
from app.models import ActionType, AgentDecision, ControlOwner, LocatorCandidate, RiskLevel, StepSpec, TargetSpec
from app.policy import Policy
from app.redaction import redact


def test_interpolation_and_parameterization() -> None:
    assert parameterize("/member/12345/savings", {"member_id": "12345"}) == "/member/{{member_id}}/savings"
    assert interpolate("/member/{{member_id}}/savings", {"member_id": "22222"}) == "/member/22222/savings"


def test_missing_interpolation_value_fails() -> None:
    with pytest.raises(ValueError, match="member_id"):
        interpolate("{{member_id}}", {})


def test_validate_inputs(sample_artifact) -> None:
    assert validate_inputs(sample_artifact, {"member_id": 12345}) == {"member_id": "12345"}
    with pytest.raises(ValueError, match="Unexpected inputs"):
        validate_inputs(sample_artifact, {"member_id": "1", "extra": "x"})


def test_sensitive_fields_are_redacted_recursively() -> None:
    source = {"user": "demo", "api_key": "abc", "nested": {"Authorization": "Bearer secret", "ok": 3}}
    assert redact(source) == {"user": "demo", "api_key": "[REDACTED]", "nested": {"Authorization": "[REDACTED]", "ok": 3}}


def test_external_navigation_is_blocked() -> None:
    policy = Policy()
    step = StepSpec(id="bad", action=ActionType.NAVIGATE, value="https://example.com")
    with pytest.raises(PolicyViolation):
        policy.validate_step(step)


def test_risky_action_requires_human() -> None:
    assert Policy().requires_human(RiskLevel.RISKY)
    assert not Policy().requires_human(RiskLevel.SAFE)


def test_agent_decision_requires_target_for_click() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(reason_summary="click it", action=ActionType.CLICK)


def test_handoff_state_transitions() -> None:
    controller = HandoffController()
    intervention = Intervention("run-1", "needs approval", "step-2", None, "http://127.0.0.1")
    controller.request(intervention)
    assert controller.state == HandoffState.PAUSED_FOR_HUMAN
    assert controller.owner == ControlOwner.NONE
    controller.take_control()
    assert controller.owner == ControlOwner.HUMAN
    controller.resume_automation()
    assert controller.state == HandoffState.AUTOMATION
    assert controller.owner == ControlOwner.AUTOMATION


def test_target_schema_supports_ranked_fallbacks() -> None:
    target = TargetSpec(
        description="member",
        candidates=[
            LocatorCandidate(strategy="label", value="Member ID"),
            LocatorCandidate(strategy="css", value="#mid"),
        ],
    )
    assert [item.strategy for item in target.candidates] == ["label", "css"]
