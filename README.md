# Computer-Use Automation System

A small end-to-end implementation of a record-once / replay-many computer-use system for legacy applications. An LLM discovers a UI workflow once, the successful run is converted into a typed capability artifact, and later invocations replay that artifact deterministically without an LLM deciding each step.

The concrete target is a local fake banking operations console. It uses only synthetic data and includes normal success, `MEMBER_NOT_FOUND`, a recoverable interstitial, session expiry, a permission handoff, and a risky account-opening review path.

## Architecture

The implementation is intentionally single-process and file-backed:

- `app/demo.py` — local legacy-style banking surface.
- `app/surface.py` — surface protocol plus Playwright adapter and ranked locator resolution.
- `app/llm.py` — `LLMProvider`, OpenAI implementation, and deterministic mock provider.
- `app/agent.py` — observe → decide → policy-check → act discovery loop.
- `app/models.py` — typed action, artifact, result, checkpoint, risk, and error contracts.
- `app/capability.py` — artifact parameterization, serialization, interpolation, and input validation.
- `app/replay.py` — deterministic replay engine; no LLM decision calls.
- `app/policy.py` — host/action allowlist and risk gates.
- `app/handoff.py` — session ownership and automation ↔ human control state machine.
- `app/observability.py` / `app/redaction.py` — JSONL evidence and secret redaction.

## Repository layout

```text
app/
  agent.py
  capability.py
  cli.py
  config.py
  demo.py
  errors.py
  handoff.py
  llm.py
  models.py
  observability.py
  policy.py
  redaction.py
  replay.py
  surface.py
evidence/
  example_capability.json
  README.md
  BUILD_VERIFICATION.md
tests/
  conftest.py
  test_browser_integration.py
  test_core.py
  test_demo.py
  test_playwright_surface.py
  test_replay_unit.py
README.md
REPORT.md
pyproject.toml
.env.example
```

## Requirements and setup

Python 3.11+ is supported; Python 3.12+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -e ".[dev,llm]"
playwright install chromium
```

For a genuine discovery run, export your model key. The project does not auto-load `.env`; `.env.example` documents the supported variables.

```bash
export OPENAI_API_KEY="..."
export LLM_MODEL="gpt-5.6"
```

Replay, tests, and the demo app do not require an LLM key.

## Start the demo application

Terminal 1:

```bash
python -m app.cli demo
```

Open `http://127.0.0.1:8000` if you want to inspect it manually.

Useful synthetic IDs:

- `12345` — normal success.
- `99999` — `MEMBER_NOT_FOUND` business outcome.
- `55555` — delayed page plus known dismissible interstitial.
- `70000` — permission condition requiring human handoff.
- `88888` — simulated session expiry with a known recovery action.

## Genuine LLM discovery

Terminal 2, while the demo is running:

```bash
python -m app.cli discover \
  --goal "Look up member 12345 and return their current savings balance" \
  --target http://127.0.0.1:8000 \
  --param member_id=12345 \
  --artifact evidence/example_capability.json \
  --evidence evidence/discovery \
  --headed
```

The model receives a compact observation rather than raw full-page HTML, emits one typed action at a time, and every decision passes schema and policy validation before Playwright executes it. The successful trace is parameterized (`12345` → `{{member_id}}`) and saved as a reviewable artifact.

## Deterministic replay

No LLM provider is used by this path.

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=12345 \
  --evidence evidence/replay-success \
  --headed
```

Expected result contains:

```json
{
  "status": "success",
  "outputs": {
    "savings_balance": "4621.77"
  }
}
```

### Business outcome

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=99999 \
  --evidence evidence/replay-not-found \
  --headed
```

This returns `status=business_outcome` and `business_code=MEMBER_NOT_FOUND`; it is not reported as an automation crash.

### Recoverable runtime condition

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=55555 \
  --evidence evidence/replay-recovered \
  --headed
```

The known interstitial is dismissed and recorded in `recovered_conditions` before replay continues.

## Human handoff demo

Use a headed browser because a human must interact with the same live session:

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=70000 \
  --evidence evidence/replay-handoff \
  --headed \
  --interactive-handoff
```

When the permission marker appears, automation pauses, records an intervention, releases session ownership, and leaves the existing browser open. Click **Operator Override** in that same browser. Then return to the terminal and press Enter. Ownership returns to automation and replay continues.

## Safety model

The executor enforces policy outside the model prompt:

1. LLM output is parsed into a typed `AgentDecision`.
2. Action/domain policy is checked.
3. Risk class is checked.
4. Only then can the surface adapter execute the action.

The default policy permits only `localhost` and `127.0.0.1`. Risky and irreversible actions require human control. The model cannot submit arbitrary Python, shell commands, JavaScript, or unrestricted URLs. Structured logs recursively redact common secret-bearing fields such as passwords, tokens, API keys, cookies, authorization values, and SSNs.

## Tests

```bash
pytest
```

The suite covers artifact validation, input interpolation, policy blocking, redaction, business-outcome classification, checkpoint failures, structured replay failures, recovery, handoff ownership, demo routes, Playwright locator behavior, deterministic replay, and mock-provider discovery.

`tests/test_browser_integration.py` launches the real FastAPI demo plus Playwright. The build workspace used to generate this repository had an administrator Chromium URL blocklist, so those localhost navigation tests could not be completed there. `evidence/BUILD_VERIFICATION.md` records exactly what was and was not verified; nothing is fabricated.

## Design trade-offs and limitations

This is deliberately not a distributed production platform. It has no fleet scheduler, durable database, authentication layer, tenant management service, or co-browsing UI. The important seams are present: surface abstraction, typed/versioned artifact, deterministic replay, result/error taxonomy, risk enforcement, observability, and session ownership. `REPORT.md` explains how those seams extend to desktop surfaces and multi-tenant vendor variants.
