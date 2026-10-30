# Require a reviewed-content digest for every proposal approval flip

## Context
`mctl-agents-approve` (`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`) flips a proposal's `.status.yaml` from `proposed` to `accepted`. It accepts an optional `expected_content_digest`. When the parameter is set (the Temporal DevLoop `aar_` path, mctl-agents#681), the flip refuses unless the proposal files still hash to that digest. When it is empty (the direct `mctl_trigger_approve` path, or a hand-submitted Workflow), the template hashes whatever bytes are present at flip time and records that hash as `approval.content_digest`. The template's own comment calls this "the #658 behaviour". The recorded digest then proves only that nothing changed after the flip. It does not prove that a human reviewed those bytes. An edit pushed between the human's review and the flip becomes the approved content, and the record cannot tell the two cases apart.

The issue (G3 / P2 of the mctlhq/.github#182 decision-assurance audit) asks for the invariant `reviewed_hash=A + approve + current_hash=B (A != B) -> hard fail`. It also asks that no empty or unbound mode can produce an approval binding from bytes first seen at execution time. This proposal removes the unbound mode from the CWFT, which is the last writer before gitops, so the invariant holds whatever caller submits the Workflow. It also adds typed refusal evidence, a helper that lets a human compute the digest of the bytes they reviewed, and regression tests that run the template's real script.

## User stories
- AS a platform admin approving a proposal directly I WANT the approval to bind to the exact bytes I reviewed SO THAT an edit pushed after my review can never ride on my approval.
- AS an auditor I WANT every `accepted` record created from now on to carry a digest that a caller supplied before the decision SO THAT `approval.content_digest` always means "the content the human decided on".
- AS the DevLoop (`aar_` path) I WANT my behaviour unchanged SO THAT the #681 guarantees and the idempotent-retry semantics keep working.
- AS an operator debugging a failed approve I WANT a typed refusal code (unbound vs mismatch vs malformed) SO THAT I can tell a missing digest apart from a changed proposal without reading shell logs.

## Acceptance criteria (EARS)
- WHEN `mctl-agents-approve` runs with an empty `expected_content_digest` THE SYSTEM SHALL refuse with refusal code `approval_content_unbound`, exit non-zero, and leave `.status.yaml` untouched. No commit is made, and this holds whatever the proposal's current status is.
- WHEN `expected_content_digest` is set and the proposal files hash to a different value THE SYSTEM SHALL refuse with refusal code `approval_content_mismatch` before any edit to `.status.yaml`. The message SHALL name both the reviewed and the current digest.
- WHEN `expected_content_digest` is not of the form `sha256:<64 lowercase hex>` THE SYSTEM SHALL refuse with refusal code `approval_content_digest_malformed` before any edit.
- WHEN `expected_content_digest` matches the current content of a `proposed` proposal THE SYSTEM SHALL flip it to `accepted` and record `approval.content_digest` equal to the supplied digest byte for byte. It SHALL also record `approval.digest_binding: 'reviewed'`.
- WHEN the proposal is already `accepted` and the supplied digest equals the recorded `approval.content_digest` THE SYSTEM SHALL exit 0 with result `noop`, keeping the idempotent-retry behaviour.
- IF the proposal is already `accepted` with a different recorded digest, or with none THEN THE SYSTEM SHALL refuse with `approval_content_mismatch`.
- WHILE any refusal path runs THE SYSTEM SHALL emit exactly one machine-readable line `approve_refusal: code=<code> service=<service> slug=<slug> expected=<digest|-> current=<digest|->` on stderr. It SHALL also expose the code as the `refusal_code` output parameter of the `flip-status` step.
- WHEN an admin needs the digest of the proposal bytes they reviewed THE SYSTEM SHALL provide `scripts/proposal-content-digest.py <proposal-dir>` (and a `--rev <commit>` form). It SHALL produce the same framing as the CWFT and as mctl-agents `proposal_state.proposal_content_digest`.
- IF a future change restores execution-time self-binding (an empty digest flips, or the computed digest is recorded without being compared) THEN THE SYSTEM SHALL fail CI through `tests/test_cwft_mctl_agents_approve_digest_binding.py`.

## Out of scope
- Changing mctl-api so that `mctl_trigger_approve` and the `mctl-agents-approve` operation require `expected_content_digest` up front (`internal/operations/registry.go`, `internal/mcp/server.go`). That is a companion change in mctlhq/mctl-api. This proposal is safe to land first, because the CWFT then refuses the unbound request with a typed code.
- The DevLoop `aar_` grant flow: grant creation, decision, consumption, and `approval_content_unbound` on unbound grants in mctl-api. Its inputs to the CWFT are unchanged.
- The incident-responder path (P3), which writes `status: accepted` directly without this CWFT and without `control.requires_human_approval`.
- Rewriting historical `accepted`/`merged` records. Existing records keep their `approval` blocks as written.
- Persisting refusal evidence in the mctl-api audit store. mctl-api already records a failed `mctl-agents-approve` operation, and attaching the typed code to that row is part of the mctl-api companion change.

## Open questions
- Does any legitimate caller still submit `mctl-agents-approve` without a digest? Audit-log evidence (`mctl_list_recent_operations`) shows that the only `mctl-agents-approve` executions in the visible window were DevLoop grant spends, and they carry `expected_content_digest`. The window is the last 50 operations, so older or infrequent direct callers are not ruled out. This proposal assumes there are none and removes the mode without a compatibility flag. If one appears, the refusal is typed and the fix is to supply a digest, not to restore the mode.
- The audit row for the 2026-10-19 grant spend shows `grant_ref`, but the resulting `.status.yaml` (`agents-state/mctl-api/proposals/issue-700-...`) has no `approval.approval_ref`. Either the deployed mctl-api does not yet forward `approval_ref`, or it forwards it under another name. This does not block this proposal, which does not depend on `approval_ref`. It should be confirmed in the mctl-api companion change.
- Should `approval.digest_binding` be read by mctl-agents (`human_approval_satisfied()`) as a hard requirement for new records? This proposal only writes it. Making the implementer require it is a follow-up in mctl-agents.
