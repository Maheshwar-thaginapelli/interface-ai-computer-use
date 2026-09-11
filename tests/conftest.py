from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from app.models import (
    ActionType,
    BusinessOutcomeSpec,
    CapabilityArtifact,
    Checkpoint,
    CompatibilitySpec,
    InputSpec,
    LocatorCandidate,
    OutputSpec,
    StepSpec,
    TargetSpec,
)


@pytest.fixture(scope="session")
def demo_server() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    base_url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.demo:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=Path(__file__).parents[1],
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base_url, timeout=0.2).read()
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Demo server did not start")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def sample_artifact(demo_server: str) -> CapabilityArtifact:
    return make_artifact(demo_server)


def make_artifact(base_url: str) -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="lookup-savings-balance",
        name="Lookup Savings Balance",
        description="Look up a member and return their savings balance",
        application="Legacy Bank Operations Demo",
        compatibility=CompatibilitySpec(application_family="legacy-bank-demo"),
        inputs=[InputSpec(name="member_id", type="string")],
        outputs=[OutputSpec(name="savings_balance", type="string")],
        steps=[
            StepSpec(id="navigate", action=ActionType.NAVIGATE, value=base_url),
            StepSpec(
                id="member-id",
                action=ActionType.TYPE,
                target=TargetSpec(
                    description="Member ID field",
                    expected_tag="input",
                    candidates=[
                        LocatorCandidate(strategy="label", value="Member ID"),
                        LocatorCandidate(strategy="css", value="#mid"),
                    ],
                ),
                value="{{member_id}}",
            ),
            StepSpec(
                id="search",
                action=ActionType.CLICK,
                target=TargetSpec(
                    description="Search Member button",
                    candidates=[
                        LocatorCandidate(strategy="role", value="button", name="Search Member"),
                        LocatorCandidate(strategy="text", value="Search Member"),
                    ],
                ),
            ),
            StepSpec(
                id="view-savings",
                action=ActionType.CLICK,
                target=TargetSpec(
                    description="View Savings link",
                    candidates=[
                        LocatorCandidate(strategy="role", value="link", name="View Savings"),
                        LocatorCandidate(strategy="text", value="View Savings"),
                    ],
                ),
            ),
            StepSpec(
                id="extract-balance",
                action=ActionType.EXTRACT,
                target=TargetSpec(
                    description="Current savings balance",
                    candidates=[LocatorCandidate(strategy="css", value="#savings-balance")],
                ),
                output_key="savings_balance",
            ),
        ],
        checkpoint=Checkpoint(type="url_contains", value="/member/{{member_id}}/savings"),
        business_outcomes=[
            BusinessOutcomeSpec(
                code="MEMBER_NOT_FOUND",
                selector="[data-business-outcome='MEMBER_NOT_FOUND']",
                message="No member exists for the supplied identifier.",
            )
        ],
    )
