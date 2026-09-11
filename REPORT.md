# 1. Architecture

The system is a deliberately small vertical slice. A local FastAPI application represents a legacy banking operations console. `PlaywrightSurface` is the concrete computer-use adapter, while the `Surface` protocol separates perception/action mechanics from the discovery and replay layers. The discovery path uses an `LLMProvider` to choose one typed action at a time from a compact observation. Every action is validated by Pydantic and by an explicit policy before the surface can execute it. The production-style path is `ReplayEngine`, which consumes a saved artifact and never asks an LLM what to do next.

The implementation stays single-process and stores artifacts/evidence as files. That is intentional: queues, databases, workers, and orchestration would add deployment surface without improving the load-bearing design questions in this exercise. The main boundaries are the LLM provider, surface adapter, capability contract, policy, replay engine, and handoff controller.

# 2. Artifact schema

`CapabilityArtifact` is a typed, versioned contract rather than a raw model transcript. It includes identity and compatibility metadata, typed inputs and outputs, ordered `StepSpec` actions, risk classification, known business outcomes, and a final checkpoint. Concrete discovery values are replaced with templates such as `{{member_id}}`, so one learned flow can be invoked with different runtime inputs.

Targets use an ordered set of locator candidates. The browser adapter prefers accessible role/name or associated labels, then visible text, then CSS/XPath fallbacks. Replay rejects ambiguous matches rather than clicking the first approximate element. `robustness_note` lets a reviewer understand why a target strategy is expected to survive. The artifact is mostly surface-neutral: actions such as click/type/extract and semantic target descriptions can be mapped by a future accessibility, vision, or desktop adapter even though this implementation uses Playwright.

Artifacts never intentionally contain credentials, cookies, tokens, or raw LLM transcripts. The checked-in example is human-readable JSON and can be reviewed or version-controlled before approval.

# 3. Determinism & error handling

Deterministic replay validates inputs, interpolates parameters, validates each action against policy, resolves a target using ordered locators, executes with bounded retries, checks for runtime conditions, extracts declared outputs, and verifies the final checkpoint. There is no LLM decision call in this path.

The result contract separates three concerns. A normal result returns `success` plus typed outputs. A known domain condition such as `MEMBER_NOT_FOUND` returns `business_outcome` instead of throwing a system error. Recoverable conditions such as the demo interstitial or session expiry are handled explicitly and appended to `recovered_conditions`. Unrecoverable problems return a structured failure with error code, step id, and evidence path. Locator ambiguity fails immediately; missing targets and Playwright timeouts receive only bounded retries.

The checkpoint prevents false success after the final click. For the sample capability it asserts that the current URL contains the parameterized savings route. A real deployment would add stronger page-state assertions and replay telemetry to identify selector/version drift.

# 4. Heterogeneity & multi-tenant

The main extension seam is `Surface`. A desktop adapter could implement the same contract using OS accessibility APIs; a vision adapter could resolve `TargetSpec` against screenshots and coordinates. The artifact records semantic action intent and prioritized target evidence rather than spreading Playwright calls through the model/replay code. A legacy-web adapter could add frame traversal, accessibility-tree matching, or constrained visual targeting without changing the calling contract.

For multi-tenant reuse, the artifact already carries `application_family`, `application_version`, and `tenant_variant`. In a larger system, a base artifact would belong to a vendor/application family and tenant-specific variants would store small route or locator overrides, not full copied flows. Compatibility tests and replay telemetry would track success by vendor version and tenant. When a version starts failing checkpoints or locator resolution, the base capability could be quarantined for that compatibility range while other tenants continue using it.

# 5. Escalation & handoff

`HandoffController` models explicit ownership: automation, nobody while paused, or human. When replay detects a permission marker or reaches a risky/irreversible step, it captures evidence and creates an `Intervention` containing run id, step, URL, reason, and screenshot. In non-interactive mode the run returns `paused`. In interactive headed mode, the same Playwright page remains alive, ownership moves to the human, the operator performs the manual action in that existing browser, and pressing Enter returns ownership to automation.

This is intentionally a minimal operator surface. A production system would expose the same state transition through an authenticated operator console and remote session stream. The important seam is real: the browser context is not recreated during handoff, and automation/human ownership is mutually exclusive.

# 6. Safety

Safety is enforced in code rather than only in an LLM prompt. The default policy allowlists localhost hosts and allowed action types. Navigation is checked before execution. Actions carry `safe`, `reversible`, `risky`, or `irreversible` classifications; the latter two require a human. The LLM is never given an action that executes arbitrary Python, shell commands, or JavaScript.

Structured logging passes records through recursive redaction for common secret-bearing field names. The demo contains synthetic data only. The design still has limits: field-name redaction is not a full DLP system, the local demo has no real authentication boundary, and a production deployment would need encrypted evidence storage, tenant-scoped authorization, retention controls, stronger content-level PII detection, signed/approved artifact versions, and audited operator identity.

# 7. Cuts

I deliberately did not build distributed workers, queues, databases, Kubernetes deployment, full tenant plumbing, a native desktop adapter, or a real-time co-browsing console. Those pieces would be appropriate later but would distract from the central contract and replay semantics here. I also did not fabricate a genuine LLM discovery run: the build environment did not expose an `OPENAI_API_KEY`, and its managed Chromium policy blocks local URL navigation. The repository includes the genuine provider path, browser integration tests, exact commands, and a checked-in reviewable example artifact so those final evidence runs can be produced on a normal development machine.

With more time, the next additions would be an approval lifecycle for learned artifacts, replay stability scoring, persisted intervention records, application-family/tenant override resolution, stronger accessibility/vision targeting, and authenticated remote operator handoff.
