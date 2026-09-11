1. Architecture

The system is a deliberately small end-to-end vertical slice of a record-once / replay-many computer-use platform.

A local FastAPI application represents a legacy banking operations console. PlaywrightSurface is the concrete computer-use adapter, while the Surface abstraction separates perception and interaction mechanics from discovery and deterministic replay.

The discovery path uses an LLMProvider to choose one typed action at a time from a compact representation of the current UI. Model output is parsed into structured Pydantic models and validated against policy before the browser can execute it.

The production-style execution path is ReplayEngine. It consumes a saved capability artifact and executes the recorded workflow deterministically without asking an LLM what action to perform next.

The implementation intentionally stays single-process and file-backed. Adding queues, distributed workers, databases, or orchestration would increase implementation complexity without improving the core design questions being evaluated here.

The primary boundaries are:

LLM provider

surface adapter

capability artifact

policy enforcement

deterministic replay engine

observability

human handoff controller

This keeps the system small enough to understand while preserving clear seams for future production expansion.

2. Artifact schema

CapabilityArtifact is a typed and versioned contract rather than a raw model transcript.

It contains:

capability identity and schema version

application-family and compatibility metadata

typed runtime inputs

typed outputs

ordered actions

target/locator strategies

risk classifications

retry and error behavior

known business outcomes

final success checkpoint

creation metadata

Concrete values learned during discovery are parameterized. For example, the member identifier used during discovery is converted from 12345 to {{member_id}}, allowing the same capability to execute for different members.

Targets contain an ordered set of locator candidates. The browser adapter prefers stronger semantic strategies such as accessible role/name and associated labels before falling back to visible text, CSS, or XPath.

For legacy table-style data extraction, the surface can also resolve semantic field descriptions to structured table values and canonicalize them into a more stable selector for the saved artifact.

Ambiguous targets are rejected rather than silently selecting the first approximate match. This is particularly important for actions that mutate application state.

The artifact remains mostly surface-neutral. Actions such as click, type, extract, and wait express user-interface intent rather than exposing Playwright calls directly. A future desktop, accessibility-tree, or vision-based adapter could map those same action contracts onto another interaction mechanism.

The committed evidence/example_capability.json was generated from the successful live LLM-driven discovery run and is stored as human-readable JSON so it can be reviewed, versioned, and deterministically replayed.

Artifacts do not intentionally persist credentials, authentication tokens, cookies, raw model transcripts, or other secrets.

3. Determinism & error handling

Deterministic replay performs no LLM decision calls.

Given a capability artifact and runtime input values, the replay engine:

validates artifact inputs,

interpolates parameterized values,

validates each action against policy,

resolves the required control using ranked locator strategies,

executes the action,

handles known recoverable runtime conditions,

extracts declared outputs,

verifies the final checkpoint,

returns a structured result.

The result contract distinguishes three important categories.

A normal execution returns success with declared outputs.

A known domain condition such as an unknown member returns business_outcome with a code such as MEMBER_NOT_FOUND. This is intentionally not treated as an automation crash.

Recoverable runtime conditions such as a known interstitial, transient delay, or simulated session expiry can be handled and recorded before replay continues.

Unrecoverable failures return structured debugging information such as:

error code

failing step

expected state

observed condition

evidence path

Locator ambiguity is treated as a failure rather than allowing automation to guess. Missing controls and browser timeouts receive only bounded retries.

The capability also contains a final checkpoint so success is verified from observable application state rather than inferred merely because the final click completed.

The generated capability was successfully replayed locally without an LLM and returned:

{
  "status": "success",
  "outputs": {
    "current_savings_balance": "$4621.77"
  }
}

The same artifact was also exercised with an unknown member and correctly returned MEMBER_NOT_FOUND as a business outcome.

4. Heterogeneity & multi-tenant

The primary extension seam is Surface.

The current implementation uses Playwright, but another adapter could implement the same contract using:

operating-system accessibility APIs

native desktop automation

browser accessibility trees

screenshot/coordinate interaction

constrained vision-based targeting

This allows the discovery and replay layers to remain independent from the specific mechanism used to observe or control the application.

A legacy-web implementation could add:

iframe or frameset traversal

deeper table interpretation

accessibility-tree matching

constrained visual fallback

without changing the capability contract.

For multi-tenant reuse, the artifact already carries concepts such as:

application_family

application_version

tenant_variant

In a production system, a base capability would belong to a vendor/application family. Tenant-specific differences would be represented as small overrides for routes, labels, or locator strategies instead of duplicating the entire workflow.

Replay telemetry could track success rates by vendor version and tenant. If one application version begins failing checkpoints or locator resolution, that compatibility range could be quarantined while unaffected tenants continue using the base capability.

This design supports reuse while still allowing controlled specialization when vendor configuration differs.

5. Escalation & handoff

HandoffController models explicit session ownership.

A session can be owned by:

automation

a human operator

nobody while control transfer is in progress

When replay encounters a permission condition or another state that should not be handled automatically, it captures evidence and creates an intervention containing context such as:

run identifier

current step

current URL

reason for escalation

screenshot/evidence

current ownership state

In non-interactive mode the execution can return a paused intervention state.

In interactive headed mode, the same Playwright browser remains open. Automation releases ownership, the human performs the required action in that exact live session, and control is then returned to automation.

The verified handoff demonstration used synthetic member 70000. Automation paused at the permission condition, the operator used the same browser session to perform the manual override, and replay resumed successfully without recreating the browser context.

This is intentionally a minimal operator interface. A production deployment would expose the same ownership/state transitions through an authenticated remote operator console.

The important property demonstrated here is that human and automation ownership are mutually exclusive and session context survives the handoff.

6. Safety

Safety is enforced in executable policy rather than relying solely on the LLM prompt.

The execution path is:

LLM decision
→ schema validation
→ policy validation
→ risk validation
→ surface execution

The default policy allowlists only:

localhost

127.0.0.1

Allowed action types are explicitly controlled.

Actions are classified into risk levels such as:

safe

reversible

risky

irreversible

Risky or irreversible behavior requires human involvement.

The model is not given an interface for executing arbitrary:

Python

shell commands

JavaScript

unrestricted external URLs

Structured logging passes values through recursive redaction for common secret-bearing fields such as:

passwords

API keys

authorization values

tokens

cookies

SSNs

The banking application contains only synthetic data.

The current approach still has limits. Field-name redaction is not a full data-loss-prevention system. A production implementation would also require:

encrypted evidence storage

authenticated operator identities

tenant-scoped authorization

retention policies

stronger content-level PII detection

artifact approval/signing

audit logging

production secret management

7. Cuts

I deliberately did not build:

distributed workers

queues

Kubernetes deployment

production databases

full tenant-management infrastructure

a native desktop adapter

a real-time remote co-browsing console

production authentication and authorization

Those components would be reasonable extensions for a deployed system, but they are not necessary to demonstrate the central computer-use architecture.

A genuine LLM-driven discovery run was completed locally against the live demo application after configuring model API access.

That discovery produced the committed capability artifact. The generated artifact was then replayed deterministically without an LLM decision loop and successfully returned the expected savings balance.

Additional verified scenarios included:

successful deterministic replay

MEMBER_NOT_FOUND as a business outcome

same-session human handoff and resume

policy and error-path behavior

browser locator handling

The final local test suite completed with:

32 passed, 1 warning

With more time, the next additions would be:

artifact approval lifecycle

replay reliability/stability scoring

persistent intervention records

tenant/application-family override resolution

stronger accessibility and vision-based targeting

authenticated remote operator handoff

richer drift detection and replay telemetry
