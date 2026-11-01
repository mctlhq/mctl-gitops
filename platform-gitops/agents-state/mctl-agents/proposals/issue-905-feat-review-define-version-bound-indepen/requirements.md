# Version-bound independent review receipts and private evidence ingestion

## Context

Issue mctlhq/mctl-agents#905 (parent epic mctlhq/.github#281, graph in
mctlhq/.github#282) asks for a contract for **independent review** of two
subject classes: spike reports (a report `.md` plus a `measurements/` tree in
a repository at one commit) and agents-state proposals (the triplet plus
`proposed-content.md`). A review request names an exact, digest-bound subject;
a review receipt answers it with exactly one of `PASS`, `CHANGES_REQUESTED`,
`NEEDS_HUMAN`, `UNOBSERVABLE`. A receipt is valid only for the subject bytes
and Git SHAs it was issued for: any change to the report, the measurements,
the proposal bytes, or the source/base commit invalidates it. Evidence that
was not observed is never `PASS`.

Today the only review signal the platform consumes is a GitHub review state
read by `orchestrator/run_shepherd.py` (`GATING_BOTS`, `VERDICT_STATES`),
which is attached to a mutable PR, can survive amendments via re-anchoring,
and is public. The issue requires receipts to live in private, durable,
authenticated storage (mctl-api Tier B, ADR 018 `ExecutionEvidence` model)
and never in public gitops or GitHub comments; manual (human-submitted)
assertions must be attributed by the server, labelled advisory, and must
never satisfy an autonomous independent-worker gate. This proposal is
**planning only** (the issue states "no implementation approval"); it
defines the contract, the digests with golden vectors, the gate, and the
cross-repo ingestion adapter that must exist before any live acceptance is
claimed.

## User stories

- AS an epic owner I WANT a spike report's review to be bound to the exact
  report and measurement bytes at a full commit SHA SO THAT an amended
  report cannot ride on an earlier approval.
- AS a proposal approver I WANT a proposal review receipt bound to the same
  `content_digest_of` digest the `aar_` grant binds SO THAT reviews and
  approvals describe identical bytes with one digest function.
- AS a platform operator I WANT receipts stored privately in mctl-api Tier B
  with server-derived tenant and actor SO THAT findings never leak to public
  gitops and producers cannot forge identity.
- AS a human reviewer I WANT to submit a manual review assertion through an
  authenticated MCTL tool SO THAT my review is recorded, attributed and
  clearly labelled advisory.
- AS a gate consumer (shepherd, DevLoop, epic tooling) I WANT a single
  `evaluate_review_gate` answer (`satisfied` / `stale` / `missing` /
  `unknown` / `advisory_only` / `not_independent`) SO THAT a green GitHub
  state can never stand in for a current independent receipt.

## Acceptance criteria (EARS)

Request and receipt shape
- THE SYSTEM SHALL define `ReviewRequest` and `ReviewReceipt` as frozen,
  sealed documents (`api_version: review.mctl.ai/v1alpha1`) whose
  `content_hash` and derived id (`rr_`/`rc_` + 16 hex) follow the ADR 018
  sealing rules (canonical JSON, unknown keys rejected, bounded strings).
- THE SYSTEM SHALL restrict `ReviewReceipt.outcome` to the closed set
  `PASS`, `CHANGES_REQUESTED`, `NEEDS_HUMAN`, `UNOBSERVABLE`.
- IF a receipt's `outcome` is `PASS` and any rubric criterion is
  `unobserved` or any required input is missing, THEN THE SYSTEM SHALL
  reject the receipt at validation (`review_pass_with_unobserved`).
- THE SYSTEM SHALL select the rubric by subject kind: `spike_report`
  (hypothesis, measurement method, reproducibility, measurement-to-claim
  traceability) or `proposal` (scope, contracts, acceptance criteria,
  rollback), and SHALL reject a receipt whose rubric does not match its
  subject kind.

Digests
- WHEN a proposal subject is digested THE SYSTEM SHALL use
  `orchestrator.proposal_state.content_digest_of` over
  `PROPOSAL_DIGEST_FILES` (remote: `read_proposal_content_digest`) and
  SHALL NOT define a second proposal digest.
- WHEN a proposal receipt is issued THE SYSTEM SHALL record the gitops
  commit the digest was read at and, when one exists, the `aar_` id whose
  `artifact_hash` equals that digest.
- WHEN a spike report subject is digested THE SYSTEM SHALL compute
  `spike_report_digest_v1`: SHA-256 over the versioned header
  `spike_report_digest_v1\n`, followed by, for every regular file under the
  report root (the report `.md` and every regular file under
  `measurements/`), sorted by UTF-8 byte order of its root-relative POSIX
  path, the frame `<len(path)>\n<path>\n<len(bytes)>\n<bytes>`, terminated
  by `<count>\n`, all read at one full 40/64-hex commit SHA.
- IF the inventory contains a symlink, submodule, non-regular entry, a path
  with `..`, `.` segments, backslash, NUL, a leading `/`, a non-UTF-8 name,
  a case-fold collision, a truncated/oversized/non-inlined blob, a
  truncated tree listing, or any read error, THEN THE SYSTEM SHALL refuse
  to produce a digest (typed `SpikeDigestError`) rather than hash a partial
  inventory.
- THE SYSTEM SHALL pin `spike_report_digest_v1` with golden vectors
  (empty measurements, nested measurements, binary bytes, and the
  boundary case where moving bytes between two files changes the digest)
  in `tests/test_review_receipts.py`.

Binding and invalidation
- THE SYSTEM SHALL bind each spike receipt to `repository`, `report_root`,
  full `source_sha`, `base_sha`, `head_sha`, and `inventory_digest`; each
  proposal receipt to `service`, `slug`, `gitops_commit` and
  `content_digest`.
- WHEN the current inventory digest differs from a receipt's
  `inventory_digest` THE SYSTEM SHALL answer `stale`.
- WHEN the current `source_sha` or `base_sha` differs from the receipt's,
  THE SYSTEM SHALL answer `stale` even if the inventory digest is equal.
- WHEN the current proposal `content_digest` differs from the receipt's,
  THE SYSTEM SHALL answer `stale` (proposal supersession reused from
  mctl-agents#701 for agents-state proposal bytes only).
- IF the caller cannot observe the current revision or digest, THEN THE
  SYSTEM SHALL answer `unknown` and SHALL NOT make a decision.
- WHILE evaluating a review gate THE SYSTEM SHALL ignore GitHub review
  states, `commit_id` of a review, stale-review dismissal, and any GitHub
  check status as inputs.

Ingestion, authentication and storage
- THE SYSTEM SHALL store requests and receipts only in mctl-api Tier B
  (private, durable) and SHALL NOT write receipts, raw findings, or rubric
  text into public gitops, GitHub reviews, or GitHub comments.
- WHEN a worker receipt is submitted THE mctl-api adapter SHALL accept it
  only from an enrolled reviewer producer principal, SHALL verify the
  request id, nonce/attempt id, subject binding and fencing epoch against
  the open request, and SHALL derive tenant and actor server-side.
- WHEN a manual assertion is submitted THE mctl-api adapter SHALL accept it
  only from a direct authenticated human MCTL principal, SHALL derive
  tenant and actor from the token, SHALL bind it to an exact subject and a
  single-use nonce, and SHALL store it with `mode: manual`,
  `assurance: advisory`.
- IF a submitted receipt replays a consumed nonce, names a closed or
  superseded request, carries a subject binding that differs from the
  request, or claims a producer identity the token does not carry, THEN THE
  adapter SHALL refuse it with a typed error and store nothing.
- THE SYSTEM SHALL NOT infer reviewer identity or model independence from
  a model name, a pasted string, or an OAuth client name (#891 separation).

Independence
- IF the receipt's actor equals any author/committer actor of the reviewed
  revision (spike head commits since base, or the proposal's writer
  execution), THEN THE gate SHALL answer `not_independent`.
- THE SYSTEM SHALL NOT treat actor inequality as proof of independence,
  because agent commits carry the operator's identity: a worker request
  SHALL carry the authoring execution id, and IF it is absent THEN THE gate
  SHALL answer `unknown`.
- IF the reviewer's execution lineage (execution id, attempt id, shared
  trace/parent root) overlaps the authoring execution's, THEN THE gate
  SHALL answer `not_independent` even when the actors differ.
- IF the only current receipts are `mode: manual`, THEN THE gate SHALL
  answer `advisory_only` for an autonomous independent-worker gate.
- IF the reviewer execution id equals the authoring execution id or shares
  its attempt id, THEN THE gate SHALL answer `not_independent`.

Reviewer capabilities
- THE reviewer execution profile SHALL grant read-only access to the
  bound subject inputs and the receipt-submission tool only, and SHALL hold
  no GitHub write, merge, label, lifecycle-approval or approval-signal
  capability.
- THE SYSTEM SHALL NOT post any GitHub review or comment from the reviewer,
  and in particular SHALL NOT post as `chatgpt-codex-connector[bot]` or any
  login in `run_shepherd.GATING_BOTS`.

Regression
- WHEN a `.github` spike PR is amended after carrying a `claude[bot]`
  `APPROVED` review THE gate SHALL answer `stale` regardless of GitHub's
  review or check state.

## Out of scope

- Implementation approval and `agents:intake` labelling (the issue is
  planning-only).
- Deduplicating reusable reviews (mctlhq/.github#283), inline-comment
  re-anchoring (mctl-agents#336), the disputed same-head finding
  (mctl-gitops#1176).
- OAuth-based model/client inference (#891).
- Changing `run_shepherd` merge gating in this proposal; wiring the gate
  into shepherd or DevLoop is a later, separately approved slice.
- Measuring owner decision time (#848, still open).
- The explainer (#670/#846/#847), which stays advisory.

## Open questions

- Tier B on `origin/main` has only the `evidence:write`-gated
  `POST /api/v1/evidence/records` and no user-write path (design.md
  "Deployed state checked"); the new adapter is therefore required. That
  the NEW routes answer on the deployed build is a live-acceptance
  condition (task 9), not an assumption.
- RESOLVED (owner, 2026-11-01): receipts are a NEW Tier B resource
  (`/api/v1/review-receipts`) that references `ExecutionEvidence` by `ev-`
  id and `ArtifactRef`; `SUBJECT_KINDS` is not extended.
- Exact author set for spike independence: all commit authors and
  committers in `base_sha..head_sha`, or also the PR opener? Proposal uses
  the union of all three.
- RESOLVED in design: `spike_report_digest_v1` no longer fixes a report
  file name. The subject carries `report_root` and `report_path` as binding
  fields and the digest covers that one file plus `measurements/`. Where
  spikes actually keep their reports (none exist in `mctlhq/.github`
  today) is chosen by the first consumer, without changing the digest.
- Who enrols reviewer producers (admin MCP tool vs gitops-declared
  principal); proposal assumes a gitops-declared service principal like
  `service:mctl-agents-evidence`.
