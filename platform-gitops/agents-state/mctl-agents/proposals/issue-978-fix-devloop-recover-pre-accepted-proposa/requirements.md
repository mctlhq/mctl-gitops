# Recover pre-accepted proposals without approval_ref into a canonical approval grant

## Context

A canonical (Temporal) DevLoop started for an issue whose proposal was already
`accepted` through the standalone GitOps approve path (`approved_by` +
`content_digest`, no `approval.approval_ref`) gets stuck. The loop parks, the
human decides the loop's `aar_` grant, and the loop runs the delegated
`mctl-agents-approve` operation. The approve CWFT treats a proposal that is
already accepted with a matching digest as an idempotent no-op. It exits 0
without writing the grant id, so the grant mctl-api just consumed is never bound
to the record. The implementer then refuses with
`execution not authorized: approved with no verifiable approval grant`
(`orchestrator/proposal_state.py::UNAUTHORIZED_NO_APPROVAL_GRANT`). It writes a
`blocked: execution-unauthorized` marker and opens no PR. The marker's remedy
tells the operator to approve through the DevLoop, which is the path that just
failed. The loop then enters the merge watch with `shepherd_in_loop=true` and
stays Running with no PR to shepherd. Live reproduction: `mctlhq/.github#299`.

The fix must not weaken `execution_authorization` and must not accept a legacy
`approved_by` as authority. A fresh human decision on the DevLoop's canonical
`aar_` grant, bound to the current content digest, has to become the
`approval_ref` that the implementer verifies. Content drift must still
supersede the grant. If the implementation is blocked and no PR exists, the
loop must end in a terminal, actionable state rather than wait as if
shepherd work existed.

## User stories

- AS a platform admin I WANT a DevLoop started over a legacy-accepted proposal to ask me for a fresh decision and then implement it SO THAT legacy approvals can be migrated to canonical authority without hand-editing `.status.yaml`.
- AS a security reviewer I WANT execution authority to come only from a human-decided, content-bound `aar_` grant SO THAT a writable `approved_by` field can never release the implementer.
- AS an operator I WANT a DevLoop whose implementer was blocked without a PR to end with a typed reason SO THAT I am not misled by a Running loop that claims shepherd ownership.

## Acceptance criteria (EARS)

- WHEN a canonical DevLoop reaches its approval park for a proposal whose `.status.yaml` is `status: accepted` with no valid `approval.approval_ref` THE SYSTEM SHALL request (or reuse, by the existing deterministic key) a canonical `aar_` grant bound to the loop's `we_`, `<service>/<slug>` and the current proposal content digest, and park for a human decision without submitting the implementer.
- WHEN the human approves that grant and the delegated `mctl-agents-approve` operation runs against an already-accepted proposal whose recorded `content_digest` equals the expected digest and which records no `approval_ref` THE SYSTEM SHALL write `approval.approval_ref: <aar_ id>` into that record and commit it to gitops main, leaving `status` and the original `approved_by`/`approved_at`/`content_digest` intact. It SHALL also record when the binding happened.
- IF an already-accepted record already carries an `approval_ref` equal to the one supplied THEN THE SYSTEM SHALL treat the approve as an idempotent no-op.
- IF an already-accepted record already carries a different `approval_ref` THEN THE SYSTEM SHALL refuse the approve with the typed code `approval_ref_conflict` and SHALL NOT overwrite it.
- IF an already-accepted record's `content_digest` differs from the expected digest THEN THE SYSTEM SHALL keep refusing with `approval_content_mismatch`, as today.
- WHEN the delegated approve operation reports success THE SYSTEM SHALL read the proposal's `.status.yaml` back from gitops main and, before resolving or submitting the implementer, confirm that `approval.approval_ref` equals the grant id this loop spent.
- IF that read-back finds no `approval_ref`, or a different one, THEN THE SYSTEM SHALL end the loop with the typed outcome `approval_failed` and the detail `approval grant not bound to the proposal record`, and SHALL NOT submit the implementer.
- IF that read-back cannot be read after the activity's retries THEN THE SYSTEM SHALL end the loop with `approval_failed` (unavailable) and SHALL NOT submit the implementer. An unreadable record is never authorization.
- WHILE the implementer evaluates any proposal THE SYSTEM SHALL keep applying `execution_authorization` and `verify_execution_grant` unchanged: `approved_by` without a verifiable, human-decided, consumed, content-matching `aar_` grant authorizes nothing.
- IF the proposal content changes after the grant was requested THEN THE SYSTEM SHALL supersede the grant and ask for a new human decision (the existing #701 freshness path), and a grant whose `artifact_hash` does not match the files SHALL be refused by the implementer (`GRANT_CONTENT_MISMATCH`).
- WHEN, during the merge watch, no PR is resolvable and the proposal's `.status.yaml` carries a `blocked` marker THE SYSTEM SHALL end the watch after `PROPOSAL_TERMINAL_CONFIRM_POLLS` consecutive confirming polls, unless an open PR was observed earlier in the watch. The loop SHALL end with `ended="implementation blocked (<code>)"`, and from that point the `shepherd_in_loop` query SHALL answer false.
- WHILE an execution's history predates the new patch markers THE SYSTEM SHALL replay it unchanged: every new command is guarded by `workflow.patched`.

## Out of scope

- Any change to `execution_authorization`, `verify_execution_grant`, branch protection or rulesets.
- Any fallback that accepts `approved_by` (or `digest_binding: reviewed`) as execution authority.
- Bulk migration of all legacy accepted proposals. Each one recovers through its own DevLoop.
- Changing mctl-api's grant model, consume/execute transitions or approve endpoint.
- The non-canonical (legacy relay) DevLoop approve path.

## Open questions

- The CWFT change lives in mctl-gitops (`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`), not in this repo. The proposal assumes a paired mctl-gitops PR. If cross-repo work is not allowed for this proposal, the mctl-agents half still makes the loop fail closed with an actionable reason, but recovery stays impossible.
- Whether the binding commit should also clear a stale `blocked: execution-unauthorized` marker. Assumed: the CWFT leaves `blocked` in place, and the implementer's existing marker handling re-evaluates on the authorized run. The reviewer should confirm the implementer clears or overwrites a stale marker on success.
- Whether a differing pre-existing `approval_ref` should be refused (chosen here, `approval_ref_conflict`) or replaced by the newer consumed grant.
- The live workflow `dev-loop-mctlhq-.github-299` could not be described from this run (the tool was outside investigate scope). Its current status is unobserved.
