# Governed execution evidence envelope: construction, validation and sealing (Tier A)

## Context

mctl-agents already has four sealed, canonical governance contracts, each owned by
exactly one store: execution identity (`we_` execution ids, `orchestrator/work_context/`,
`orchestrator/execution_identity.py`), context snapshots (`cs_`/`cs-`,
`orchestrator/context_snapshot.py`, ADR 009), execution requests (`xr_`,
`orchestrator/work_context/execution_requests.py`), human approvals (`aar_`,
`orchestrator/action_approvals.py`), policy decisions
(`orchestrator/policy_checkpoint.py`, ADR 014) and the model usage ledger
(`orchestrator/usage_ledger.py`, ADR 012, joined on `session_id`/`result_uuid`).
What is missing is the one document that says, for a single governed execution,
*which* of those canonical records applied — a tamper-evident envelope that joins
them by reference. `orchestrator/context_snapshot.py:728` already declares the seam
for it: `EvidenceRef{evidence_id, kind}`, documented as "a pointer into the #199
evidence store", with no payload field and `from_dict` rejecting any other key. The
referent does not exist yet.

PR #483 tried to build that referent as `orchestrator/evidence_store.py` writing
durable `_evidence/` trees into the public `mctl-gitops` repository with 3650-day
retention. That architecture is invalid: it puts governance evidence in a public
repo, it duplicates state that is already canonical in mctl-api, and it predates
`we_`, `cs_`, `xr_` and the implemented usage ledger. This issue supersedes it and
scopes down to **Tier A only: the pure evidence contract** — construction,
validation, redaction and content-addressed sealing, with no persistence layer of
any kind. Durable storage and the retrieval API are Tier B, owned by mctl-api.

## User stories

- AS a platform operator I WANT one sealed, content-addressed envelope per governed
  execution SO THAT I can reconstruct what ran, under which policy, on which
  approvals, from which context and at what cost, without trusting model prose.
- AS a compliance reviewer I WANT the envelope to say explicitly when a required
  piece of evidence is unavailable SO THAT "no record" is never silently
  indistinguishable from "nothing happened".
- AS an mctl-agents developer I WANT the envelope to hold references and hashes only
  SO THAT there is exactly one owner per record and no second copy of the work-item,
  execution, snapshot or usage state to keep in sync.
- AS a security reviewer I WANT every block of the envelope to pass through
  redaction before it is hashed SO THAT a sealed evidence id can never certify bytes
  that contain a credential or a payload.
- AS a Tier B implementer (mctl-api) I WANT a versioned schema with a stable
  canonicalization and identity rule SO THAT I can persist and retrieve envelopes
  later without renegotiating the contract.

## Acceptance criteria (EARS)

### Schema and identity

- WHEN a new module `orchestrator/execution_evidence.py` is added THE SYSTEM SHALL
  declare `API_VERSION = "evidence.mctl.ai/v1alpha1"`, `KIND = "ExecutionEvidence"`
  and `SUPPORTED_API_VERSIONS`, following the pattern of
  `orchestrator/context_snapshot.py:39-45` and
  `orchestrator/execution_identity.py:43-50`.
- WHEN an envelope is sealed THE SYSTEM SHALL compute
  `content_hash = hash_bytes(canonical_json(<every field except content_hash,
  evidence_id and created_at>))` using `hash_bytes` and `canonical_json` imported
  from `orchestrator.context_snapshot` (the single hashing rule declared at
  `context_snapshot.py:130-144`), and SHALL NOT define a second hashing or
  canonicalization convention.
- WHEN an envelope is sealed THE SYSTEM SHALL derive
  `evidence_id = "ev-" + content_hash[7:23]`, mirroring the `cs-` rule at
  `context_snapshot.py:1245`.
- WHEN the same inputs are sealed twice with different `created_at` values THE
  SYSTEM SHALL produce the identical `evidence_id` and `content_hash`.
- WHEN any referenced block changes THE SYSTEM SHALL produce a different
  `evidence_id`.
- WHILE the envelope schema grows THE SYSTEM SHALL hash a newly added optional block
  only when it is present, so that previously sealed envelopes keep their
  `content_hash` (the rule stated at `context_snapshot.py:1174-1207`).
- WHEN `recompute_content_hash(envelope)` is called THE SYSTEM SHALL return the hash
  a fresh `seal()` of the same fields would produce, without mutating the envelope.

### Canonical joins (references, never copies)

- WHEN an envelope is constructed THE SYSTEM SHALL carry the execution join as an
  execution id validated against the `we_` prefix exported by
  `orchestrator/work_context/snapshots.py:39` (`EXECUTION_ID_PREFIX`), plus
  `work_item_id` and `trace_id`.
- WHEN an envelope carries context snapshots THE SYSTEM SHALL carry them as
  `snapshot_refs[]`, each a snapshot id plus its `sha256:`-prefixed `content_hash`,
  and SHALL NOT carry any snapshot source, selector, locator or body.
- WHEN an envelope carries an execution request THE SYSTEM SHALL carry the `xr_` id
  (`work_context/execution_requests.py:32`), its `kind` from
  `execution_requests.KINDS` and its `state` from `execution_requests.STATES`.
- WHEN an envelope carries usage THE SYSTEM SHALL carry only join keys into the
  canonical usage ledger — `session_id`, optional `result_uuid`, `model_key` and
  optional `devloop_stage` from `usage_ledger.DEVLOOP_STAGES` — and SHALL NOT copy
  token counts, cost figures or any ledger row content.
- WHEN an envelope carries approvals THE SYSTEM SHALL carry the canonical `aar_` id
  (`action_approvals.py:47`), the `intent_hash`, and a state from the
  `action_approvals` state vocabulary (`pending`/`approved`/`denied`/`expired`/
  `consumed`).
- WHEN an envelope carries policy decisions THE SYSTEM SHALL carry, per decision,
  `action_digest`, `verdict` from `policy_checkpoint.VERDICTS`, `code`,
  `policy_version`, `rule_id` and `approval_ref`, and SHALL NOT carry the action
  arguments.
- WHEN an envelope carries generated artifacts THE SYSTEM SHALL carry an immutable
  ref: a bounded `name`, a `kind`, and a `sha256:`-prefixed `content_hash`.
- WHEN an envelope is sealed THE SYSTEM SHALL carry exactly one `outcome` block with
  a `code` drawn from a closed vocabulary and a machine-readable `reason_code` slug.

### Undecided, derived from the canonical set

- WHEN a policy-decision reference is evaluated for whether the checkpoint failed to
  decide THE SYSTEM SHALL derive that answer by membership in
  `policy_checkpoint.UNDECIDED_CODES` (`policy_checkpoint.py:103`), imported from
  that module.
- THE SYSTEM SHALL NOT re-declare, copy or hard-code any undecided code list inside
  the evidence module.
- IF a policy-decision reference carries an undecided code THEN THE SYSTEM SHALL
  treat that decision as evidence that is not an answer, and SHALL require a
  corresponding gap unless a later decision for the same `action_digest` resolved it.

### Redaction

- WHEN an envelope is sealed THE SYSTEM SHALL pass **every** block of the envelope —
  not a subset — through `_safe()` before the canonical bytes are computed, so that
  `content_hash` and `evidence_id` certify the redacted document.
- WHEN `_safe()` encounters a value that matches a credential shape THE SYSTEM SHALL
  drop that value rather than mask it, following the documented rule at
  `orchestrator/tracing_sdk.py:132-138` ("dropped, never masked").
- WHEN `_safe()` drops a value THE SYSTEM SHALL record the drop as an explicit gap
  with a `redacted_out` code, so that redaction is visible rather than silent.
- WHILE building any block THE SYSTEM SHALL accept only scalar leaves of declared,
  bounded fields, and SHALL reject free-text fields; every human-facing reason is a
  slug from a closed vocabulary.
- WHEN a caller supplies an unknown key to any `from_dict` THE SYSTEM SHALL raise
  `ExecutionEvidenceError`, following `_reject_unknown_keys`
  (`context_snapshot.py:147`).

### Completeness and gaps

- WHEN an envelope is sealed THE SYSTEM SHALL expose `completeness` as a **derived**
  value, computed from the gap list, and SHALL NOT accept it as a caller-supplied
  field.
- WHILE an envelope has no gap whose `required` flag is true THE SYSTEM SHALL report
  `completeness == COMPLETE`.
- IF an envelope has at least one gap whose `required` flag is true THEN THE SYSTEM
  SHALL report `completeness == INCOMPLETE`.
- WHEN a required block cannot be populated THE SYSTEM SHALL require an explicit gap
  naming the block and a reason code from a closed vocabulary
  (`not_produced`, `store_unavailable`, `not_applicable`, `redacted_out`,
  `undecided`), and `seal()` SHALL raise `ExecutionEvidenceError` if a required block
  is both absent and ungapped.
- WHEN a gap names a block THE SYSTEM SHALL validate the block name against the
  closed set of envelope block names.

### No path construction, no pointer files

- THE SYSTEM SHALL NOT construct, accept or emit any filesystem path, path fragment,
  directory name or URL derived from caller input.
- THE SYSTEM SHALL NOT write any file, pointer file, "latest" symlink or absolute
  pointer to disk, and SHALL NOT import `pathlib`, `os.path` or perform any I/O.
- THE SYSTEM SHALL be stdlib-only and import no network, filesystem or third-party
  dependency, following `orchestrator/policy_checkpoint.py:39-41`.

### Runtime emission (payload-free)

- WHEN a governed execution seals an envelope THE SYSTEM SHALL expose a
  `to_log_dict()` projection consisting of `evidence_id`, `content_hash`,
  `completeness`, the outcome code and integer `*_count` values per block, and
  nothing else — the same count-not-list idiom as
  `ContextSnapshot.to_log_dict`'s `evidence_ref_count` (`context_snapshot.py:1082`).
- THE SYSTEM SHALL expose the envelope's identity in a form directly usable as the
  existing `context_snapshot.EvidenceRef{evidence_id, kind}`
  (`context_snapshot.py:728`) without changing that dataclass.
- THE SYSTEM SHALL NOT persist the projection or the envelope anywhere.
- THE SYSTEM SHALL produce an `ev-` id that is also valid as a `human_input`
  `"evidence:"` context ref (`orchestrator/human_input.py:46`), which already
  reserves that prefix.

## Out of scope

- Creating `orchestrator/evidence_store.py`, or anything resembling it.
- Writing evidence (envelopes, summaries, pointer files, indexes) into
  `mctl-gitops` or any other git repository.
- Any retention policy, and specifically any 3650-day public retention.
- Any second store for work items, executions, snapshots, execution requests,
  approvals or usage. This proposal reads no store and writes no store.
- The evidence retrieval API, durable persistence, and any mctl-api route. That is
  Tier B and a separate mctl-api issue.
- Continuing, repairing or shepherding mctlhq/mctl-agents#483.
- Wiring the envelope into `run_issue_investigator.py`, `run_implementer.py`,
  `run_shepherd.py` or `temporal/workflows/dev_loop.py` as a mandatory step. The
  module ships inert and additive, exactly as `context_snapshot.py` first shipped
  (ADR 009: "the only code that ships with it is a new, inert, additive schema
  module").
- Changing `EvidenceRef`, `ContextSnapshot` or any already-sealed hash.

## Open questions

- **Store id vs local id for snapshots.** `context_snapshot.seal()` mints local ids
  with the `cs-` prefix (`context_snapshot.py:1245`) while the mctl-api store uses
  `cs_` (`work_context/snapshots.py:42`). Proceeding with: `snapshot_refs[]` accepts
  either prefix and records which one it is, because both are real ids of the same
  document and the envelope must be sealable before the snapshot reaches the store.
- **Which blocks are "required".** The issue says `COMPLETE` holds iff there are no
  required gaps, but does not enumerate the required set. Proceeding with: execution
  join, outcome and at least one policy-decision reference are required for a
  governed execution; snapshots, execution request, usage, approvals and artifacts
  are required-if-applicable, expressed by the caller passing a declared
  `requirements` profile at seal time rather than by the module guessing.
- **ADR number.** `docs/adr/` has three files numbered `011-*` (three
  near-simultaneous proposals each took "the next free number") and 015/016 are free
  but burned and unreferenced. Proceeding with
  `018-execution-evidence-envelope-contract.md`, the next number above the highest
  used, and disambiguating every ADR cross-reference by full path rather than number.
- **Reason-code vocabulary for `outcome`.** The issue says "the final outcome" without
  naming values. Proceeding with a closed set aligned to the existing dev-loop
  outcome language (`succeeded`, `failed`, `refused`, `abandoned`, `superseded`).
- **Redaction module extraction.** Reusing the credential-shape screen in
  `orchestrator/tracing_sdk.py` requires it to be importable without OpenTelemetry.
  Proceeding with a behaviour-preserving extraction into a stdlib-only
  `orchestrator/redaction.py` that `tracing_sdk` then imports; the alternative
  (duplicating the regexes) is explicitly rejected as the "second, disagreeing
  convention" risk ADR 009 already names.
