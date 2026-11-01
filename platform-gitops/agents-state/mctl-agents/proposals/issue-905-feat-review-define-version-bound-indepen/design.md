# Design: issue-905-feat-review-define-version-bound-indepen

## Current state

Proposal digest (reused, not duplicated):
- `orchestrator/proposal_state.py` defines `PROPOSAL_DIGEST_FILES =
  ("requirements.md", "design.md", "tasks.md", "proposed-content.md")` and
  `content_digest_of(files)`: a length-framed SHA-256 (`<name>\n<len>\n<bytes>`,
  absent file = `<name>\n-\n`), prefixed `sha256:`. Pinned by
  `tests/test_proposal_digest.py` / `tests/test_proposal_digest_remote.py`.
- `orchestrator/temporal/activities/proposals.py::read_proposal_content_digest`
  resolves gitops `main` to one 40-hex SHA and reads every file at that SHA;
  any non-404 failure, symlink, directory or non-inlined blob raises
  `ProposalListingError` ("content that could not be read has no digest").
- The `aar_` action approval (`orchestrator/action_approvals.py`,
  `ApprovalRecord.artifact_hash`) binds the same digest;
  `orchestrator/approval_evidence.py` refuses a grant whose `artifact_hash`
  differs from the files on disk.
- Proposal supersession (mctl-agents#701): `orchestrator/temporal/workflows/dev_loop.py`
  `GRANT_FRESHNESS_PATCH`, `GRANT_FRESHNESS_INTERVAL`, `MAX_GRANT_SUPERSEDES`
  supersede a pending grant when the proposal bytes change. It is scoped to
  agents-state proposal bytes; nothing invalidates anything for spike
  reports. Typed approval refusals (#702) live at `dev_loop.py` ~L1114-1170;
  execution authorization (#703) is `proposal_state.py` ~L296-320.

Spikes:
- `orchestrator/spike_issue.py` classifies a source issue as spike via title
  or a SpikeDefinition manifest under `mctlhq/.github` `roadmap/spikes`. It
  has no notion of a report digest or a review.

Evidence (ADR 018, `docs/adr/018-execution-evidence-envelope-contract.md`,
`orchestrator/execution_evidence.py`):
- Tier A seals an `ExecutionEvidence` envelope; Tier B (persistence,
  retrieval) is owned by mctl-api. Amendment 2 adds `subject`
  (`SUBJECT_KINDS = pull_request, issue, branch, release, work_item`),
  `provenance.authority` (`observed > derived > asserted`), `supersedes`,
  and `resolve_current()` with `CURRENT_STATES = current, no_evidence,
  stale_revision, unknown_revision, ambiguous`.
- `orchestrator/evidence_producer.py` posts envelopes to
  `POST /api/v1/evidence/records` with `MCTL_EVIDENCE_WRITER_TOKEN`
  (`service:mctl-agents-evidence`, write-only). Amendment 2 blocks are gated
  by `MCTL_EVIDENCE_AMENDMENT_2`. There is **no** user-write endpoint and no
  review-verdict field; `subject` has no `proposal` or `spike_report` kind.

Review gating today:
- `orchestrator/run_shepherd.py`: `REVIEW_BOT = "claude[bot]"`,
  `CODEX_CONNECTOR_BOT = "chatgpt-codex-connector[bot]"`,
  `GATING_BOTS = (REVIEW_BOT, CODEX_CONNECTOR_BOT)`, `VERDICT_STATES =
  {"APPROVED", "CHANGES_REQUESTED"}`. Review is read from public GitHub
  review state on a PR; any process able to post as a gating login enters
  the gate. `orchestrator/pr_adoption.py` reuses `GATING_BOTS`.

Deployed state checked:
- `mcp__mctl__mctl_get_service_config(team=admins, service=mctl-api)`:
  error "service not found: admins/mctl-api". mctl-api is not a tenant
  catalogue service under `admins`; its deployed Tier B schema could not be
  observed. Not observed is not absent.
- `$MCTL_GITOPS_ROOT`-equivalent `/workdir/mctl-gitops/platform-gitops/services/admins/`:
  lists `mctl-agents-worker`, `mctl-agents-worker-exec`,
  `mctl-agents-worker-implement`, `mctl-design`, `mctl-docs`,
  `mctl-support`, `mctl-web`, `umami`; no `mctl-api` directory. A grep for
  `MCTL_EVIDENCE` / `EVIDENCE` in those values files returned nothing, so
  whether `MCTL_EVIDENCE_AMENDMENT_2` is on in production was not observed
  here (earlier proposals issue-735/issue-744 in agents-state claim the CWFTs
  set it to `"true"`; that is a claim, not an observation by this run).
- Consequence: the existence and shape of any review-capable Tier B write
  path is **unknown**; this design plans the adapter explicitly (task 6) and
  makes live acceptance conditional on observing it deployed.

## Proposed solution

A new contract, ADR 025 "Independent review receipts", plus one pure Tier A
module and one cross-repo mctl-api adapter. Nothing touches `run_shepherd`
gating in this proposal.

### 1. Documents (`orchestrator/review_receipts.py`, Tier A, pure)

Modelled on `execution_evidence.py`: frozen dataclasses, `from_dict`
rejecting unknown keys, `seal()` as the only identity filler,
`canonical_json`/`hash_bytes` reused from `execution_evidence`.

`ReviewSubject` (tagged by `kind`):
- `spike_report`: `repository` (owner/name), `report_root` (validated POSIX
  path, no `..`), `source_sha`, `base_sha`, `head_sha` (full 40/64 hex,
  lowercase), `inventory_digest` (`sha256:`), `digest_version =
  "spike_report_digest_v1"`.
- `proposal`: `service`, `slug`, `gitops_commit` (full SHA),
  `content_digest` (from `content_digest_of`), optional `approval_ref`
  (`aar_` regex reused from `approval_evidence.GRANT_REF_RE`).

`ReviewRequest`: `subject`, `rubric` (`spike_v1` | `proposal_v1`, must
match subject kind), `mode` (`worker` | `manual`), `author_actors` (the
set of principals/commit identities that authored the revision),
`authoring_execution_id` (optional `we_`/`ex-`), `nonce` (server-minted,
opaque), `created_at`. Id `rr_` + 16 hex of content hash.

`ReviewReceipt`: `request_id`, `subject` (must equal request's, compared
by canonical bytes), `outcome` in `PASS | CHANGES_REQUESTED | NEEDS_HUMAN |
UNOBSERVABLE`, `criteria[]` each `{id, status: met|unmet|unobserved}` with
ids from the rubric's closed list, `findings_ref` (an `ArtifactRef`-shaped
hash pointer to the private findings blob; never inline text), `mode`,
`assurance` (`independent` | `advisory`, derived: `manual` => `advisory`),
`reviewer_actor` and `reviewer_execution_id` (filled by the server on
ingest; Tier A only validates shape), `attempt_id`, `nonce`,
`evidence_ref` (optional `ev-` id of the reviewer's `ExecutionEvidence`).
Validation: `PASS` requires every criterion `met`; any `unobserved`
criterion forces `UNOBSERVABLE` or `NEEDS_HUMAN`.

Rubrics (closed criterion ids, versioned constants):
- `spike_v1`: `hypothesis_stated`, `method_described`,
  `measurements_present`, `measurements_reproducible`,
  `claims_traceable_to_measurements`, `limitations_stated`.
- `proposal_v1`: `scope_bounded`, `contracts_specified`,
  `acceptance_testable`, `rollback_defined`, `matches_issue`.

### 2. `spike_report_digest_v1`

`spike_report_digest(entries: Sequence[InventoryEntry]) -> str`, pure, plus
an async reader `read_spike_inventory(repository, report_root, sha)` using
the GitHub git trees API (`recursive=1`) at a full SHA, rejecting
`truncated: true`, and blobs by sha (verifying the git blob sha of the
returned bytes). Canonical bytes:

```
"spike_report_digest_v1\n"
for entry in sorted(entries, key=path.encode("utf-8")):
    f"{len(path_bytes)}\n" + path_bytes + "\n" + f"{len(content)}\n" + content
f"{len(entries)}\n"
digest = "sha256:" + sha256(...).hexdigest()
```

Inventory = the single report file `<report_root>/report.md` (name fixed
by the rubric version; open question if spikes use another name) plus every
regular file under `<report_root>/measurements/`. Tree modes other than
`100644`/`100755` (symlink `120000`, submodule `160000`) are a typed
refusal, as are path anomalies, case-fold collisions, oversize blobs, and
any non-200 read. Golden vectors live in
`tests/fixtures/review/spike_digest_vectors.json` and are asserted literally.

### 3. Gate (`evaluate_review_gate`, pure)

Inputs: the live subject as just observed by the caller (or an
`observation_failed` marker), the candidate receipts from Tier B, the
gate's `required_assurance` (`independent` | `any`). Order:
1. live revision/digest unknown -> `unknown` (never decide).
2. pool = receipts whose subject canonical bytes equal the live subject;
   for spikes this compares `source_sha`, `base_sha`, `head_sha`,
   `inventory_digest` and `report_root`; for proposals `content_digest`
   (the `gitops_commit` is provenance only, since equal bytes at a later
   commit are the same proposal under #701 semantics). Receipts for other
   values -> historical; if the pool is empty but historical exist ->
   `stale`, else `missing`.
3. drop receipts whose `reviewer_actor` is in `author_actors` or whose
   `reviewer_execution_id`/`attempt_id` equals the authoring one ->
   if nothing remains, `not_independent`.
4. if `required_assurance == independent` and only `advisory` remain ->
   `advisory_only`.
5. latest remaining receipt by server ingest order: `PASS` -> `satisfied`;
   otherwise return its outcome (`changes_requested`, `needs_human`,
   `unobservable`).
GitHub review state is not an input; the function signature has no slot
for it.

### 4. Tier B adapter (cross-repo, mctl-api; explicit part of this proposal)

New resource in mctl-api, alongside `internal/evidence`:
- `POST /api/v1/review-requests` (admin or DevLoop service principal):
  stores a request, mints `nonce`, records `author_actors` it derives from
  GitHub (commit authors/committers in `base..head`, PR opener) or the
  proposal writer execution.
- `POST /api/v1/review-receipts`: two auth paths.
  - Worker: token of an enrolled `service:mctl-agents-reviewer` principal
    (separate from `service:mctl-agents-evidence`); body carries
    `request_id`, `nonce`, `attempt_id`, lifecycle fencing epoch (ADR 010)
    and the receipt; server checks request open, subject bytes equal,
    nonce unused (single-use, consumed atomically), epoch current, then
    fills `reviewer_actor` from the token and `assurance=independent`.
  - Manual: direct human MCTL OAuth principal (not a service/agent token,
    mirroring the "human admins only" rule of `mctl_approve_dev_loop`),
    tenant and actor derived server-side, `mode=manual`,
    `assurance=advisory`, same nonce/subject checks.
  - Typed refusals: `review_nonce_replayed`, `review_request_closed`,
    `review_subject_mismatch`, `review_producer_not_enrolled`,
    `review_fence_stale`, `review_pass_with_unobserved`. Nothing stored on
    refusal.
- `GET /api/v1/review-receipts?subject_kind=&...` (admin + work-item
  scoped), complete pool or typed 5xx, never truncated.
- Storage: append-only table with immutability trigger, as
  `execution_evidence`; findings blob in a private column/object, never
  served publicly.
- MCP tool (mctl-api) `mctl_submit_review_assertion` for manual mode;
  `mctl_get_review_gate` read tool.

The reviewer's own run seals an ordinary `ExecutionEvidence` envelope
(through `evidence_producer.py`) with `artifacts=[ArtifactRef(kind=
"review-receipt", content_hash=<receipt hash>)]`, linking ADR 018 refs and
provenance without a parallel telemetry system.

### 5. Reviewer execution profile (later slice, contract defined here)

An `ExecutionProfile` `independent-review` whose tool allowlist is:
read subject inputs (GitHub contents read at a pinned SHA, gitops read),
and `submit_review_receipt`. No `gh` write, no merge, no label, no
`mctl_approve_dev_loop`, no comment posting. The policy checkpoint
(ADR 014) refuses any `github_write` action kind for this profile. The
reviewer never authenticates as any `GATING_BOTS` login; a test asserts the
profile contains no GitHub write token.

## Alternatives

1. **Use GitHub review state with `commit_id` + stale-review dismissal.**
   Dropped: the issue explicitly rejects it; `commit_id` re-anchors, a
   review survives amendments that do not dismiss, results are public, and
   anyone who can post as a gating login enters `run_shepherd`'s gate.
2. **Extend `ExecutionEvidence` (`SUBJECT_KINDS += proposal, spike_report`,
   a `review` block) instead of a new resource.** Viable but dropped as the
   primary path: it would bump ADR 018's hash-neutral `v1alpha1` shape,
   cannot carry nonce/request lifecycle, and evidence is "grants nothing"
   by contract whereas a gate needs request-bound, fenced, single-use
   submission. Receipts instead reference evidence by `ev-` id and
   `ArtifactRef`. Kept as an open question for the owner.
3. **Store receipts in agents-state gitops next to the proposal.** Dropped:
   public repository; the issue forbids receipts/raw findings in public
   gitops, and gitops commits carry no authenticated producer identity.

## Platform impact

- Migrations: new mctl-api tables (`review_requests`, `review_receipts`),
  append-only; no change to `execution_evidence`. No change to existing
  proposals, `aar_` grants or `content_digest_of` (golden vectors
  untouched).
- Backward compatibility: purely additive; nothing consumes the gate until
  a separately approved wiring slice. `run_shepherd` behaviour unchanged.
- Resources: digest reads are one tree call plus one blob call per file
  per evaluation; cap inventory size (`MAX_SPIKE_FILES = 512`,
  `MAX_SPIKE_BYTES = 32 MiB`) with typed refusal past it.
- Risks and mitigations:
  - Digest drift between Python and any other reader -> golden vectors,
    and mctl-api re-derives nothing (it compares bytes the caller bound);
    the gate's live read is done by the consumer.
  - Forged producer -> enrolled service principal + nonce + fence,
    server-derived actor; manual path labelled advisory structurally.
  - Unknown deployed Tier B capability -> live acceptance is blocked on
    observing the adapter deployed (task 9); until then the module is
    offline-testable only.
  - Same-human self-certification via manual mode -> `not_independent` by
    actor equality and `advisory_only` regardless.
