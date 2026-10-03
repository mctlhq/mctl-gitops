# Tasks: issue-352-feat-lifecycle-ownership-add-executor-cl

- [ ] 1. Add the claim contract to `orchestrator/lifecycle/contract.py`: frozen
      `Executor`, `ExecutionClaim`, `ClaimAnswer` dataclasses (every field
      defaulted), the closed verdict constants `CLAIM_HELD_BY_ME`,
      `CLAIM_HELD_BY_OTHER`, `CLAIM_FENCED`, `CLAIM_UNCLAIMED`, `CLAIM_UNKNOWN`,
      the closed `HOLDING_CLAIM_STATES` / `FREE_CLAIM_STATES` sets, and
      `OWNER_IMPLEMENTER` beside the five existing `OWNER_*` constants —
      DoD: `ClaimAnswer.may_execute` is true only for `CLAIM_HELD_BY_ME`;
      `ExecutionClaim.from_payload` returns `None` on a malformed body rather
      than an all-empty record; a claim state in neither closed set classifies
      as `CLAIM_UNKNOWN`; exported from `orchestrator/lifecycle/__init__.py`.

- [ ] 2. Add `claim_answer_from` and `idempotency_key_for` to `contract.py`
      (depends on 1) — DoD: `idempotency_key_for` is
      `sha256("{kind}|{id}|{phase}|{owner_epoch}|{attempt}|{version}|{action}")`
      with no clock and no random source; `claim_answer_from` maps 2xx-with-record
      to a verdict, 2xx-without-record to `CLAIM_UNKNOWN`, 404-on-write to
      `CLAIM_UNKNOWN`, 409 carrying `code: "fenced"` to `CLAIM_FENCED`, any other
      409 to `CLAIM_HELD_BY_OTHER`, and everything else to `CLAIM_UNKNOWN`; it
      lives next to `answer_from` and there is no second copy anywhere.

- [ ] 3. Add `orchestrator/lifecycle/claim.py` with the synchronous
      `ClaimClient` (depends on 2) — DoD: reuses the https pin, the no-redirect
      opener and the `OwnershipUnavailable`-to-unknown conversion from
      `client.py`; exposes `acquire`, `renew`, `check`, `record`, `release`
      against `/api/v1/lifecycle/claims/*`; sends `lease_seconds` and never
      `lease_until`; raises `ValueError` on an empty `attempt`, matching
      `OwnershipClient.progress`'s empty-`evidence` guard; no HTTP call is made
      when `rollout.records_writes()` is false.

- [ ] 4. Add claim event emission to `claim.py` (depends on 3) — DoD: a
      `LOG_PREFIX = "lifecycle-claim:"` in the style of `shadow.LOG_PREFIX`; one
      line per decision over the closed vocabulary
      `acquired | rejected | renewed | released | expired | fenced`; every line
      carries entity kind, entity id, phase, owner epoch, entity version,
      executor type, executor id, attempt id and claim id; emission never raises.

- [ ] 5. Add the `execution_claim` activity to
      `orchestrator/temporal/activities/lifecycle.py` (depends on 2) — DoD: flat
      `ExecutionClaimRequest` / `ExecutionClaimResult` dataclasses with every
      field defaulted; a `_CLAIM_PATHS` map; the same `rollout.records_writes()`
      short-circuit the ownership activity applies at lines 209-230; it calls
      `contract.claim_answer_from` and performs no classification of its own;
      it returns an unknown verdict rather than raising on any failure; the name
      does not collide with `DevLoopWorkflow.lifecycle_claim`, the existing
      ownership query at `dev_loop.py:674`.

- [ ] 6. Register `execution_claim` in `orchestrator/temporal/worker.py`
      (depends on 5) — DoD: registered on the same queue as
      `lifecycle_ownership`; `tests/test_worker_roles.py` and
      `tests/test_worker_isolation.py` still pass.

- [ ] 7. Wire claims into `run_implementer.py` (depends on 3) — DoD: a named
      constant replaces the bare `timedelta(minutes=130)` at line 1782; the
      attempt id resolves `WORKFLOW_UID`, then the deterministic
      `sha256("{service}|{slug}|{owner_epoch}|{attempt_ordinal}")` fallback, and
      never `uuid.uuid4()`; the run refuses to acquire a claim when no
      deterministic identity is derivable; a claim is acquired beside the
      existing `attempt` write at line 1786 and released or recorded on every
      terminal arm that currently stamps `finished_at`
      (`_mark_needs_triage` at 1595-1618 and the success path at 1852-1861).

- [ ] 8. Fence the two push sites in `run_implementer.py` (depends on 7) —
      DoD: `_push_followup` (line 921) becomes
      `git push --force-with-lease=<branch>:<claimed sha> origin <branch>`, the
      explicit-SHA form and never the bare flag; `_push_and_open_pr` (line 1660)
      keeps `-u` on the create path and takes the lease only on the
      adopt-existing-branch path guarded by `_branch_exists_on_origin`
      (line 915); both call `ClaimClient.check()` immediately before invoking
      git and abort without mutating on `CLAIM_FENCED`.

- [ ] 9. Add the `fenced` outcome to the shepherd's follow-up vocabulary
      (depends on 8) — DoD: `"fenced"` added to the `FollowupKind` literal at
      `run_shepherd.py:643` with a new sentinel exit code beside 42/43/44/46/47;
      it does not consume a `MAX_REVIEW_ATTEMPTS` slot, does not count toward
      `harness_failures` or `refusals`, and produces its own operator-facing log
      line distinct from `transient`.

- [ ] 10. Make `run_shepherd._attempt_is_fresh` the union of the claim and the
      yaml lease (depends on 3) — DoD: held if an active claim exists OR the yaml
      lease is unexpired; the yaml branch additionally compares the holder
      instead of only `expires_at`; at rollout mode `only` the yaml read is
      skipped; both existing call sites (lines 2282 and 2847) keep working.

- [ ] 11. Wire the DevLoop handoff (depends on 5, 6) — DoD: `_watch_pr`'s
      `finally` (`dev_loop.py:2349-2364`) issues `handoff-start` to
      `OWNER_SHEPHERD` instead of a bare `release` when the watch ends
      non-terminally, using the activity op that already exists at
      `lifecycle.py:105` and has no caller today; terminal PRs still go
      `terminal`; all claim and handoff calls sit behind a new
      `workflow.patched("lifecycle-claims")` marker, separate from
      `lifecycle-ownership`; no HTTP originates in `@workflow.defn` code.

- [ ] 12. Add the delegated-claim path for steward-owned services (depends on
      3, 9) — DoD: the shepherd may take a claim whose `executor` is itself while
      `owner_epoch` belongs to the steward's ownership row, and the ownership row
      does not move; merge authority is re-evaluated at the merge boundary
      through `policy.merge_authority_for`, `run_shepherd._service_mode` and
      `NEVER_MERGE_SERVICES` (line 552), and holding a claim contributes nothing
      to it.

- [ ] 13. Document the phase-2 surface (depends on 1-12) — DoD: ADR-010's
      implementation-map row for phase 2 is marked shipped, with the wire status
      chosen for a fence, the proposal `entity_version` hash input, the
      deterministic attempt fallback and the two lease-duration env vars
      (`LIFECYCLE_CLAIM_LEASE_SECONDS_IMPLEMENT`,
      `LIFECYCLE_CLAIM_LEASE_SECONDS_REVIEW`) recorded; `.env.example` and
      `README.md` list the new variables; no new rollout switch is introduced.

## Tests

- [ ] T1. Deliberate shepherd/pr-steward race: two `ClaimClient.acquire` calls
      against a stubbed store for the same `(entity, phase, owner_epoch,
      entity_version)` produce exactly one `CLAIM_HELD_BY_ME`, and the loser's
      answer names the winning executor and has `may_execute` false.
- [ ] T2. Stale worker after handoff: a claim taken at epoch N is fenced once the
      ownership row reaches epoch N+1; the pre-handoff executor's `check()`
      returns `CLAIM_FENCED` and no git subprocess is invoked. Proved by mutation
      in both directions — the same call at epoch N still succeeds.
- [ ] T3. Head-change fence: a claim pinned to head A returns `CLAIM_FENCED` once
      head B is current, and `_push_followup` is not reached.
- [ ] T4. `--force-with-lease` is passed with the explicit
      `<branch>:<sha>` form on the follow-up path, and the bare flag is never
      used; asserted on the argv the runner receives.
- [ ] T5. `merge_pr` still passes `--match-head-commit` with `pr.head_sha`
      (`run_shepherd.py:2221`) — a regression guard, since the merge side is the
      half that is already correct.
- [ ] T6. Idempotency determinism: `idempotency_key_for` returns identical output
      across a simulated Temporal replay and a simulated pod restart, contains no
      clock or random input, and a second `record` under the same key returns the
      first recorded outcome without repeating the mutation.
- [ ] T7. No UUID: `run_implementer` never mints `uuid.uuid4()` for an attempt id,
      and refuses to acquire a claim when no deterministic identity is derivable.
- [ ] T8. Lease expiry does not transfer ownership: an expired claim permits a
      new acquire only when the ownership row still names an owner at the
      expected epoch; an expired claim against a superseded epoch is refused.
- [ ] T9. Unknown never licenses execution: for every failure the transport can
      produce — 500, 503, timeout, malformed JSON, a 200 carrying an HTML error
      page, an unrecognised claim state — the verdict is `CLAIM_UNKNOWN` and
      `may_execute` is false.
- [ ] T10. Rollout modes: at `off` no claim HTTP call is made; at `observe` a
      fence is logged and blocks nothing; at `enforce` a fence blocks the push
      and the merge while leaving reads and escalation permitted; at `only` the
      yaml lease read is gone.
- [ ] T11. No lifecycle HTTP call originates in workflow code, extending the
      existing assertion to the claim path; `tests/test_workflow_replay.py`
      replays a history recorded before `workflow.patched("lifecycle-claims")`
      without a non-determinism error.
- [ ] T12. Claim holding grants no merge authority: a delegated claim on a
      `NEVER_MERGE_SERVICES` or `fix-only` service still refuses the merge.
- [ ] T13. Event completeness: each of `acquired | rejected | renewed |
      released | expired | fenced` emits a line carrying entity, phase, owner
      epoch, executor and attempt identifiers.
- [ ] T14. `claim_answer_from` and `answer_from` classify the shared status codes
      identically, so the two classifiers cannot drift.
- [ ] T15. `uv run pytest`, `uv run ruff check orchestrator config tests` and
      `uv run mypy` all pass, per `CONTRIBUTING.md`.

## Rollback

Three independent levers, smallest blast radius first.

1. **Set `LIFECYCLE_ROLLOUT_MODE=observe`.** Claims are still acquired and fences
   still logged, but nothing is blocked. This reverses the only behaviour change
   users can feel — a blocked push or merge — without a deploy, and keeps the
   evidence stream that says whether the fence was right.
2. **Set `LIFECYCLE_OWNERSHIP_REQUIRED=false`.** The documented break-glass,
   read only through `rollout.blocks_on_unknown()`. Use this when mctl-api is
   unreachable and the fail-closed inversion is stalling pushes: it restores
   fail-open behaviour while leaving `enforce` in place for answers that do
   arrive.
3. **Set `LIFECYCLE_ROLLOUT_MODE=off`.** No claim HTTP call is made at all and
   the system returns to the phase-1 behaviour exactly: the 130-minute yaml
   lease, `_attempt_is_fresh` on `expires_at` alone, and `_dev_loop_owns` as the
   ownership answer.

A code revert is a last resort and is safe but not instant. The Temporal side is
gated by `workflow.patched("lifecycle-claims")`, so reverting the commit leaves
in-flight executions replaying the patched branch — the same attrition
`tests/test_patch_memoization.py` documents for the `lifecycle-ownership` flip.
Prefer mode 3 and let the executions drain.

The `--force-with-lease` change is the one piece that should **not** be reverted
under any of the above: it is strictly safer than the unconditional push it
replaces, is independent of the claim store, and a push with a stale lease fails
closed rather than clobbering. If the claim is unavailable, pass the lease from
the locally observed head rather than dropping the flag.
