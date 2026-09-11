from __future__ import annotations

import pytest

from app.capability import build_artifact
from app.models import ActionType, AgentDecision, LocatorCandidate, TargetSpec
from app.surface import PlaywrightSurface

pytestmark = pytest.mark.asyncio


async def test_playwright_surface_ranked_locators_and_extract() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        assert surface.page is not None
        await surface.page.set_content(
            """
            <html><head><title>Fixture</title></head><body>
              <label for='member'>Member ID</label>
              <input id='member'>
              <button id='go'>Search Member</button>
              <div id='balance'>4621.77</div>
            </body></html>
            """
        )
        await surface.execute(
            AgentDecision(
                reason_summary="enter member",
                action=ActionType.TYPE,
                target=TargetSpec(
                    description="member input",
                    candidates=[
                        LocatorCandidate(strategy="label", value="Member ID"),
                        LocatorCandidate(strategy="css", value="#member"),
                    ],
                ),
                value="12345",
            )
        )
        value = await surface.execute(
            AgentDecision(
                reason_summary="read balance",
                action=ActionType.EXTRACT,
                target=TargetSpec(
                    description="balance",
                    candidates=[LocatorCandidate(strategy="css", value="#balance")],
                ),
                output_key="savings_balance",
            )
        )
        assert await surface.page.locator("#member").input_value() == "12345"
        assert value == "4621.77"


@pytest.mark.asyncio
async def test_observation_exposes_legacy_table_data_fields() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
            </table>
            """
        )
        observation = await surface.observe()
        assert {
            "label": "Current Savings Balance",
            "value": "4621.77",
            "selector": "#savings-balance",
        } in observation.data_fields


@pytest.mark.asyncio
async def test_extract_falls_back_to_legacy_label_value_row() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table>
              <tr><th>Member ID</th><td>12345</td></tr>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
            </table>
            """
        )
        decision = AgentDecision(
            reason_summary="Extract requested balance",
            action=ActionType.EXTRACT,
            target=TargetSpec(
                description="Current savings balance for member 12345",
                candidates=[LocatorCandidate(strategy="text", value="Current savings balance for member 12345")],
            ),
            output_key="savings_balance",
        )
        result = await surface.execute(decision)
        assert result == "4621.77"

@pytest.mark.asyncio
async def test_extract_semantic_legacy_row_match_handles_natural_model_phrase() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table>
              <tr><th>Member ID</th><td>12345</td></tr>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
              <tr><th>Checking Balance</th><td>120.00</td></tr>
            </table>
            """
        )
        decision = AgentDecision(
            reason_summary="Extract visible savings balance",
            action=ActionType.EXTRACT,
            target=TargetSpec(
                description="Savings balance value for member 12345",
                candidates=[LocatorCandidate(strategy="text", value="Savings balance value for member 12345")],
            ),
            output_key="savings_balance",
        )
        result = await surface.execute(decision)
        assert result == "4621.77"
        assert decision.target is not None
        assert decision.target.description == "Current Savings Balance"
        assert decision.target.candidates[0].strategy == "css"
        assert decision.target.candidates[0].value == "#savings-balance"


@pytest.mark.asyncio
async def test_extract_uses_output_contract_when_model_description_is_truncated() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table>
              <tr><th>Member ID</th><td>12345</td></tr>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
              <tr><th>Checking Balance</th><td id='checking-balance'>1245.60</td></tr>
            </table>
            """
        )
        decision = AgentDecision(
            reason_summary="Extract savings",
            action=ActionType.EXTRACT,
            target=TargetSpec(
                description="Savings balance v",
                candidates=[LocatorCandidate(strategy="text", value="Savings balance v")],
            ),
            output_key="savings_balance",
        )
        result = await surface.execute(decision)
        assert result == "4621.77"
        assert decision.target is not None
        assert decision.target.candidates[0].value == "#savings-balance"


@pytest.mark.asyncio
async def test_click_does_not_use_semantic_table_value_fallback() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table><tr><th>Current Savings Balance</th><td>4621.77</td></tr></table>
            """
        )
        decision = AgentDecision(
            reason_summary="Click nonexistent control",
            action=ActionType.CLICK,
            target=TargetSpec(
                description="Savings balance value",
                candidates=[LocatorCandidate(strategy="text", value="Not a real button")],
            ),
        )
        from app.errors import TargetNotFound
        with pytest.raises(TargetNotFound):
            await surface.execute(decision)


@pytest.mark.asyncio
async def test_repaired_extract_target_is_recorded_in_generated_artifact() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <table>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
            </table>
            """
        )
        decision = AgentDecision(
            reason_summary="Extract savings",
            action=ActionType.EXTRACT,
            target=TargetSpec(
                description="Savings balance v",
                candidates=[LocatorCandidate(strategy="text", value="Savings balance v")],
            ),
            output_key="savings_balance",
        )
        value = await surface.execute(decision)
        artifact = build_artifact(
            goal="Look up member 12345 and return their current savings balance",
            application_url="http://127.0.0.1:8000",
            decisions=[decision],
            parameters={"member_id": "12345"},
            outputs={"savings_balance": value},
            final_url="http://127.0.0.1:8000/member/12345/savings",
        )
        extract_step = next(step for step in artifact.steps if step.action == ActionType.EXTRACT)
        assert extract_step.target is not None
        assert extract_step.target.candidates[0].strategy == "css"
        assert extract_step.target.candidates[0].value == "#savings-balance"
        assert artifact.metadata["generated_from"] == "llm_discovery"

@pytest.mark.asyncio
async def test_extract_recovers_from_ambiguous_text_candidate_using_output_contract() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <h2>Savings</h2>
            <table>
              <tr><th>Current Savings Balance</th><td id='savings-balance'>4621.77</td></tr>
              <tr><th>Checking Balance</th><td id='checking-balance'>1245.60</td></tr>
            </table>
            <a href='#'>Savings</a>
            """
        )
        decision = AgentDecision(
            reason_summary="Extract current savings balance",
            action=ActionType.EXTRACT,
            target=TargetSpec(
                description="Current savings balance for member 12345",
                candidates=[LocatorCandidate(strategy="text", value="Savings", exact=True)],
            ),
            output_key="savings_balance",
        )
        result = await surface.execute(decision)
        assert result == "4621.77"
        assert decision.target is not None
        assert decision.target.candidates[0].strategy == "css"
        assert decision.target.candidates[0].value == "#savings-balance"


@pytest.mark.asyncio
async def test_ambiguous_click_remains_blocked() -> None:
    async with PlaywrightSurface(headless=True) as surface:
        await surface._page().set_content(
            """
            <button>Savings</button>
            <button>Savings</button>
            """
        )
        decision = AgentDecision(
            reason_summary="Click savings",
            action=ActionType.CLICK,
            target=TargetSpec(
                description="Savings button",
                candidates=[LocatorCandidate(strategy="text", value="Savings", exact=True)],
            ),
        )
        from app.errors import AmbiguousTarget
        with pytest.raises(AmbiguousTarget):
            await surface.execute(decision)
