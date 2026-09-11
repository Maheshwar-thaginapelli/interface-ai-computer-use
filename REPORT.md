# 1. ARCHITECTURE

The system is a deliberately small end-to-end vertical slice of a **record-once / replay-many computer-use platform**.

A local FastAPI application represents a legacy banking operations console. `PlaywrightSurface` is the concrete browser automation adapter, while the `Surface` abstraction separates perception and interaction mechanics from discovery and deterministic replay.

The discovery path uses an `LLMProvider` to choose one typed action at a time from a compact representation of the current UI. Model output is parsed into structured Pydantic models and validated against policy before the browser can execute it.

The production-style execution path is `ReplayEngine`. It consumes a saved capability artifact and executes the recorded workflow deterministically without asking an LLM what action to perform next.

The implementation intentionally stays single-process and file-backed. Adding queues, distributed workers, databases, or orchestration would increase implementation complexity without improving the core design questions being evaluated here.

The primary boundaries are:

- LLM provider
- Surface adapter
- Capability artifact
- Policy enforcement
- Deterministic replay engine
- Observability
- Human handoff controller

This keeps the system small enough to understand while preserving clear seams for future production expansion.

---

# 2. ARTIFACT SCHEMA

`CapabilityArtifact` is a typed and versioned contract rather than a raw model transcript.

It contains:

- Capability identity and schema version
- Application-family and compatibility metadata
- Typed runtime inputs
- Typed outputs
- Ordered actions
- Target and locator strategies
- Risk classifications
- Retry and error behavior
- Known business outcomes
- Final success checkpoint
- Creation metadata

Concrete values learned during discovery are parameterized.

For example:

```text
12345 → {{member_id}}
```

This allows the same capability to execute for different members without rediscovering the workflow.

Targets contain an ordered set of locator candidates. The browser adapter prefers stronger semantic strategies such as accessible role/name and associated labels before falling back to visible text, CSS, or XPath.

For legacy table-style data extraction, the surface can also resolve semantic field descriptions to structured table values and canonicalize them into a more stable selector for the saved artifact.

Ambiguous targets are rejected rather than silently selecting the first approximate match. This is especially important for actions that may change application state.

The artifact remains mostly surface-neutral. Actions such as `click`, `type`, `extract`, and `wait` express user-interface intent rather than exposing Playwright calls directly. A future desktop, accessibility-tree, or vision-based adapter could map those same action contracts onto another interaction mechanism.

The committed `evidence/example_capability.json` was generated from the successful live LLM-driven discovery run and is stored as human-readable JSON so it can be reviewed, versioned, and deterministically replayed.

Artifacts do not intentionally persist credentials, authentication tokens, cookies, raw model transcripts, or other secrets.

---

# 3. DETERMINISM & ERROR HANDLING

Deterministic replay performs **no LLM decision calls**.

Given a capability artifact and runtime input values, the replay engine:

1. Validates artifact inputs
2. Interpolates parameterized values
3. Validates each action against policy
4. Resolves the required control using ranked locator strategies
5. Executes the action
6. Handles known recoverable runtime conditions
7. Extracts declared outputs
8. Verifies the final checkpoint
9. Returns a structured result

The result contract separates three important categories.

## SUCCESS

A normal execution returns `success` with declared outputs.

```json
{
  "status": "success",
  "outputs": {
    "current_savings_balance": "$4621.77"
  }
}
```

## BUSINESS OUTCOME

A known domain condition such as an unknown member returns:

```text
status = business_outcome
business_code = MEMBER_NOT_FOUND
```

This is intentionally not treated as an automation crash.

## RECOVERABLE OR HARD FAILURE

Recoverable runtime conditions such as a known interstitial, transient delay, or simulated session expiry can be handled and recorded before replay continues.

Unrecoverable failures return structured debugging information such as:

- Error code
- Failing step
- Expected state
- Observed condition
- Evidence path

Locator ambiguity is treated as a failure rather than allowing the automation to guess. Missing controls and browser timeouts receive only bounded retries.

The capability also contains a final checkpoint so success is verified from observable application state rather than inferred merely because the final click completed.

The generated capability was successfully replayed locally without an LLM and returned the expected savings balance.

The same artifact was also exercised with an unknown member and correctly returned `MEMBER_NOT_FOUND` as a business outcome.

---

# 4. HETEROGENEITY & MULTI-TENANT

The primary extension seam is `Surface`.

The current implementation uses Playwright, but another adapter could implement the same contract using:

- Operating-system accessibility APIs
- Native desktop automation
- Browser accessibility trees
- Screenshot/coordinate interaction
- Constrained vision-based targeting

This allows the discovery and replay layers to remain independent from the specific mechanism used to observe or control the application.

A legacy-web implementation could add:

- Iframe or frameset traversal
- Deeper table interpretation
- Accessibility-tree matching
- Constrained visual fallback

without changing the capability contract.

For multi-tenant reuse, the artifact already carries concepts such as:

- `application_family`
- `application_version`
- `tenant_variant`

In a production system, a base capability would belong to a vendor or application family. Tenant-specific differences would be represented as small route or locator overrides instead of duplicating the complete workflow.

Replay telemetry could track success rates by vendor version and tenant. If one application version begins failing checkpoints or locator resolution, that compatibility range could be quarantined while unaffected tenants continue using the base capability.

This design supports reuse while still allowing controlled specialization when vendor configuration differs.

---

# 5. ESCALATION & HANDOFF

`HandoffController` models explicit session ownership.

A session can be owned by:

- Automation
- A human operator
- Nobody while control transfer is in progress

When replay encounters a permission condition or another state that should not be handled automatically, it captures evidence and creates an intervention containing context such as:

- Run identifier
- Current step
- Current URL
- Reason for escalation
- Screenshot or evidence
- Current ownership state

In non-interactive mode, the execution can return a paused intervention state.

In interactive headed mode, the same Playwright browser remains open. Automation releases ownership, the human performs the required action in that exact live session, and control is then returned to automation.

The verified handoff demonstration used synthetic member `70000`.

The flow was:

```text
AUTOMATION
    ↓
Permission condition detected
    ↓
Automation pauses
    ↓
Human takes control of the SAME browser session
    ↓
Operator Override is performed
    ↓
Control returns to automation
    ↓
Replay resumes successfully
```

The browser context is not recreated during the handoff.

This is intentionally a minimal operator interface. A production deployment would expose the same ownership and state transitions through an authenticated remote operator console.

The important property demonstrated here is that human and automation ownership are mutually exclusive and session context survives the handoff.

---

# 6. SAFETY

Safety is enforced in executable policy rather than relying only on the LLM prompt.

The execution path is:

```text
LLM decision
      ↓
Schema validation
      ↓
Policy validation
      ↓
Risk validation
      ↓
Surface execution
```

The default policy allowlists only:

- `localhost`
- `127.0.0.1`

Allowed action types are explicitly controlled.

Actions are classified into risk levels such as:

- Safe
- Reversible
- Risky
- Irreversible

Risky or irreversible behavior requires human involvement.

The model is not given an interface for executing arbitrary:

- Python
- Shell commands
- JavaScript
- Unrestricted external URLs

Structured logging passes values through recursive redaction for common secret-bearing fields such as:

- Passwords
- API keys
- Authorization values
- Tokens
- Cookies
- SSNs

The banking application contains only synthetic data.

## CURRENT LIMITATIONS

This implementation is not a complete production security boundary.

A production deployment would additionally require:

- Encrypted evidence storage
- Authenticated operator identities
- Tenant-scoped authorization
- Retention policies
- Stronger content-level PII detection
- Artifact approval and signing
- Centralized audit logging
- Production secret management

---

# 7. CUTS

I deliberately did not build:

- Distributed workers
- Queues
- Kubernetes deployment
- Production databases
- Full tenant-management infrastructure
- A native desktop adapter
- A real-time remote co-browsing console
- Production authentication and authorization

Those components would be reasonable extensions for a deployed system, but they are not necessary to demonstrate the central computer-use architecture.

A genuine LLM-driven discovery run was completed locally against the live demo application after configuring model API access.

That discovery produced the committed capability artifact.

The generated artifact was then replayed deterministically without an LLM decision loop and successfully returned the expected savings balance.

Additional verified scenarios included:

- Successful deterministic replay
- `MEMBER_NOT_FOUND` as a business outcome
- Same-session human handoff and resume
- Policy and error-path behavior
- Browser locator handling

## FINAL LOCAL VERIFICATION

```text
32 passed, 1 warning
```

With more time, the next additions would be:

- Artifact approval lifecycle
- Replay reliability and stability scoring
- Persistent intervention records
- Tenant and application-family override resolution
- Stronger accessibility and vision-based targeting
- Authenticated remote operator handoff
- Richer drift detection and replay telemetry
