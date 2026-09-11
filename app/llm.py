from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.models import AgentDecision
from app.surface import Observation


SYSTEM_PROMPT = """You are the discovery controller for a constrained computer-use system.
Choose exactly one safe UI action at a time to accomplish the user's goal.
Return only data matching the provided AgentDecision schema.
Never request shell execution, arbitrary JavaScript, credentials, or navigation outside the supplied application.
Prefer robust locators in this order: role/name, label, visible text, stable CSS, XPath.
For role locators, strategy='role', value is the ARIA role (button, link, textbox), and name is the accessible name.
For label locators, value is the visible associated label.
Use extract with output_key when the requested result is visible.
Use finish only after the requested data has been extracted and the goal is satisfied.
Use escalate if proceeding would be unsafe or the state is genuinely stuck.
Keep reason_summary short and operational; do not provide hidden chain-of-thought.
"""


def _openai_strict_schema() -> dict:
    """Return the AgentDecision schema in OpenAI Structured Outputs form.

    Pydantic emits a general JSON Schema. OpenAI strict structured outputs require
    object schemas to be closed and every property to be listed as required; fields
    that are optional in Python remain nullable in the schema. Defaults are removed
    because they are not needed for generation.
    """
    schema = AgentDecision.model_json_schema()

    def normalize(node: object) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class LLMProvider(ABC):
    @abstractmethod
    async def decide(self, goal: str, observation: Observation, step_number: int) -> AgentDecision:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-5.6") -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install the LLM extra with: pip install -e '.[llm]'") from exc
        self.client = AsyncOpenAI()
        self.model = model

    async def decide(self, goal: str, observation: Observation, step_number: int) -> AgentDecision:
        payload = {
            "goal": goal,
            "step_number": step_number,
            "observation": observation.as_prompt_data(),
        }
        response = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "agent_decision",
                    "schema": _openai_strict_schema(),
                    "strict": True,
                }
            },
        )
        return AgentDecision.model_validate_json(response.output_text)


class MockLLMProvider(LLMProvider):
    def __init__(self, decisions: Iterable[AgentDecision]) -> None:
        self._decisions = iter(decisions)

    async def decide(self, goal: str, observation: Observation, step_number: int) -> AgentDecision:
        try:
            return next(self._decisions)
        except StopIteration as exc:
            raise RuntimeError("MockLLMProvider ran out of decisions") from exc
