from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import uvicorn

from app.agent import DiscoveryAgent
from app.capability import load_artifact
from app.config import Settings
from app.llm import OpenAIProvider
from app.policy import Policy
from app.replay import ReplayEngine
from app.surface import PlaywrightSurface


def _key_values(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Expected KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        values[key] = value
    return values


async def _discover(args: argparse.Namespace) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is required for a genuine discovery run.")
        return 2
    settings = Settings.from_env()
    provider = OpenAIProvider(model=args.model or settings.llm_model)
    agent = DiscoveryAgent(provider, Policy(), max_steps=args.max_steps)
    async with PlaywrightSurface(headless=not args.headed) as surface:
        result = await agent.run(
            goal=args.goal,
            target_url=args.target,
            surface=surface,
            parameters=_key_values(args.param),
            artifact_path=args.artifact,
            evidence_dir=args.evidence,
            interactive_handoff=args.interactive_handoff,
        )
    print(json.dumps({
        "status": "success",
        "run_id": result.run_id,
        "artifact": str(args.artifact),
        "outputs": result.outputs,
        "steps": result.steps,
    }, indent=2))
    return 0


async def _replay(args: argparse.Namespace) -> int:
    artifact = load_artifact(args.artifact)
    engine = ReplayEngine(Policy())
    async with PlaywrightSurface(headless=not args.headed) as surface:
        result = await engine.run(
            artifact=artifact,
            inputs=_key_values(args.input),
            surface=surface,
            evidence_dir=args.evidence,
            interactive_handoff=args.interactive_handoff,
        )
    print(result.model_dump_json(indent=2))
    return 0 if result.status.value in {"success", "business_outcome"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Computer-use automation take-home demo")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Start the local legacy banking demo")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8000)

    discover = sub.add_parser("discover", help="Run genuine LLM-driven discovery")
    discover.add_argument("--goal", required=True)
    discover.add_argument("--target", default="http://127.0.0.1:8000")
    discover.add_argument("--param", action="append", default=[], help="Runtime parameter, e.g. member_id=12345")
    discover.add_argument("--artifact", type=Path, default=Path("evidence/example_capability.json"))
    discover.add_argument("--evidence", type=Path, default=Path("evidence/discovery"))
    discover.add_argument("--model", default=None)
    discover.add_argument("--max-steps", type=int, default=15)
    discover.add_argument("--headed", action="store_true")
    discover.add_argument("--interactive-handoff", action="store_true")

    replay = sub.add_parser("replay", help="Replay a saved artifact without LLM decisions")
    replay.add_argument("--artifact", type=Path, required=True)
    replay.add_argument("--input", action="append", default=[], help="Runtime input, e.g. member_id=12345")
    replay.add_argument("--evidence", type=Path, default=Path("evidence/replay"))
    replay.add_argument("--headed", action="store_true")
    replay.add_argument("--interactive-handoff", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "demo":
        uvicorn.run("app.demo:app", host=args.host, port=args.port, reload=False)
        return
    if args.command == "discover":
        raise SystemExit(asyncio.run(_discover(args)))
    if args.command == "replay":
        raise SystemExit(asyncio.run(_replay(args)))


if __name__ == "__main__":
    main()
