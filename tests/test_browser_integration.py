from __future__ import annotations

from pathlib import Path

import pytest

from app.agent import DiscoveryAgent
from app.handoff import HandoffController, HandoffState
from app.llm import MockLLMProvider
from app.models import ActionType, AgentDecision, LocatorCandidate, RunStatus, TargetSpec
from app.policy import Policy
from app.replay import ReplayEngine
from app.surface import PlaywrightSurface

pytestmark = pytest.mark.asyncio


async def _require_local_navigation(surface: PlaywrightSurface, base_url: str) -> None:
    try:
        await surface.navigate(base_url)
    except Exception as exc:
        if "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc):
            pytest.skip("Managed Chromium policy blocks local HTTP navigation in this environment")
        raise


async def test_deterministic_replay_success(sample_artifact, demo_server: str, tmp_path: Path) -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await _require_local_navigation(surface, demo_server)
        result = await ReplayEngine(Policy()).run(
            artifact=sample_artifact,
            inputs={"member_id": "12345"},
            surface=surface,
            evidence_dir=tmp_path / "success",
        )
    assert result.status == RunStatus.SUCCESS
    assert result.outputs["savings_balance"] == "4621.77"


async def test_not_found_is_business_outcome(sample_artifact, demo_server: str, tmp_path: Path) -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await _require_local_navigation(surface, demo_server)
        result = await ReplayEngine(Policy()).run(
            artifact=sample_artifact,
            inputs={"member_id": "99999"},
            surface=surface,
            evidence_dir=tmp_path / "not-found",
        )
    assert result.status == RunStatus.BUSINESS_OUTCOME
    assert result.business_code == "MEMBER_NOT_FOUND"


async def test_known_dialog_is_recovered(sample_artifact, demo_server: str, tmp_path: Path) -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await _require_local_navigation(surface, demo_server)
        result = await ReplayEngine(Policy()).run(
            artifact=sample_artifact,
            inputs={"member_id": "55555"},
            surface=surface,
            evidence_dir=tmp_path / "recovered",
        )
    assert result.status == RunStatus.SUCCESS
    assert "KNOWN_INTERSTITIAL_DISMISSED" in result.recovered_conditions
    assert result.outputs["savings_balance"] == "300.00"


async def test_permission_condition_pauses_same_live_session(sample_artifact, demo_server: str, tmp_path: Path) -> None:
    handoff = HandoffController()
    async with PlaywrightSurface(headless=True) as surface:
        await _require_local_navigation(surface, demo_server)
        result = await ReplayEngine(Policy()).run(
            artifact=sample_artifact,
            inputs={"member_id": "70000"},
            surface=surface,
            evidence_dir=tmp_path / "handoff",
            handoff=handoff,
        )
        assert result.status == RunStatus.PAUSED
        assert handoff.state == HandoffState.PAUSED_FOR_HUMAN
        assert "/member?member_id=70000" in surface.current_url
        assert surface.page is not None and not surface.page.is_closed()


async def test_mock_discovery_creates_parameterized_artifact(demo_server: str, tmp_path: Path) -> None:
    decisions = [
        AgentDecision(
            reason_summary="Enter the member ID.",
            action=ActionType.TYPE,
            target=TargetSpec(description="Member ID", candidates=[LocatorCandidate(strategy="label", value="Member ID")]),
            value="12345",
        ),
        AgentDecision(
            reason_summary="Submit the member search.",
            action=ActionType.CLICK,
            target=TargetSpec(description="Search", candidates=[LocatorCandidate(strategy="role", value="button", name="Search Member")]),
        ),
        AgentDecision(
            reason_summary="Open the savings account.",
            action=ActionType.CLICK,
            target=TargetSpec(description="View Savings", candidates=[LocatorCandidate(strategy="role", value="link", name="View Savings")]),
        ),
        AgentDecision(
            reason_summary="Extract the requested balance.",
            action=ActionType.EXTRACT,
            target=TargetSpec(description="Savings balance", candidates=[LocatorCandidate(strategy="css", value="#savings-balance")]),
            output_key="savings_balance",
        ),
        AgentDecision(reason_summary="The requested balance was extracted.", action=ActionType.FINISH),
    ]
    provider = MockLLMProvider(decisions)
    artifact_path = tmp_path / "capability.json"
    async with PlaywrightSurface(headless=True) as surface:
        await _require_local_navigation(surface, demo_server)
        result = await DiscoveryAgent(provider, Policy()).run(
            goal="Look up member 12345 and return their savings balance",
            target_url=demo_server,
            surface=surface,
            parameters={"member_id": "12345"},
            artifact_path=artifact_path,
            evidence_dir=tmp_path / "discovery",
        )
    assert result.outputs == {"savings_balance": "4621.77"}
    text = artifact_path.read_text()
    assert "{{member_id}}" in text
    assert '"generated_from": "llm_discovery"' in text
