from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    READ = "read"
    EXTRACT = "extract"
    WAIT = "wait"
    FINISH = "finish"
    ESCALATE = "escalate"


class RiskLevel(str, Enum):
    SAFE = "safe"
    REVERSIBLE = "reversible"
    RISKY = "risky"
    IRREVERSIBLE = "irreversible"


class ControlOwner(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"
    NONE = "none"


class RunStatus(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    FAILURE = "failure"
    PAUSED = "paused"


class LocatorCandidate(BaseModel):
    strategy: Literal["role", "label", "text", "css", "xpath"]
    value: str
    name: str | None = None
    exact: bool = True


class TargetSpec(BaseModel):
    description: str
    candidates: list[LocatorCandidate] = Field(min_length=1)
    expected_tag: str | None = None
    robustness_note: str = ""


class AgentDecision(BaseModel):
    reason_summary: str = Field(max_length=400)
    action: ActionType
    target: TargetSpec | None = None
    value: str | None = None
    expected_result: str | None = None
    output_key: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)
    risk: RiskLevel = RiskLevel.SAFE

    @model_validator(mode="after")
    def validate_target_requirements(self) -> "AgentDecision":
        if self.action in {ActionType.CLICK, ActionType.TYPE, ActionType.SELECT, ActionType.READ, ActionType.EXTRACT} and self.target is None:
            raise ValueError(f"{self.action.value} requires a target")
        if self.action in {ActionType.TYPE, ActionType.SELECT, ActionType.NAVIGATE} and not self.value:
            raise ValueError(f"{self.action.value} requires a value")
        if self.action == ActionType.EXTRACT and not self.output_key:
            raise ValueError("extract requires output_key")
        return self


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=2, ge=1, le=5)
    backoff_ms: int = Field(default=250, ge=0, le=10_000)


class StepSpec(BaseModel):
    id: str
    action: ActionType
    target: TargetSpec | None = None
    value: str | None = None
    output_key: str | None = None
    expected_result: str | None = None
    timeout_ms: int = Field(default=5000, ge=100, le=60_000)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    risk: RiskLevel = RiskLevel.SAFE


class InputSpec(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"]
    required: bool = True
    description: str = ""


class OutputSpec(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"]
    description: str = ""


class Checkpoint(BaseModel):
    type: Literal["text_present", "url_contains"]
    value: str


class BusinessOutcomeSpec(BaseModel):
    code: str
    selector: str
    message: str


class CompatibilitySpec(BaseModel):
    application_family: str
    application_version: str = "demo-v1"
    tenant_variant: str = "base"


class CapabilityArtifact(BaseModel):
    schema_version: str = "1.0"
    capability_id: str
    name: str
    description: str
    application: str
    compatibility: CompatibilitySpec
    risk_level: RiskLevel = RiskLevel.SAFE
    approval_state: Literal["draft", "approved"] = "draft"
    inputs: list[InputSpec]
    outputs: list[OutputSpec]
    steps: list[StepSpec] = Field(min_length=1)
    checkpoint: Checkpoint
    business_outcomes: list[BusinessOutcomeSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunError(BaseModel):
    code: str
    message: str
    step_id: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence: str | None = None


class RunResult(BaseModel):
    status: RunStatus
    run_id: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    business_code: str | None = None
    message: str | None = None
    error: RunError | None = None
    recovered_conditions: list[str] = Field(default_factory=list)
    intervention_id: str | None = None
