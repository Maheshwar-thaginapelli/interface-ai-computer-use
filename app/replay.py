from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.capability import interpolate, validate_inputs
from app.errors import AmbiguousTarget, AutomationError, CheckpointFailed, PolicyViolation, TargetNotFound
from app.handoff import HandoffController, Intervention
from app.models import AgentDecision, CapabilityArtifact, RunError, RunResult, RunStatus, StepSpec
from app.observability import RunLogger
from app.policy import Policy
from app.surface import Surface


class ReplayEngine:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    async def run(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[str, object],
        surface: Surface,
        evidence_dir: str | Path,
        handoff: HandoffController | None = None,
        interactive_handoff: bool = False,
    ) -> RunResult:
        run_id = str(uuid4())
        evidence_dir = Path(evidence_dir)
        logger = RunLogger(evidence_dir / "run.jsonl", run_id, "replay")
        handoff = handoff or HandoffController()
        recovered_conditions: list[str] = []
        outputs: dict[str, str] = {}

        try:
            values = validate_inputs(artifact, inputs)
        except Exception as exc:
            return self._failure(run_id, "INPUT_VALIDATION", str(exc))

        for step in artifact.steps:
            concrete = self._materialize_step(step, values)
            try:
                self.policy.validate_step(concrete)
            except PolicyViolation as exc:
                logger.emit("policy_block", step_id=step.id, message=str(exc))
                return self._failure(run_id, exc.code, str(exc), step_id=step.id)

            if self.policy.requires_human(concrete.risk):
                paused = await self._handoff(
                    run_id=run_id,
                    step=concrete,
                    reason=f"Risk gate: {concrete.risk.value}",
                    surface=surface,
                    evidence_dir=evidence_dir,
                    logger=logger,
                    controller=handoff,
                    interactive=interactive_handoff,
                    human_handles_step=True,
                )
                if paused:
                    return RunResult(
                        status=RunStatus.PAUSED,
                        run_id=run_id,
                        recovered_conditions=recovered_conditions,
                        intervention_id=handoff.active.id if handoff.active else None,
                        message="Automation paused for human control.",
                    )
                continue

            try:
                result = await self._execute_with_retry(concrete, surface, logger)
            except Exception as exc:
                shot = await surface.screenshot(evidence_dir / f"failure-{step.id}.png")
                code = exc.code if isinstance(exc, AutomationError) else "STEP_EXECUTION_FAILED"
                logger.emit(
                    "replay_failure",
                    step_id=step.id,
                    code=code,
                    message=str(exc),
                    evidence=shot,
                )
                handoff.fail()
                return self._failure(run_id, code, str(exc), step_id=step.id, evidence=shot)
            if concrete.output_key and result is not None:
                outputs[concrete.output_key] = result
                logger.emit("output_extracted", step_id=step.id, key=concrete.output_key, value=result)

            recovered = await surface.recover_known_condition()
            if recovered:
                recovered_conditions.append(recovered)
                logger.emit("recovered_condition", step_id=step.id, condition=recovered)

            outcome = await surface.business_outcome(artifact.business_outcomes)
            if outcome:
                code, message = outcome
                await surface.screenshot(evidence_dir / "business-outcome.png")
                logger.emit("business_outcome", step_id=step.id, code=code, message=message)
                handoff.complete()
                return RunResult(
                    status=RunStatus.BUSINESS_OUTCOME,
                    run_id=run_id,
                    business_code=code,
                    message=message,
                    recovered_conditions=recovered_conditions,
                )

            intervention_reason = await surface.intervention_reason()
            if intervention_reason:
                paused = await self._handoff(
                    run_id=run_id,
                    step=concrete,
                    reason=intervention_reason,
                    surface=surface,
                    evidence_dir=evidence_dir,
                    logger=logger,
                    controller=handoff,
                    interactive=interactive_handoff,
                    human_handles_step=False,
                )
                if paused:
                    return RunResult(
                        status=RunStatus.PAUSED,
                        run_id=run_id,
                        recovered_conditions=recovered_conditions,
                        intervention_id=handoff.active.id if handoff.active else None,
                        message="Automation paused for human control.",
                    )

        try:
            await self._verify_checkpoint(artifact, values, surface)
            self._validate_outputs(artifact, outputs)
        except Exception as exc:
            shot = await surface.screenshot(evidence_dir / "failure.png")
            code = exc.code if isinstance(exc, AutomationError) else "OUTPUT_VALIDATION"
            logger.emit("replay_failure", code=code, message=str(exc), evidence=shot)
            handoff.fail()
            return self._failure(run_id, code, str(exc), evidence=shot)

        await surface.screenshot(evidence_dir / "final.png")
        logger.emit("replay_complete", outputs=outputs, recovered_conditions=recovered_conditions)
        handoff.complete()
        return RunResult(
            status=RunStatus.SUCCESS,
            run_id=run_id,
            outputs=outputs,
            recovered_conditions=recovered_conditions,
        )

    async def _execute_with_retry(
        self,
        step: StepSpec,
        surface: Surface,
        logger: RunLogger,
    ) -> str | RunResult | None:
        decision = AgentDecision(
            reason_summary=f"Deterministic replay of {step.id}",
            action=step.action,
            target=step.target,
            value=step.value,
            expected_result=step.expected_result,
            output_key=step.output_key,
            risk=step.risk,
            confidence=1.0,
        )
        last_exc: Exception | None = None
        for attempt in range(1, step.retry.max_attempts + 1):
            started = perf_counter()
            try:
                result = await surface.execute(decision, timeout_ms=step.timeout_ms)
                logger.emit(
                    "step_success",
                    step_id=step.id,
                    action=step.action.value,
                    attempt=attempt,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return result
            except AmbiguousTarget:
                raise
            except (TargetNotFound, PlaywrightTimeoutError) as exc:
                last_exc = exc
                logger.emit(
                    "step_retry",
                    step_id=step.id,
                    action=step.action.value,
                    attempt=attempt,
                    message=str(exc),
                )
                if attempt < step.retry.max_attempts:
                    await asyncio.sleep(step.retry.backoff_ms / 1000)
        if last_exc:
            raise last_exc
        return None

    async def _handoff(
        self,
        *,
        run_id: str,
        step: StepSpec,
        reason: str,
        surface: Surface,
        evidence_dir: Path,
        logger: RunLogger,
        controller: HandoffController,
        interactive: bool,
        human_handles_step: bool,
    ) -> bool:
        shot = await surface.screenshot(evidence_dir / f"handoff-{step.id}.png")
        intervention = controller.request(Intervention(run_id, reason, step.id, shot, surface.current_url))
        logger.emit(
            "human_intervention_requested",
            step_id=step.id,
            intervention_id=intervention.id,
            reason=reason,
            control_owner=controller.owner.value,
        )
        if not interactive:
            return True

        controller.take_control()
        logger.emit("human_control_started", step_id=step.id, intervention_id=intervention.id, control_owner="human")
        instruction = (
            "Human control is active in the SAME browser session. "
            + ("Perform/approve the gated step manually. " if human_handles_step else "Resolve the visible blocking condition. ")
            + "Press Enter here when finished: "
        )
        await asyncio.to_thread(input, instruction)
        controller.resume_automation()
        logger.emit("automation_resumed", step_id=step.id, intervention_id=intervention.id, control_owner="automation")
        if not human_handles_step and await surface.intervention_reason():
            raise CheckpointFailed("Human returned control but the blocking condition is still present")
        return False

    async def _verify_checkpoint(
        self,
        artifact: CapabilityArtifact,
        values: dict[str, object],
        surface: Surface,
    ) -> None:
        expected = interpolate(artifact.checkpoint.value, values) or ""
        if artifact.checkpoint.type == "text_present":
            passed = await surface.checkpoint_text_present(expected)
        else:
            passed = await surface.checkpoint_url_contains(expected)
        if not passed:
            raise CheckpointFailed(f"Checkpoint failed: expected {artifact.checkpoint.type}={expected!r}")

    def _materialize_step(self, step: StepSpec, values: dict[str, object]) -> StepSpec:
        concrete = step.model_copy(deep=True)
        concrete.value = interpolate(concrete.value, values)
        if concrete.target:
            concrete.target.description = interpolate(concrete.target.description, values) or concrete.target.description
            for candidate in concrete.target.candidates:
                candidate.value = interpolate(candidate.value, values) or candidate.value
                candidate.name = interpolate(candidate.name, values)
        return concrete

    def _validate_outputs(self, artifact: CapabilityArtifact, outputs: dict[str, str]) -> None:
        missing = [spec.name for spec in artifact.outputs if spec.name not in outputs]
        if missing:
            raise ValueError(f"Missing declared outputs: {', '.join(missing)}")
        for spec in artifact.outputs:
            value = outputs[spec.name]
            if spec.type == "integer":
                int(value)
            elif spec.type == "number":
                float(value)
            elif spec.type == "boolean" and value.lower() not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"Output {spec.name!r} is not a boolean")

    def _failure(
        self,
        run_id: str,
        code: str,
        message: str,
        *,
        step_id: str | None = None,
        evidence: str | None = None,
    ) -> RunResult:
        return RunResult(
            status=RunStatus.FAILURE,
            run_id=run_id,
            error=RunError(code=code, message=message, step_id=step_id, evidence=evidence),
        )
