from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.models import (
    ActionType,
    AgentDecision,
    BusinessOutcomeSpec,
    CapabilityArtifact,
    Checkpoint,
    CompatibilitySpec,
    InputSpec,
    OutputSpec,
    StepSpec,
)

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")


def interpolate(template: str | None, values: dict[str, Any]) -> str | None:
    if template is None:
        return None

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise ValueError(f"Missing required parameter {name!r}")
        return str(values[name])

    return PLACEHOLDER_RE.sub(replace, template)


def parameterize(value: str | None, parameters: dict[str, Any]) -> str | None:
    if value is None:
        return None
    result = value
    for key, concrete in sorted(parameters.items(), key=lambda item: len(str(item[1])), reverse=True):
        concrete_text = str(concrete)
        if concrete_text:
            result = result.replace(concrete_text, f"{{{{{key}}}}}")
    return result


def _parameterized_url_checkpoint(url: str, parameters: dict[str, Any]) -> str:
    parts = urlsplit(url)
    path_and_query = parts.path + (f"?{parts.query}" if parts.query else "")
    return parameterize(path_and_query, parameters) or path_and_query


def build_artifact(
    *,
    goal: str,
    application_url: str,
    decisions: list[AgentDecision],
    parameters: dict[str, Any],
    outputs: dict[str, Any],
    final_url: str,
) -> CapabilityArtifact:
    steps: list[StepSpec] = []
    for index, decision in enumerate(decisions, start=1):
        if decision.action in {ActionType.FINISH, ActionType.ESCALATE}:
            continue
        target = decision.target.model_copy(deep=True) if decision.target else None
        steps.append(
            StepSpec(
                id=f"step-{index:02d}-{decision.action.value}",
                action=decision.action,
                target=target,
                value=parameterize(decision.value, parameters),
                output_key=decision.output_key,
                expected_result=decision.expected_result,
                risk=decision.risk,
            )
        )

    if not steps or steps[0].action != ActionType.NAVIGATE:
        steps.insert(0, StepSpec(id="step-00-navigate", action=ActionType.NAVIGATE, value=application_url))

    input_specs = [
        InputSpec(name=name, type=_json_type(value), description=f"Runtime value for {name}")
        for name, value in parameters.items()
    ]
    output_specs = [
        OutputSpec(name=name, type=_json_type(value), description=f"Extracted {name}")
        for name, value in outputs.items()
    ]

    return CapabilityArtifact(
        capability_id="lookup-savings-balance",
        name="Lookup Savings Balance",
        description=goal,
        application="Legacy Bank Operations Demo",
        compatibility=CompatibilitySpec(application_family="legacy-bank-demo", application_version="demo-v1"),
        inputs=input_specs,
        outputs=output_specs,
        steps=steps,
        checkpoint=Checkpoint(type="url_contains", value=_parameterized_url_checkpoint(final_url, parameters)),
        business_outcomes=[
            BusinessOutcomeSpec(
                code="MEMBER_NOT_FOUND",
                selector="[data-business-outcome='MEMBER_NOT_FOUND']",
                message="No member exists for the supplied identifier.",
            )
        ],
        metadata={"generated_from": "llm_discovery", "parameter_names": list(parameters)},
    )


def save_artifact(artifact: CapabilityArtifact, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    return target


def load_artifact(path: str | Path) -> CapabilityArtifact:
    return CapabilityArtifact.model_validate_json(Path(path).read_text(encoding="utf-8"))


def validate_inputs(artifact: CapabilityArtifact, values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for spec in artifact.inputs:
        if spec.required and spec.name not in values:
            raise ValueError(f"Missing required input {spec.name!r}")
        if spec.name not in values:
            continue
        normalized[spec.name] = _coerce(values[spec.name], spec.type)
    extras = set(values) - {spec.name for spec in artifact.inputs}
    if extras:
        raise ValueError(f"Unexpected inputs: {', '.join(sorted(extras))}")
    return normalized


def _coerce(value: Any, type_name: str) -> Any:
    if type_name == "string":
        return str(value)
    if type_name == "integer":
        if isinstance(value, bool):
            raise ValueError("boolean is not an integer input")
        return int(value)
    if type_name == "number":
        if isinstance(value, bool):
            raise ValueError("boolean is not a number input")
        return float(value)
    if type_name == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        raise ValueError(f"Cannot coerce {value!r} to boolean")
    raise ValueError(f"Unsupported type {type_name!r}")


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"
