# Resolve execute(agent, task): declarative resolver pilot

## Context

Accepted ADR 007 defines canonical v1alpha2 AgentDefinition, independently
published ExecutionProfile, atomic environment ReleaseBinding, and one immutable
ExecutionPlan per run. Issue #227 implements the runtime seam for only
\`issue-investigator\`.

Production activation remains blocked on #950 and real registry-backed binding
resolution. This issue may use checked-in, explicitly non-promotable
compatibility fixtures, but they must not become a second catalog or silently
replace a missing v1alpha2 release.

## Acceptance criteria

- \`execute("issue-investigator", task)\` returns a frozen deterministic
  ExecutionPlan containing exact definition/profile versions and binding
  revision/source; concrete model plus model-policy version; skill and prompt
  hashes; effective tools, \`policyRef\` and permissions; bounded budget and
  timeout; entrypoint/options builder/sandbox/CWFT; target repository SHA;
  approval and evidence requirements.
- The definition's \`executionProfileRef.compatibility\` is checked against the
  concrete selected profile version. Compatibility is not read from a
  profile-owned range.
- v1alpha2 missing release/profile/policy, disabled or ambiguous version,
  compatibility mismatch, unknown reference, unbounded limit, or unapproved
  sandbox fails before Argo submission. It never falls back silently.
- Legacy fallback is available only when explicit
  \`ISSUE_INVESTIGATOR_RESOLVER_MODE=legacy\` is selected and is observable.
  Declarative mode never falls back to baked-in CWFT defaults.
- Compatibility fixtures live under test/compatibility paths, are marked
  \`bindingSource: compatibility-fixture\` and \`promotable: false\`, and
  cannot be interpreted as registry or production activation state.
- The migrated v1alpha2 AgentDefinition remains canonical at the existing
  manifest path. Any local ExecutionProfile is a pilot fixture mirroring the
  future #950 catalog, not a second authoring surface.
- Resolved options preserve current investigator behavior, caller request
  shape, deterministic proposal slug/idempotency, proposal artifacts,
  source status block, issue comment, and stop-at-\`proposed\`.
- Runtime mutation capabilities remain constrained by explicit policy and
  permissions; tools alone are not authorization.
- Same binding fixture plus same task/target SHA yields identical plan
  identifiers. A later promotion never mutates an already created plan.
- A rollback drill proves explicit legacy mode reproduces current behavior.
- ExecutionPlan identifiers are logged in structured form; extending the
  durable mctl-api ExecutionRecord is a follow-up unless the existing API
  already accepts them.

## Out of scope

- Implementer/shepherd migration.
- Production default/cutover.
- Live catalog/release API changes owned by #950/mctl-api.
- Prompt, permission, model-selection, or product-visible behavior changes.
- Proposal acceptance, Tier 2 implementation semantics, or merge behavior.

## Fixed decisions

ADR 007 is normative. The pilot may choose module/fixture mechanics only; it
may not change lifecycle authority, atomic pairing, exact rollback,
v1alpha2 fail-closed behavior, or tools-versus-permissions.