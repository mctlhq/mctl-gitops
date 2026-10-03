# Design: issue-199-feat-governance-auditable-execution-evid

## Current state

### The four inputs exist and are not joined

**Traces (#195)** — `orchestrator/tracing.py` (stdlib-only facade),
`orchestrator/tracing_sdk.py` (SDK pipeline plus `GuardedExporter`),
`orchestrator/temporal/tracing.py` (worker interceptors). It already emits the
two domain events #199 wants: `tracing.record_policy_decision(...)`
(`tracing.py:607`, event `mctl.policy.decision`) and
`tracing.record_artifact(name, kind)` (`tracing.py:641`, event
`mctl.artifact.write`, called once per published proposal file from
`run_issue_investigator._trace_published`, `run_issue_investigator.py:2176`).
`AgentRunObserver` (`tracing.py:795`) reads model name, message ids and the two
usage counters and nothing else; `PROVIDER = "anthropic"` is a constant
(`tracing.py:776`).

Three properties of that pipeline decide this design:

1. **Nothing is exported in production.** `docs/observability/execution-traces.md`
   §Status: the platform Collector has no trace backend, choosing one is
   mctl-gitops#1280, and the 12-item live-evidence checklist is entirely open.
2. **Spans are droppable by design.** A 2048-span queue that drops when full, a
   5 s export timeout, a 5 s flush at exit. That is correct for telemetry and
   disqualifying for an audit record.
3. **The guard removes exactly what evidence needs.** `GuardedExporter` drops
   any key ending in `target`-shaped or payload-shaped suffixes, drops every
   string over 256 chars, and `record_policy_decision` deliberately omits the
   target and both digests ("never the target (it can be a URL with a path)",
   `tracing.py:620`).

**Identity (#196, ADR 011)** — `orchestrator/execution_identity.py`,
`api_version: identity.mctl.ai/v1alpha1`, `kind: ExecutionContext`. Sealed by
`seal()` (`:614`); `context_id = "ex-" + content_hash[7:23]`;
`content_hash = "sha256:" + sha256(canonical_json(payload))` over every field
except `content_hash`, `context_id`, `issued_at`. Blocks: `Actor{type, id,
verification}`, `Executor{type, id, agent, version, image_ref, binding}`,
`Scope{environment, tenant, repository, target_repository_sha, service, slug}`,
`Trigger{type, ref}`, `Correlation{temporal_workflow_id, temporal_run_id,
argo_workflow_name, attempt}`, `Assertions{asserted_by, asserted_fields,
declared_fields}`. Minted by the `mint_execution_context` activity
(`orchestrator/temporal/activities/identity.py:132`, `POST
/api/v1/agents/executions/context`), degrades to `mint_local()` on any failure;
consumed in the pod by `load_from_environment()` from
`MCTL_EXECUTION_CONTEXT_FILE`, which re-verifies the content hash and the
`context_id` binding with `hmac.compare_digest`. It is already projected into
gitops: `run_issue_investigator.py:1210` writes an `execution: {context_id,
trace_id, agent, version}` block into `.status.yaml`.

**Policy (#197, ADR 014)** — `orchestrator/policy_checkpoint.py`, stdlib-only.
`ActionRequest{action_kind, operation, target, args_digest, execution_id,
trace_id, actor, grants, metadata}` with `action_digest()` over kind,
operation, target, args digest, execution id and actor (`:133`).
`Decision{verdict, code, reason, policy_version, rule_id, action_digest,
approval_ref}` with `permitted = code in {allowed, approved}` (`:176`) and
`undecided` over `UNDECIDED_CODES` (`:103`). Every decision prints one
`POLICY_DECISION <json>` line (`DECISION_PREFIX`, `:105`) carrying exactly the
fields evidence needs — including the target and both digests, which the trace
event drops. ADR 014 §5 enumerates every governed site: the MCP `PreToolUse`
hook (`options._PolicyCheckpointHook`), the directive poller's reply and
submit, and seven orchestrator GitHub mutations in `run_implementer`,
`run_shepherd`, `run_issue_investigator` and `run_issue_poller`.

**Approvals (#198/mctl-api#366)** — `orchestrator/action_approvals.py`:
`SCHEMA_VERSION = "actionapproval/v1"`, `ID_PREFIX = "aar_"`,
`INTENT_ENCODING_VERSION = "mctl-action-intent/v1"`, `intent_hash()` byte-identical
to mctl-api's `IntentHash`, `ApprovalRecord`/`ApprovalAnswer`, and
`MctlApiApprovals` reached through `ROUTES` (`:41`). Receipts are consumed
atomically at decision time; `approval_ref` on a permitted decision is the
receipt id.

**Models/cost (ADR 012)** — not implemented. The ADR states, and a re-check
confirms, that no module in `orchestrator/` reads `total_cost_usd` or
`model_usage`. The only model data that exists today is the token counters
`AgentRunObserver` puts on spans.

### The reserved seam

ADR 009 (`docs/adr/009-context-snapshot-contract.md`) already declared this
proposal's referent and made the boundary normative:
`ContextSnapshot.evidence_refs: tuple[EvidenceRef, ...]` where
`EvidenceRef{evidence_id, kind}` and nothing else
(`orchestrator/context_snapshot.py:710`), with the §5 row "Evidence (#199) |
Evidence store | `evidence_refs: {evidence_id, kind}` only | Inline a payload;
evidence has exactly one owner". ADR 011 §6 has the mirror row: the execution
context records nothing about evidence. So #199 owns a store and an id, and
neither contract may hold the payload.

The reusable primitives are in place and must not be re-invented:
`context_snapshot.hash_bytes` / `canonical_json` (`:113`, `:123`), the
`sha256:` prefix enforced by `_require_sha256` (`:166`), the
`"<prefix>-" + content_hash[7:23]` id derivation, and — most directly — the
upload shape of `orchestrator/work_context/snapshots.py:89` (`canonical_b64` +
`content_hash` + a divergence verdict against
`/api/v1/work-items/{id}/executions/{execution_id}/snapshot`), which is a
shipped, immutable, content-addressed, one-per-execution store.

Nothing in the repo assembles or stores an evidence record today; `grep -rn
evidence --include=*.py` returns only `context_snapshot.EvidenceRef` and
prompt text.

## Proposed solution

Three additions, no behaviour change to any existing decision.

### 1. `docs/adr/015-execution-evidence-contract.md`

The contract, numbered 015 because 014 is the policy checkpoint (and 011 is
already triple-booked: identity, budget and work-item-resume). It pins the
schema, the id format, the redaction and retention rules, the completeness
vocabulary and the export bytes, and states the two normative boundary rows
that mirror ADR 009 §5 and ADR 011 §6: evidence never re-decides anything, and
no other contract inlines an evidence payload.

### 2. `orchestrator/execution_evidence.py` — stdlib-only contract module

Same shape as its three siblings (`context_snapshot.py`,
`execution_identity.py`, `policy_checkpoint.py`) so the worker, the pollers and
the SDK hooks can all import it, and so `canonical_json`/`hash_bytes` are
shared rather than duplicated.

```
API_VERSION = "evidence.mctl.ai/v1alpha1"
KIND        = "ExecutionEvidence"
ID_PREFIX   = "ev-"          # evidence_id = "ev-" + content_hash[7:23]
EVIDENCE_LINE_PREFIX = "EXECUTION_EVIDENCE"
```

Frozen dataclasses, each with `to_dict` / `from_dict`, and `from_dict`
rejecting unknown keys exactly as `execution_identity._reject_unknown_keys`
does:

| Block | Fields | Source |
|---|---|---|
| `ExecutionBlock` | `trace_id`, `context_id`, `parent_context_id`, `workflow_type`, `step_sequence`, `temporal_workflow_id`, `temporal_run_id`, `argo_workflow_name`, `attempt`, `work_item_id`, `store_execution_id`, `started_at`, `completed_at`, `duration_ms` | `ExecutionContext` + `Correlation`, `work_context.executions` |
| `IdentityBlock` | `actor{type,id,verification}`, `executor{type,id,agent,version,image_ref,binding}`, `environment`, `tenant`, `repository`, `target_repository_sha`, `context_trust` | `Actor`/`Executor`/`Scope`; `context_trust` from `Assertions.asserted_by` |
| `ModelUse[]` | `provider`, `model`, `turns`, `input_tokens`, `output_tokens`, `usage_record_ref` | `AgentRunObserver` vocabulary; `usage_record_ref` empty until ADR 012 lands |
| `ActionRecord[]` | `sequence`, `action_kind`, `operation`, `target_ref`, `target_digest`, `args_digest`, `action_digest`, `policy_version`, `rule_id`, `decision`, `code`, `permitted`, `undecided`, `mutation`, `approval_ref`, `at` | one per `Decision` |
| `ApprovalRecordRef[]` | `receipt_id`, `intent_hash`, `state`, `approver`, `requested_at`, `decided_at`, `consumed_at` | `action_approvals.ApprovalRecord` / `GET /action-approvals/{id}` |
| `ArtifactRecord[]` | `name`, `kind`, `content_hash`, `byte_count`, `locator`, `immutable_ref` | proposal files, branch, PR, merge commit |
| `Evaluation[]` | `name`, `result` (`PASS`/`FAIL`/`SKIP`), `code` | built-in `policy_compliance`, `evidence_completeness`; open for #60 |
| `Completeness` | `status` (`COMPLETE`/`INCOMPLETE`), `gaps[]{code, action_kind, operation, detail_code}` | the checker below |
| `Outcome` | `status` (`SUCCESS`/`FAILURE`/`REFUSED`/`UNDECIDED`/`SKIPPED`), `code` | the run's own result |
| `Retention` | `class_` (`telemetry`/`execution-record`/`gitops`), `expires_after_days` | ADR 009 vocabulary, reused verbatim |

`seal(...) -> ExecutionEvidence` computes `content_hash` over the canonical
JSON of every field except `content_hash`, `evidence_id` and `created_at`, and
derives `evidence_id`. `recompute_content_hash(record)` verifies one, like
`execution_identity.recompute_content_hash`.

**`EvidenceRecorder`** — the in-process collector. Not a new instrumentation
layer: it is fed from the call sites that already feed tracing, so a governed
action is recorded once, by the code that performs it.

- `policy_checkpoint._emit` (the site that already calls
  `tracing.record_policy_decision`, `policy_checkpoint.py:525`) gains one line
  that offers the `Decision` and its `ActionRequest` to the active recorder.
  The recorder is an optional module-level sink, set by the run entrypoint;
  unset, the call is a no-op, so the checkpoint keeps its stdlib-only,
  never-raises contract.
- `tracing.record_artifact` call sites (`run_issue_investigator._trace_published`,
  and the new implementer/shepherd ones) offer the artifact plus the bytes'
  hash.
- `AgentRunObserver` offers `(provider, model, usage)` per completed turn.
- The run entrypoint offers `started_at`, `completed_at` and the outcome.

**`check_completeness(record)`** answers the issue's "detect incomplete
evidence". A recorded mutation is any `ActionRecord` with `mutation=True`
(derived from the `action_kind`, using the same classification
`tracing.classify_command`'s `_GH_MUTATING` set encodes) or any artifact of
kind `branch`/`pull_request`/`merge_commit`. Gap codes:

| Code | Raised when |
|---|---|
| `mutation_without_decision` | a mutation artifact exists with no `ActionRecord` sharing its action digest |
| `approval_unresolved` | `code == approved` but the receipt could not be read |
| `identity_unavailable` | no control-plane context was loadable |
| `ungoverned_transport` | standing gap for the agent's own Bash/`gh` reach (ADR 014 open decision 4) |
| `decision_without_outcome` | a permitted decision whose side effect neither succeeded nor failed in the record |

`policy_compliance` is `PASS` only when every mutation links to a permitted
decision **and** `completeness.status == COMPLETE`.

**Redaction guard.** Evidence is not exported through `GuardedExporter`, so the
module carries its own `_safe(value)` applying the same rules: drop (never
mask, never truncate) any string over 256 characters or matching a credential
shape (`ghp_`/`ghs_`/`github_pat_`, `sk-`, `hv*.`, JWT, PEM, `Bearer `,
`user:pass@`). `target` is admitted as `target_ref` only when it matches a
closed allowlist — a github.com issue/PR URL, `owner/repo`, `owner/repo:<ref>`,
an `aar_`/`we_`/`ex-`/`cs-` id, or an mctl-api operation id — and otherwise is
reduced to `target_digest`. Every hash is `sha256:`-prefixed and validated by
the same `_require_sha256` rule ADR 009 enforces.

### 3. `orchestrator/evidence_store.py` — persistence and retrieval

Tier A, in this slice: the gitops agents-state tree, which is the only durable
store every agent pod already writes to, and which ADR 009 already names as a
retention class.

```
platform-gitops/agents-state/_evidence/
  <workflow_type>/<temporal_workflow_id>/<attempt>-<evidence_id>.json
  by-trace/<trace_id>/<evidence_id>            # pointer file: the record path
```

Every path is unique per record, so two concurrent executions of the same
DevLoop never touch the same file and there is no shared index to serialize on.
Retrieval is a path walk: by workflow id it is one directory listing sorted by
attempt descending; by trace id it is the pointer directory dereferenced. A
thin CLI (`python -m orchestrator.evidence_store show --workflow-id ... |
--trace-id ... | --evidence-id ...`) prints the canonical JSON, which is the
export format: the exported bytes re-hash to `content_hash`, so an exported
document is self-verifying.

Tier B, a follow-up issue, not this slice: an mctl-api evidence store, shaped
byte-for-byte on `work_context/snapshots.py:89` — `POST .../evidence` with
`{canonical_b64, content_hash, evidence_id}`, a divergence verdict on replay,
and `GET /api/v1/evidence/{evidence_id}`. Because the sealed document and its
hash are already the unit of storage, that import is additive and changes no
field. `EvidenceRef{evidence_id, kind}` in a `ContextSnapshot` dereferences
through whichever tier is configured.

**Failure isolation.** `seal`, persist and emit are wrapped so that any failure
logs once (`warn: evidence …`) and returns; the run's own result and exit code
are untouched. This mirrors tracing's "never raises" rule and is the reason
evidence assembly cannot become a new way for a governed run to fail.

## Alternatives

1. **Assemble evidence by querying the trace backend.** The issue's own framing
   ("derived from execution traces") points here, and it needs no new storage.
   Dropped: there is no backend (mctl-gitops#1280 open, all 12 items of the
   #195 live-evidence checklist unticked), spans are dropped under load by a
   bounded queue, and `GuardedExporter` plus `record_policy_decision`
   deliberately strip the target and the digests that make an action
   identifiable. An audit record cannot be built from a sampled, lossy,
   redacted stream that does not yet exist. Traces stay the "what is
   happening" view; `trace_id` is the join key, not the source.
2. **Make mctl-api the store now.** It already holds work items, executions and
   approvals, and `work_context/snapshots.py` proves the pattern. Dropped for
   this slice only: it is a cross-repo dependency with no endpoint today, and
   ADR 011's own experience (`POST /api/v1/agents/executions/context` degrading
   to `mint_local` because the server side may not exist) shows the ordering
   cost. The contract here is written so that store is an import, not a
   redesign.
3. **Extend the proposal's `.status.yaml`.** It is already written per
   proposal, already carries `execution` and `context` blocks
   (`run_issue_investigator.py:1210-1232`), and needs no new file. Dropped: it
   is mutable lifecycle state owned by the implementer/shepherd loop
   (`proposal_state.update_status_file`), it is per proposal rather than per
   execution, and an audit record that a later tick rewrites is not evidence.
   The evidence document is immutable and content-addressed; `.status.yaml`
   gains only an `evidence_ids` pointer list.
4. **A dedicated `EVIDENCE` structured-log line and nothing else.** Cheapest
   option, and consistent with `POLICY_DECISION`. Dropped as the *primary*
   record: pod logs rotate and the issue asks for retrieval by workflow id. The
   line is kept as the summary/greppable surface on top of the durable file.

## Platform impact

- **Migrations:** none. No existing schema changes. `.status.yaml` gains one
  optional `evidence_ids` list, read by nothing that exists today, so old
  status files stay valid (`proposal_state.load_status` tolerates extra keys).
- **Backward compatibility:** `policy_checkpoint`, `execution_identity`,
  `context_snapshot` and `tracing` keep their public signatures. The recorder
  sink is optional and unset by default, so an unwired caller behaves exactly
  as today. `ContextSnapshot.evidence_refs` finally gets a producer, using the
  field that already exists.
- **Dependencies:** none added. The module is stdlib-only; `pyproject.toml` is
  untouched.
- **Resource impact:** one JSON document per execution, dominated by the action
  list; an investigate run makes single-digit governed actions, so roughly
  4-16 KB. At the current run rate the gitops repo grows by a few MB per year.
  No new network call in the happy path; resolving an approval receipt is one
  `GET` per approved action, only when approvals are enabled.
- **Risks and mitigations:**
  - *Evidence becomes a covert payload or secret store.* The same risk ADR 009
    names for snapshots, and the same mitigation: no payload field is declared,
    `from_dict` rejects unknown keys, the `_safe` guard drops long and
    credential-shaped strings, and a test greps a sealed record produced from
    deliberately secret-bearing inputs for zero hits.
  - *A false "COMPLETE".* Mitigated by making `ungoverned_transport` a standing
    gap rather than an assumption of coverage, so a run that could have used
    the agent's shell can never claim full coverage.
  - *Evidence assembly breaking a run.* Mitigated by the never-raises wrapper
    and a test that injects a failure at each recording point and asserts the
    run's result and exit code are unchanged.
  - *Gitops write contention.* Mitigated by deterministic per-record paths and
    no shared index file.
  - *Contract drift against mctl-api.* Mitigated by making the canonical bytes
    plus `content_hash` the unit of storage, exactly as
    `work_context/snapshots.py` does, so the Tier B import is a transport
    change only.
