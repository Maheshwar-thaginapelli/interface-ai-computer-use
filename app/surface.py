from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

from app.errors import AmbiguousTarget, TargetNotFound
from app.models import ActionType, AgentDecision, BusinessOutcomeSpec, LocatorCandidate, TargetSpec


@dataclass
class Observation:
    url: str
    title: str
    text: str
    controls: list[dict[str, str]]
    state_hash: str

    def as_prompt_data(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "visible_text": self.text,
            "controls": self.controls,
        }


class Surface(Protocol):
    async def navigate(self, url: str, timeout_ms: int = 10_000) -> None: ...
    async def observe(self) -> Observation: ...
    async def execute(self, decision: AgentDecision, timeout_ms: int = 5000) -> str | None: ...
    async def recover_known_condition(self) -> str | None: ...
    async def business_outcome(self, specs: list[BusinessOutcomeSpec] | None = None) -> tuple[str, str] | None: ...
    async def intervention_reason(self) -> str | None: ...
    async def checkpoint_text_present(self, text: str) -> bool: ...
    async def checkpoint_url_contains(self, value: str) -> bool: ...
    async def screenshot(self, path: str | Path) -> str: ...
    @property
    def current_url(self) -> str: ...


class PlaywrightSurface:
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "PlaywrightSurface":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def start(self) -> None:
        if self.page:
            return
        self._playwright = await async_playwright().start()
        executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if not executable and Path("/usr/bin/chromium").exists():
            executable = "/usr/bin/chromium"
        launch_args = {"headless": self.headless}
        if executable:
            launch_args["executable_path"] = executable
        self.browser = await self._playwright.chromium.launch(**launch_args)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self._playwright = None

    def _page(self) -> Page:
        if not self.page:
            raise RuntimeError("Surface is not started")
        return self.page

    async def navigate(self, url: str, timeout_ms: int = 10_000) -> None:
        await self._page().goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    async def observe(self) -> Observation:
        page = self._page()
        title = await page.title()
        body_text = (await page.locator("body").inner_text())[:6000]
        controls: list[dict[str, str]] = []
        locators = page.locator("input, button, a, select, textarea")
        count = min(await locators.count(), 60)
        for index in range(count):
            node = locators.nth(index)
            if not await node.is_visible():
                continue
            tag = await node.evaluate("el => el.tagName.toLowerCase()")
            text = ((await node.inner_text()) if tag not in {"input", "textarea", "select"} else "").strip()
            control_id = await node.get_attribute("id") or ""
            name = await node.get_attribute("name") or ""
            aria = await node.get_attribute("aria-label") or ""
            label = ""
            if control_id:
                label_node = page.locator(f'label[for="{control_id}"]')
                if await label_node.count() == 1:
                    label = (await label_node.inner_text()).strip()
            current_value = ""
            if tag in {"input", "textarea", "select"}:
                try:
                    current_value = (await node.input_value())[:200]
                except Exception:
                    current_value = ""
            controls.append({
                "tag": tag,
                "text": text[:200],
                "id": control_id,
                "name": name,
                "label": label,
                "aria_label": aria,
                "value": current_value,
            })
        normalized = f"{page.url}\n{title}\n{body_text}\n{controls}"
        state_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
        return Observation(page.url, title, body_text, controls, state_hash)

    async def resolve_target(self, target: TargetSpec) -> Locator:
        page = self._page()
        last_error: Exception | None = None
        for candidate in target.candidates:
            try:
                locator = self._locator_for_candidate(page, candidate)
                visible_matches: list[Locator] = []
                for index in range(await locator.count()):
                    item = locator.nth(index)
                    if await item.is_visible():
                        visible_matches.append(item)
                if len(visible_matches) == 1:
                    resolved = visible_matches[0]
                    if target.expected_tag:
                        tag = await resolved.evaluate("el => el.tagName.toLowerCase()")
                        if tag != target.expected_tag.lower():
                            continue
                    return resolved
                if len(visible_matches) > 1:
                    raise AmbiguousTarget(
                        f"{target.description}: locator {candidate.strategy}:{candidate.value!r} matched {len(visible_matches)} visible elements"
                    )
            except AmbiguousTarget:
                raise
            except Exception as exc:  # a failed fallback should not block safer alternatives
                last_error = exc
        detail = f" ({last_error})" if last_error else ""
        raise TargetNotFound(f"Could not resolve target {target.description!r}{detail}")

    def _locator_for_candidate(self, page: Page, candidate: LocatorCandidate) -> Locator:
        if candidate.strategy == "role":
            return page.get_by_role(candidate.value, name=candidate.name, exact=candidate.exact)
        if candidate.strategy == "label":
            return page.get_by_label(candidate.value, exact=candidate.exact)
        if candidate.strategy == "text":
            return page.get_by_text(candidate.value, exact=candidate.exact)
        if candidate.strategy == "css":
            return page.locator(candidate.value)
        return page.locator(f"xpath={candidate.value}")

    async def execute(self, decision: AgentDecision, timeout_ms: int = 5000) -> str | None:
        page = self._page()
        action = decision.action
        if action == ActionType.NAVIGATE:
            await self.navigate(decision.value or "", timeout_ms)
            return None
        if action == ActionType.WAIT:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            return None
        if action in {ActionType.FINISH, ActionType.ESCALATE}:
            return None
        target = await self.resolve_target(decision.target)  # type: ignore[arg-type]
        if action == ActionType.CLICK:
            await target.click(timeout=timeout_ms)
            return None
        if action == ActionType.TYPE:
            await target.fill(decision.value or "", timeout=timeout_ms)
            return None
        if action == ActionType.SELECT:
            await target.select_option(decision.value or "", timeout=timeout_ms)
            return None
        if action in {ActionType.READ, ActionType.EXTRACT}:
            tag = await target.evaluate("el => el.tagName.toLowerCase()")
            if tag in {"input", "textarea", "select"}:
                return await target.input_value(timeout=timeout_ms)
            return (await target.inner_text(timeout=timeout_ms)).strip()
        raise ValueError(f"Unsupported action {action}")

    async def recover_known_condition(self) -> str | None:
        page = self._page()
        dialog = page.locator("#recoverable-dialog")
        if await dialog.count() and await dialog.is_visible():
            await page.locator("#dismiss-dialog").click()
            return "KNOWN_INTERSTITIAL_DISMISSED"
        expired = page.locator("#session-expired")
        if await expired.count() and await expired.is_visible():
            await page.locator("#restore-session").click()
            return "SESSION_RESTORED"
        return None

    async def business_outcome(self, specs: list[BusinessOutcomeSpec] | None = None) -> tuple[str, str] | None:
        page = self._page()
        if specs:
            for spec in specs:
                marker = page.locator(spec.selector)
                if await marker.count() and await marker.first.is_visible():
                    text = (await marker.first.inner_text()).strip()
                    return spec.code, text or spec.message
        marker = page.locator("[data-business-outcome]")
        if await marker.count() == 0:
            return None
        code = await marker.first.get_attribute("data-business-outcome") or "BUSINESS_OUTCOME"
        return code, (await marker.first.inner_text()).strip()

    async def intervention_reason(self) -> str | None:
        marker = self._page().locator("[data-intervention]:not([data-resolved='true'])")
        if await marker.count() and await marker.first.is_visible():
            return await marker.first.get_attribute("data-intervention") or "INTERVENTION_REQUIRED"
        return None

    async def checkpoint_text_present(self, text: str) -> bool:
        return await self._page().get_by_text(text, exact=False).count() > 0

    async def checkpoint_url_contains(self, value: str) -> bool:
        return value in self._page().url

    async def screenshot(self, path: str | Path) -> str:
        path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await self._page().screenshot(path=path, full_page=True)
        return path

    @property
    def current_url(self) -> str:
        return self._page().url
