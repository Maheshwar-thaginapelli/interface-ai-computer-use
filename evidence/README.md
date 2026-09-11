# Evidence

This directory contains evidence from the verified end-to-end computer-use automation demo.

## Included evidence

- `discovery/`
  - `run.jsonl` — structured log from the genuine LLM-driven discovery run.
  - `final.png` — final browser state captured after successful discovery.

- `example_capability.json`
  - Typed, versioned capability artifact generated from the successful live LLM discovery run.
  - Contains the parameterized workflow used for deterministic replay.

- `replay-success/`
  - Evidence from deterministic replay using the generated capability artifact.
  - The replay path does not use the LLM to decide actions.

- `replay-not-found/`
  - Demonstrates the `MEMBER_NOT_FOUND` business outcome.
  - This is returned as an expected business result rather than an automation failure.

- `replay-handoff/`
  - Demonstrates human-in-the-loop escalation.
  - Automation pauses, the human takes control of the same live browser session, resolves the blocking condition, and returns control to automation.

## Reproducing the evidence

Start the local banking demo:

```bash
python -m app.cli demo
```

Then run genuine LLM discovery:

```bash
python -m app.cli discover \
  --goal "Look up member 12345 and return their current savings balance" \
  --target http://127.0.0.1:8000 \
  --param member_id=12345 \
  --artifact evidence/example_capability.json \
  --evidence evidence/discovery \
  --headed
```

Run deterministic replay:

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=12345 \
  --evidence evidence/replay-success \
  --headed
```

Run the business-outcome case:

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=99999 \
  --evidence evidence/replay-not-found \
  --headed
```

Run the human-handoff path:

```bash
python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=70000 \
  --evidence evidence/replay-handoff \
  --headed \
  --interactive-handoff
```

When the permission condition appears, automation pauses and releases control. Click **Operator Override** in the same browser session, return to the terminal, and press Enter to resume automation.

## Data handling

All evidence uses synthetic data from the local banking demo application.

No real banking credentials, authentication tokens, API keys, production customer data, or real PII are stored in this directory.
