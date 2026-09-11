# Architecture: ContextSnapshot contract and execution correlation

## Context

`mctl-agents` already has a precise answer to "what contract ran": ADR 007
(`docs/adr/007-agent-definition-execution-profile-contract.md`) splits
`AgentDefinition` from `ExecutionProfile`, and `orchestrator/resolver.py`
materializes one immutable `ExecutionPlan` per run
(`orchestrator/resolver.py:226`) carrying definition/profile versions, content
hashes, model policy version, prompt/skill hashes, tools, permissions, budget,
timeout, sandbox and `target_repository_sha`. What the repository has no
contract for at all is the other half of reproducibility: **what information
was actually put in front of the model**. The investigator reads a GitHub issue
(`gh_issue_view`, `orchestrator/run_issue_investigator.py:856`), clones the
target repo (`_clone_repo`, same file:888), pins its SHA
(`_target_repository_sha`, same file:105) and then lets the agent free-roam the
tree with Glob/Grep/Read; the incident responder pulls incident records and
Loki log tails through `mctl_get_incident` / `mctl_get_service_logs`
(`orchestrator/run_incident_responder.py:114-116`). None of that selection is
described, versioned, hashed or correlatable after the fact.
`docs/agent-inventory.yaml` names the gap explicitly in its
`promptSources` vs `runtimeContextInputs` note (lines 40-66): runtime context
"is real prompt surface but resolves per run, outside this repo" and is
currently pinned only by a single target git SHA.

This issue is architecture-first: define the canonical, versioned
`ContextSnapshot` contract, its identity/hash semantics, its provenance and
budget/freshness/trust vocabulary, and its boundary with `ExecutionProfile`
(capability eligibility, mctl-agents#242), policy (#197), evidence (#199) and
traces (#195) — **before** any retrieval or ranking logic exists. The hard
invariant the issue states, and that this proposal must make testable, is that
context relevance never becomes an authorization mechanism. The deliverable is
an ADR plus a typed, serializable, well-tested schema module that Temporal
activities and workflows can carry; it changes no agent behaviour.

## User stories

- AS a mctl-agents maintainer I WANT a canonical versioned `ContextSnapshot`
  shape SO THAT the retrieval/ranking follow-ups do not each invent their own
  incompatible answer to "what did the agent see", the way ADR 007 prevented
  three incompatible answers to "what contract ran".
- AS an operator debugging a bad proposal I WANT every snapshot addressable
  from the execution identity already recorded by `ExecutionPlan` and
  `record_execution` (`orchestrator/temporal/activities/registry.py`,
  `state.py`) SO THAT I can go from one Argo workflow name or Temporal
  workflow id to exactly which issue text, which repo SHA, which log window
  and which incident were selected.
- AS a security reviewer I WANT source provenance expressed as locator +
  selector + content hash + byte count, never raw payload SO THAT log tails,
  issue bodies, prompts and secrets do not leak into telemetry, traces or the
  GitOps state repository.
- AS the author of the #197 policy work I WANT the ADR to state, and the tests
  to enforce, that no field of a snapshot is an input to an allow/deny decision
  SO THAT "the ranker surfaced it" can never be mistaken for "the caller may
  use it".
- AS the author of the #199 evidence work I WANT snapshots to reference
  evidence by id rather than embedding it SO THAT evidence has exactly one
  owner and snapshots do not become a second, unversioned evidence store.
- AS a future ranker implementer I WANT `strategy` and `ranker` name+version
  fields and an assembly budget expressed independently of any model's context
  window SO THAT I can change ranking and prove which snapshots came from which
  ranker version without a schema change.
- AS a reviewer of this contract I WANT a worked investigator example with
  GitHub, Loki and incident sources SO THAT the contract is demonstrated
  end-to-end at schema level before anything implements retrieval.

## Acceptance criteria (EARS)

- WHEN the ADR is published THE SYSTEM SHALL define one canonical
  `ContextSnapshot` document identified by `apiVersion:
  context.mctl.ai/v1alpha1` and `kind: ContextSnapshot`, with an explicit
  field list, an explicit lifecycle (assembled -> sealed -> referenced ->
  expired), and an explicit statement of which component owns each field.
- WHEN a snapshot is sealed THE SYSTEM SHALL compute `content_hash` as
  `"sha256:" + sha256(canonical JSON of every field except `content_hash`
  and `created_at`)`, using the same `sha256:`-prefixed convention as
  `orchestrator/resolver.py:301` (`_hash_bytes`).
- WHILE a snapshot is sealed THE SYSTEM SHALL treat it as immutable: any
  change produces a new snapshot with a new `content_hash`, never an edit,
  matching the "created once and never follows later promotions" rule ADR 007
  states for the runtime snapshot (`docs/adr/007-...:222`).
- WHEN a snapshot is created THE SYSTEM SHALL record an `execution`
  correlation block carrying agent name, environment, Temporal `workflow_id`
  and `run_id`, Argo workflow name, `target_repository_sha`, and the
  `ExecutionPlan` pins (`definition_version`, `definition_content_hash`,
  `profile_version`, `profile_content_hash`, `release_revision`) so a snapshot
  is addressable from execution identity and vice versa.
- WHEN an execution has more than one context-assembling step THE SYSTEM SHALL
  support both per-execution and per-step snapshots through a `step` block
  carrying `parent_snapshot_id`, a `step` name and a monotonic `sequence`, and
  SHALL require that a child's `execution` block equals its parent's.
- WHEN a source is included in a snapshot THE SYSTEM SHALL record a source
  descriptor containing `source_id`, `kind`, a non-secret `locator`, a
  `selector` describing the slice taken, `content_hash` of the bytes actually
  placed in context, `byte_count`, `retrieved_at`, `freshness`, `trust`,
  `selection` and `redaction` — and SHALL NOT store the source payload itself.
- IF a candidate source was considered and dropped THEN THE SYSTEM SHALL be
  able to record it with `included: false` and a `selection.reason_code`, so
  omission is auditable without storing the dropped content.
- WHEN freshness is recorded THE SYSTEM SHALL use the closed vocabulary
  `fresh | aging | stale | unknown` together with `observed_at` and an optional
  `max_age_seconds`, and SHALL define `unknown` as the fail-safe default rather
  than `fresh`.
- WHEN trust is recorded THE SYSTEM SHALL use the closed, descriptive
  vocabulary `authoritative | corroborated | reported | untrusted`, and the ADR
  SHALL state that these tiers describe origin only — they grant nothing. A
  GitHub issue body is `untrusted`, consistent with the existing prompt
  hardening in `_neutralize_prompt_tags`
  (`orchestrator/run_issue_investigator.py:1086`) and the untrusted-DATA
  wrapper in `_build_prompt` (same file:1136).
- WHILE any snapshot exists THE SYSTEM SHALL contain no allow/deny/permit/grant
  field and no field consumed by an authorization decision; a test SHALL assert
  the schema's field-name set contains no such token and that the snapshot
  module is not imported by any policy-decision path.
- WHEN a snapshot needs to reference execution results THE SYSTEM SHALL carry
  `evidence_refs` entries of `{evidence_id, kind}` only, and SHALL NOT inline
  evidence payloads (#199 owns evidence).
- WHEN a snapshot is correlated into telemetry THE SYSTEM SHALL emit only
  `snapshot_id`, `content_hash`, `strategy`/`ranker` versions, counts and byte
  totals as trace attributes (#195 owns traces), never locators' query strings
  that can embed free text, and never payloads.
- WHEN a context budget is recorded THE SYSTEM SHALL express it in
  model-independent units (`max_sources`, `max_bytes`, `max_bytes_per_source`)
  plus observed `used_sources`/`used_bytes` and a `truncated` flag, and the ADR
  SHALL state explicitly that this is an assembly budget, NOT the model's
  maximum context window, and that token-denominated budgets are deferred with
  written rationale.
- WHEN the context strategy or ranker changes THE SYSTEM SHALL record
  `strategy.name` + `strategy.version` and an optional `ranker.name` +
  `ranker.version`, so the producing configuration is recoverable from the
  snapshot alone without an `apiVersion` bump.
- WHEN a snapshot is serialized THE SYSTEM SHALL produce JSON of primitives
  only (str/int/float/bool/list/dict/None) so it can cross the Temporal
  workflow/activity boundary and be stored by mctl-api unchanged.
- IF a document declares an unknown `apiVersion` or `kind` THEN THE SYSTEM
  SHALL fail loudly with a dedicated error type, mirroring
  `orchestrator/manifest.py:135-143` and its `SUPPORTED_API_VERSIONS`
  allow-list (`orchestrator/manifest.py:35`), and SHALL NOT fall back to a
  default shape.
- IF redaction is applied to a source THEN THE SYSTEM SHALL hash the
  post-redaction bytes (the bytes actually placed in context), set
  `redaction.applied: true`, record the rule ids and `dropped_bytes`, and
  SHALL NOT store the pre-redaction payload anywhere in the snapshot.
- WHEN a snapshot is persisted THE SYSTEM SHALL carry a `retention` block with
  a class from `telemetry | execution-record | gitops` and an
  `expires_after_days`, and the ADR SHALL state which store honours which class
  and that expiry destroys the snapshot rather than truncating it in place.
- WHEN the schema module is imported THE SYSTEM SHALL depend on the standard
  library only, so that importing it inside the Temporal worker does not
  violate the worker/agent-stack separation enforced by
  `tests/test_worker_isolation.py`.
- WHEN the same inputs are assembled twice THE SYSTEM SHALL produce the same
  `content_hash`; timestamps SHALL be caller-supplied and excluded from the
  hash so determinism does not depend on wall-clock time (the same constraint
  `_now_iso`, `orchestrator/run_issue_investigator.py:162`, already implies for
  reproducible runs).
- WHEN the ADR ships THE SYSTEM SHALL include one full investigator example
  snapshot combining a GitHub issue source, a target-repository source pinned
  by SHA, a Loki log-window source and an incident-record source, checked in as
  a fixture and asserted by a round-trip test.

## Out of scope

- Implementing semantic or vector retrieval, embeddings, or any ranking
  algorithm. This proposal defines where a ranker's identity is recorded, not
  what a ranker does.
- Building a generic search or context service, or any new HTTP API.
- Changing issue-investigator, implementer, shepherd, incident-responder,
  service-agent or mentor behaviour, prompts, tools or budgets. No agent
  produces a snapshot as part of this proposal.
- Implementing #195 traces, #197 policy checkpoints, #199 evidence or #242
  capability discovery/invocation. This proposal fixes the seams they plug
  into, as ADR 007 did for its own follow-ups.
- Storing full logs, prompts, diffs or secrets anywhere in a snapshot.
- Any mctl-api schema migration or new registry table. Persistence is
  specified as a contract; wiring it into mctl-api is a follow-up.
- Token counting, model-context-window accounting, or cost attribution.

## Open questions

- **Where sealed snapshots durably live.** ADR 007's source-of-truth table
  (`docs/adr/007-...:215-224`) gives mctl-api the durable execution record and
  Temporal/Argo only until retention. This proposal therefore specifies
  `ExecutionRecord`-adjacent storage in mctl-api as the intended home and
  defines a `retention` class for it, but ships the schema module and fixtures
  in-repo only; the mctl-api row is a named follow-up, not a dependency.
- **Whether the snapshot must enumerate free-roam reads.** The investigator
  today lets the model Glob/Grep/Read arbitrarily inside the clone, so a
  faithful per-file source list cannot be produced without a tool-call hook.
  Interpretation taken: a single `target-repo` source pinned by
  `target_repository_sha` with `selector.mode: agent-directed` is contractually
  valid and honest; per-file enumeration is an optional refinement a later
  retrieval implementation may add without a schema change.
- **Whether `content_hash` should cover pre- or post-redaction bytes.**
  Interpretation taken: post-redaction, because that is what the model saw and
  what makes the snapshot reproducible; a `redaction` block records that
  something was removed. Recorded in design.md Alternatives.
- **Snapshot identifier format.** Interpretation taken:
  `snapshot_id = "cs-" + first 16 hex chars of content_hash`, derived not
  random, so identity is content-addressed; a registry may add its own opaque
  key later.
- **Numeric relevance scores.** Left optional (`selection.score: float | None`)
  because no ranker exists; `selection.rank` (ordinal) plus
  `selection.reason_code` are required so a deterministic assembler can fill
  them today.
