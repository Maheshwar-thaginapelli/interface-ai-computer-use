# Build verification in the generated workspace

Verified in the build environment:

- `python -m compileall app tests` succeeds.
- 17 non-browser core/demo/replay tests pass.
- 1 Playwright surface test passes using `page.set_content`, validating Chromium launch, ranked locators, typing, and extraction.
- Total verified passing tests: 18.

The environment's managed Chromium policy contains a global URL blocklist, so browser navigation to the local FastAPI server returns `ERR_BLOCKED_BY_ADMINISTRATOR`. The repository retains five end-to-end Playwright tests against the live local demo application; they are expected to run on a normal development machine after `playwright install chromium`.

No `OPENAI_API_KEY` was present in the build environment. Genuine LLM discovery evidence was therefore not fabricated. Run the commands in `evidence/README.md` after configuring a key.
