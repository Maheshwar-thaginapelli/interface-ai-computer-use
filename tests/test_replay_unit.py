from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import TargetNotFound
from app.handoff import HandoffController, HandoffState
from app.models import RunStatus
from app.policy import Policy
from app.replay import ReplayEngine

pytestmark = pytest.mark.asyncio


class FakeSurface:
    def __init__(self, *, outcome=None, intervention=None, fail_step=None, checkpoint=True):
        self.url = "about:blank"
        self.outcome = outcome
        self.intervention = intervention
        self.fail_step = fail_step
        self.checkpoint = checkpoint
        self.current_step = None
        self.calls = []
        self.recovered_once = False

    @property
    def current_url(self):
        return self.url

    async def execute(self, decision, timeout_ms=5000):
        self.current_step = decision.reason_summary.split()[-1]
        self.calls.append((decision.action.value, decision.value, decision.output_key))
        if self.fail_step and self.fail_step in decision.reason_summary:
            raise TargetNotFound("simulated missing target")
        if decision.action.value == "navigate":
            self.url = decision.value
            return None
        if decision.action.value == "type":
            return None
        if decision.action.value == "click":
            if "search" in decision.reason_summary:
                self.url = self.url.rstrip("/") + "/member?member_id=12345"
            if "view-savings" in decision.reason_summary:
                self.url = self.url.split("/member?")[0] + "/member/12345/savings"
            return None
        if decision.action.value == "extract":
            return "4621.77"
        return None

    async def recover_known_condition(self):
        if not self.recovered_once and any(call[0] == "click" for call in self.calls):
            self.recovered_once = True
            return "SIMULATED_RECOVERY"
        return None

    async def business_outcome(self, specs=None):
        if self.outcome and any(call[0] == "click" for call in self.calls):
            return self.outcome
        return None

    async def intervention_reason(self):
        if self.intervention and any(call[0] == "click" for call in self.calls):
            return self.intervention
        return None

    async def checkpoint_text_present(self, text):
        return self.checkpoint

    async def checkpoint_url_contains(self, value):
        return self.checkpoint

    async def screenshot(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        return str(path)


async def test_replay_engine_success_without_llm(sample_artifact, tmp_path: Path) -> None:
    surface = FakeSurface()
    result = await ReplayEngine(Policy()).run(
        artifact=sample_artifact,
        inputs={"member_id": "12345"},
        surface=surface,  # type: ignore[arg-type]
        evidence_dir=tmp_path,
    )
    assert result.status == RunStatus.SUCCESS
    assert result.outputs == {"savings_balance": "4621.77"}
    assert "SIMULATED_RECOVERY" in result.recovered_conditions


async def test_replay_engine_business_outcome(sample_artifact, tmp_path: Path) -> None:
    surface = FakeSurface(outcome=("MEMBER_NOT_FOUND", "No member exists"))
    result = await ReplayEngine(Policy()).run(
        artifact=sample_artifact,
        inputs={"member_id": "99999"},
        surface=surface,  # type: ignore[arg-type]
        evidence_dir=tmp_path,
    )
    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.business_code == "MEMBER_NOT_FOUND"


async def test_replay_engine_returns_structured_hard_failure(sample_artifact, tmp_path: Path) -> None:
    surface = FakeSurface(fail_step="view-savings")
    result = await ReplayEngine(Policy()).run(
        artifact=sample_artifact,
        inputs={"member_id": "12345"},
        surface=surface,  # type: ignore[arg-type]
        evidence_dir=tmp_path,
    )
    assert result.status == RunStatus.FAILURE
    assert result.error is not None
    assert result.error.code == "TARGET_NOT_FOUND"
    assert result.error.step_id == "view-savings"


async def test_checkpoint_failure_is_structured(sample_artifact, tmp_path: Path) -> None:
    surface = FakeSurface(checkpoint=False)
    result = await ReplayEngine(Policy()).run(
        artifact=sample_artifact,
        inputs={"member_id": "12345"},
        surface=surface,  # type: ignore[arg-type]
        evidence_dir=tmp_path,
    )
    assert result.status == RunStatus.FAILURE
    assert result.error is not None
    assert result.error.code == "CHECKPOINT_FAILED"


async def test_replay_handoff_pauses_and_preserves_controller_state(sample_artifact, tmp_path: Path) -> None:
    controller = HandoffController()
    surface = FakeSurface(intervention="PERMISSION_REQUIRED")
    result = await ReplayEngine(Policy()).run(
        artifact=sample_artifact,
        inputs={"member_id": "70000"},
        surface=surface,  # type: ignore[arg-type]
        evidence_dir=tmp_path,
        handoff=controller,
    )
    assert result.status == RunStatus.PAUSED
    assert result.intervention_id
    assert controller.state == HandoffState.PAUSED_FOR_HUMAN
