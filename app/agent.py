from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.capability import build_artifact, save_artifact
from app.handoff import HandoffController, Intervention
from app.llm import LLMProvider
from app.models import ActionType, AgentDecision, CapabilityArtifact
from app.observability import RunLogger
from app.policy import Policy
from app.surface import Surface


@dataclass
class DiscoveryResult:
    run_id: str
    artifact: CapabilityArtifact
    outputs: dict[str, str]
    steps: int


class DiscoveryAgent:
    def __init__(
        self,
        provider: LLMProvider,
        policy: Policy,
        *,
        max_steps: int = 15,
        repeat_limit: int = 3,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.max_steps = max_steps
        self.repeat_limit = repeat_limit

    async def run(
        self,
        *,
        goal: str,
        target_url: str,
        surface: Surface,
        parameters: dict[str, str],
        artifact_path: str | Path,
        evidence_dir: str | Path,
        handoff: HandoffController | None = None,
        interactive_handoff: bool = False,
    ) -> DiscoveryResult:
        self.policy.validate_url(target_url)
        run_id = str(uuid4())
        evidence_dir = Path(evidence_dir)
        logger = RunLogger(evidence_dir / "run.jsonl", run_id, "discovery")
        handoff = handoff or HandoffController()
        decisions: list[AgentDecision] = []
        outputs: dict[str, str] = {}
        seen: dict[str, int] = {}

        await surface.navigate(target_url)
        logger.emit("navigation", url=target_url)

        for step_number in range(1, self.max_steps + 1):
            recovered = await surface.recover_known_condition()
            if recovered:
                logger.emit("recovered_condition", condition=recovered)

            outcome = await surface.business_outcome()
            if outcome:
                code, message = outcome
                logger.emit("business_outcome", code=code, message=message)
                raise RuntimeError(f"Discovery ended with business outcome {code}: {message}")

            intervention_reason = await surface.intervention_reason()
            if intervention_reason:
                resumed = await self._handoff(
                    run_id=run_id,
                    step_id=f"discovery-{step_number}",
                    reason=intervention_reason,
                    surface=surface,
                    evidence_dir=evidence_dir,
                    logger=logger,
                    controller=handoff,
                    interactive=interactive_handoff,
                )
                if not resumed:
                    raise RuntimeError(
                        f"Discovery paused for human intervention {handoff.active.id if handoff.active else 'unknown'}"
                    )
                seen.clear()
                continue

            observation = await surface.observe()
            seen[observation.state_hash] = seen.get(observation.state_hash, 0) + 1
            if seen[observation.state_hash] >= self.repeat_limit:
                resumed = await self._handoff(
                    run_id=run_id,
                    step_id=f"discovery-{step_number}",
                    reason="REPEATED_STATE",
                    surface=surface,
                    evidence_dir=evidence_dir,
                    logger=logger,
                    controller=handoff,
                    interactive=interactive_handoff,
                )
                if not resumed:
                    raise RuntimeError(
                        f"Discovery stuck; intervention {handoff.active.id if handoff.active else 'unknown'} created"
                    )
                seen.clear()
                continue

            decision = await self.provider.decide(goal, observation, step_number)
            self.policy.validate_decision(decision)
            logger.emit(
                "agent_decision",
                step_id=f"discovery-{step_number}",
                action=decision.action.value,
                reason_summary=decision.reason_summary,
                risk=decision.risk.value,
            )

            if self.policy.requires_human(decision.risk) or decision.action == ActionType.ESCALATE:
                resumed = await self._handoff(
                    run_id=run_id,
                    step_id=f"discovery-{step_number}",
                    reason=decision.reason_summary,
                    surface=surface,
                    evidence_dir=evidence_dir,
                    logger=logger,
                    controller=handoff,
                    interactive=interactive_handoff,
                )
                if not resumed:
                    raise RuntimeError(
                        f"Discovery paused for human intervention {handoff.active.id if handoff.active else 'unknown'}"
                    )
                if decision.action != ActionType.ESCALATE:
                    decisions.append(decision)
                seen.clear()
                continue

            if decision.action == ActionType.FINISH:
                if not outputs:
                    raise RuntimeError("Model attempted to finish without extracting any output")
                decisions.append(decision)
                artifact = build_artifact(
                    goal=goal,
                    application_url=target_url,
                    decisions=decisions,
                    parameters=parameters,
                    outputs=outputs,
                    final_url=surface.current_url,
                )
                save_artifact(artifact, artifact_path)
                await surface.screenshot(evidence_dir / "final.png")
                logger.emit("discovery_complete", artifact_path=str(artifact_path), outputs=outputs)
                handoff.complete()
                return DiscoveryResult(run_id, artifact, outputs, step_number)

            result = await surface.execute(decision)
            decisions.append(decision)
            if decision.action == ActionType.EXTRACT and decision.output_key:
                outputs[decision.output_key] = result or ""
                logger.emit("output_extracted", key=decision.output_key, value=result)

        shot = await surface.screenshot(evidence_dir / "max-steps.png")
        intervention = handoff.request(Intervention(run_id, "MAX_STEPS", None, shot, surface.current_url))
        logger.emit("human_intervention_requested", intervention_id=intervention.id, reason="MAX_STEPS")
        raise RuntimeError(f"Discovery exceeded max steps; intervention {intervention.id} created")

    async def _handoff(
        self,
        *,
        run_id: str,
        step_id: str,
        reason: str,
        surface: Surface,
        evidence_dir: Path,
        logger: RunLogger,
        controller: HandoffController,
        interactive: bool,
    ) -> bool:
        shot = await surface.screenshot(evidence_dir / f"handoff-{step_id}.png")
        intervention = controller.request(Intervention(run_id, reason, step_id, shot, surface.current_url))
        logger.emit(
            "human_intervention_requested",
            intervention_id=intervention.id,
            step_id=step_id,
            reason=reason,
            control_owner=controller.owner.value,
        )
        if not interactive:
            return False
        controller.take_control()
        logger.emit("human_control_started", intervention_id=intervention.id, step_id=step_id, control_owner="human")
        await asyncio.to_thread(
            input,
            "Human control is active in the SAME browser session. Resolve/perform the blocked action, then press Enter: ",
        )
        controller.resume_automation()
        logger.emit("automation_resumed", intervention_id=intervention.id, step_id=step_id, control_owner="automation")
        return True
