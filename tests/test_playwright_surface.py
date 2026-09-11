from __future__ import annotations

import pytest

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
