# Evidence

`example_capability.json` is a checked-in reviewable capability example. The run-specific evidence folders are intentionally not populated with fabricated LLM/browser evidence.

Generate submission evidence on a normal local machine after installing Playwright Chromium and setting `OPENAI_API_KEY`:

```bash
python -m app.cli discover \
  --goal "Look up member 12345 and return their current savings balance" \
  --target http://127.0.0.1:8000 \
  --param member_id=12345 \
  --artifact evidence/example_capability.json \
  --evidence evidence/discovery \
  --headed

python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=12345 \
  --evidence evidence/replay-success \
  --headed

python -m app.cli replay \
  --artifact evidence/example_capability.json \
  --input member_id=99999 \
  --evidence evidence/replay-not-found \
  --headed
```

For the human-handoff path, replay with member `70000` and `--interactive-handoff`. The automation pauses on the same browser session; click **Operator Override** in that browser, then return to the terminal and press Enter.
