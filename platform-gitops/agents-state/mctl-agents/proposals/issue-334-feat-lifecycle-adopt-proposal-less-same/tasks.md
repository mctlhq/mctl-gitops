# Tasks: issue-334-feat-lifecycle-adopt-proposal-less-same

- [ ] 1. Add the `PRRef` dataclass and its record IO in a new module
  `orchestrator/pr_adoption.py`: fields `repo, number, service, head_ref,
  head_sha, owner_type, attempt, refusals, refusals_head, outcome, record_dir`
  plus derived `record_path = record_dir / ".prref.yaml"`, an `entity` property
  returning `EntityRef.for_pull_request(repo, number, head_sha)`, the closed
  `outcome` vocabulary (`adopted, review-fixing, merge-ready, review-stuck,
  merged, closed, released`) with a `TERMINAL_OUTCOMES` frozenset, and
  `load_prref` / `update_prref` built on
  `orchestrator.proposal_state._write_status_atomic` so writes are atomic,
  mode-preserving and merge-don't-clobber. Records live at
  `<state_dir>/<service>/adopted-prs/pr-<number>/.prref.yaml` — a sibling of
  `proposals/`, never inside it. — DoD: module imports with no dependency on
  `run_shepherd`; round-trip of every field passes; an unknown `outcome` value
  raises rather than being coerced; `_discover_refs` on a state dir containing
  an `adopted-prs/` tree returns exactly the same refs as before.

- [ ] 2. Add `append_attempt(prref, *, head_sha, reviewer, finding, owner_type,
  outcome)` to `orchestrator/pr_adoption.py` (depends on 1): appends one entry
  to the record's `attempts:` list carrying `at, attempt, head_sha, reviewer,
  finding, owner_type, outcome`, where `finding` is a bounded digest of the
  triggering finding body (reuse the `MAX_NOTES_CHARS = 700` bound and the
  `" ".join(body.split())[:N]` normalisation from
  `run_shepherd._read_refusal_reason`). — DoD: the evidence fields required by
  the issue (repo, PR, head SHA, triggering reviewer/finding, attempt, owner
  type, outcome) are all readable from a single record file; the list is
  append-only across writes; a finding body containing YAML metacharacters or
  10 KB of text round-trips safely and truncated.

- [ ] 3. Implement `discover_adoptable_prs(state_dir, *, service_filter=None,
  allowlist, excluded_paths)` in `orchestrator/pr_adoption.py` (depends on 1).
  Enumerate `gh pr list --repo mctlhq/<service> --state open --json
  number,headRefName,headRefOid,isCrossRepository,isDraft,url,author` for each
  allowlisted service whose `run_shepherd._service_mode` is not `SKIP`, then
  apply the nine rejection filters in design.md order (`fork`, `draft`/
  `not-open`, `implementer-branch`, `proposal-owned`, `devloop-owned`,
  `steward-owned`, `policy-excluded`, `owned`/`store-unknown`,
  `no-blocking-findings`), reusing `run_shepherd._gh_api_json`, `_parse_pr_url`,
  `_discover_refs(..., reconcile=True)` for the proposal index,
  `_dev_loop_owns_answer`, `lifecycle.policy.default_owner_for`,
  `OwnershipClient.get_many(KIND_PULL_REQUEST, PHASE_REVIEW_REMEDIATION, ids)`,
  `_fetch_pr_snapshot`, and `read_codex_review(...).fresh_findings_p1_p2(
  pr.head_sha, pr.head_pushed_at)`. Each rejection emits one
  `adoption: skip <repo>#<n> reason=<slug>` line. — DoD: `blocks_others` true
  and `UNKNOWN` both reject; the store read is one batched call per tick, not
  one per PR; only `run_shepherd.GATING_BOTS` findings can make a PR adoptable
  and `COPILOT_BOT` findings cannot; `isCrossRepository` PRs are rejected before
  any snapshot or review read happens.

- [ ] 4. Implement `adopt(prref_candidate, *, client, dry_run)` (depends on 2, 3):
  `acquire(entity, PHASE_REVIEW_REMEDIATION, Owner(OWNER_RECONCILER, id),
  proposal_ref="", policy_ref=policy.policy_ref_for(service))`, then write the
  record with `outcome: adopted` and the first attempt entry, then
  `handoff_start(..., to=Owner(OWNER_SHEPHERD, id))`. Abort and write nothing
  unless `acquire` answers `OWNED_BY_ME`. — DoD: no proposal directory,
  `.status.yaml`, `requirements.md`, `design.md` or `tasks.md` is created on any
  path; `proposal_ref` is never sent as a non-empty value; a failed or `UNKNOWN`
  `acquire` leaves the filesystem untouched; an interrupted adoption leaves the
  row in `handing-off`, which `lifecycle.reconciler.classify` already resolves as
  `ACTION_COMPLETE_HANDOFF` / `handoff-incomplete`.

- [ ] 5. Add the explicit-branch review-feedback path to the implementer
  (depends on 1). Add `--pr-repo`, `--pr-number`, `--pr-branch` to
  `run_implementer`'s argparse as an alternative to `--service`/`--slug` in
  `--review-feedback` mode, and an `adopted_review_feedback_one(...)` that
  mirrors `review_feedback_one` but takes the branch from the argument instead
  of `f"feat/agents-{ref.slug}"`, clones by repo, and calls a `_build_prompt`
  variant carrying an explicit `branch` and no `$PROPOSAL_DIR` reference (the PR
  description and the findings bundle are the whole specification). Reuse
  `_branch_exists_on_origin`, `_checkout_existing_branch`,
  `_stage_implementer_agent`, `_capture_head_sha`, the refusal-marker protocol
  and `_review_feedback_exit_code` unchanged. — DoD: a missing branch on origin
  still exits `EXIT_BRANCH_MISSING_ON_ORIGIN` and never creates the branch; no
  `gh pr create` is reachable from this path; `--pr-branch` together with
  `--slug` is a usage error; the prompt for an adopted PR contains no
  `$PROPOSAL_DIR` or `platform-gitops/agents-state/.../proposals/` string.

- [ ] 6. Extend `run_shepherd.apply_followup` with keyword-only `branch: str |
  None = None` and `pr_url: str | None = None` (depends on 5). When `branch` is
  set, build the argv with `--pr-repo/--pr-number/--pr-branch` and no
  `--service/--slug`; otherwise emit today's argv byte-for-byte. Temp-file
  naming, the refusal-out file, the `finally` cleanup and the
  `FollowupSubprocessError` exit-code classification are unchanged. — DoD:
  `tests/test_run_shepherd.py::test_apply_followup_invokes_implementer_subprocess`
  and `::test_apply_followup_propagates_state_dir` pass unmodified; the new argv
  is asserted by its own test; both temp files are unlinked on every exit path.

- [ ] 7. Implement `process_adopted_one(prref, *, state_dir, dry_run)` in
  `orchestrator/pr_adoption.py` (depends on 2, 4, 6). Reuse
  `_fetch_pr_snapshot`, `read_codex_review`, `read_copilot_review`,
  `trigger_review` and `decide(pr, review, fix_only=True)` — `fix_only=True`
  unconditionally, so `merge` is unreachable and `merge_pr` is never called.
  Complete a pending `handoff_complete` before any mutation. Map decisions:
  `address-review` -> re-read the head, abort if it moved, acquire an
  `ExecutionClaim` pinned to `entity_version=head_sha` with executor
  `OWNER_IMPLEMENTER`, fork via `apply_followup(..., branch=prref.head_ref)`,
  then `attempt += 1`, `outcome: review-fixing`, and
  `progress(..., evidence="pushed <old>-><new> for <reviewer> <severity>")`;
  `defer-merge` -> `outcome: merge-ready` plus a log line naming
  `policy.merge_authority_for(service)`; `flip-to-merged`/`flip-to-rejected` ->
  `outcome: merged`/`closed` plus `terminal(...)`; `wait` -> no write.
  Honour `MAX_REVIEW_ATTEMPTS`, `MAX_HARNESS_FAILURES` and `MAX_REFUSALS`
  (with `refusals_head` resetting the refusal budget on a head change), and on
  the review-attempt cap write `outcome: review-stuck` plus `terminal(...,
  reason=...)`. Release ownership with `outcome: released` whenever a proposal
  or live DevLoop has appeared for the PR. — DoD: `merge_pr` is not referenced
  anywhere in the new module; `progress` is called only after a push that moved
  the head; a head change between `decide` and mutation aborts the attempt; once
  the outcome is terminal no further implementer fork occurs.

- [ ] 8. Wire the entry point and flags (depends on 3, 7). Add `--adopt-prs`
  (env `SHEPHERD_ADOPT_PRS`, default off), `SHEPHERD_ADOPT_SERVICES` (empty
  allowlist by default, parsed with `run_shepherd._service_set_from_env`) and
  `ADOPTION_EXCLUDED_PATHS` (default `.github/workflows/**`, `charts/**`,
  `**/values.yaml`) to `run_shepherd.main()`. The adoption pass runs after
  proposal-backed processing, its per-PR errors are caught and logged, and its
  results append to `_print_summary`. Below `lifecycle.rollout.ENFORCE` it
  discovers, records and logs but never forks the implementer; `--dry-run`
  writes nothing at all; `--reconcile` and `--adopt-prs` together is a usage
  error. Document the flags in `README.md` under "Tier 3 — PR shepherd" and in
  `.env.example`. — DoD: with the flag unset, a full `pytest
  tests/test_run_shepherd.py tests/test_run_shepherd_attempt_fresh.py` run
  passes unmodified and no adoption code path executes; `--dry-run --adopt-prs`
  creates no file, makes no `acquire` call and forks nothing.

- [ ] 9. Companion `mctl-gitops` change and reviewer-identity follow-up
  (depends on 1, 8). Open a PR in `mctl-gitops` extending the shepherd CWFT's
  commit step to stage `':(glob)*/adopted-prs/*/**'` alongside the existing
  proposal pathspec, and add a CI assertion that the two pathspecs together
  cover everything the shepherd may write under `agents-state/`. Confirm whether
  the issue's "agy" reviewer is a distinct bot login; if so, add it to
  `run_shepherd.GATING_BOTS` with a fixture. — DoD: an adopted PR's `.prref.yaml`
  appears in `mctl-gitops` `main` after a real tick; the production
  `SHEPHERD_ADOPT_PRS` flag is not enabled until this PR merges, because an
  uncommitted record resets `attempt` to 0 every tick and the bound stops being
  a bound.

## Tests

- [ ] T1. `tests/test_pr_adoption_record.py` — `PRRef` round-trip, closed
  `outcome` vocabulary rejecting unknown values, atomic write leaving the old
  file intact on a serialisation error, `append_attempt` preserving prior
  entries and truncating a 10 KB finding body, and a state dir with
  `adopted-prs/` producing byte-identical `_discover_refs` output.
- [ ] T2. `tests/test_pr_adoption_discovery.py` — the end-to-end happy path the
  issue names: a manual/ChatGPT-authored same-repo PR in `mctl-gitops` with a
  fresh `claude[bot]` P1 on the current head, no proposal, no DevLoop, no
  steward -> adopted -> `address-review` -> fix push -> fresh clean review ->
  `outcome: merge-ready` with `merge_pr` never called. Fixtures at the module
  boundary, following `tests/test_run_shepherd.py`'s `tmp_path` worktree style.
- [ ] T3. Ownership races, one test each: live DevLoop (`_dev_loop_owns_answer`
  = owned) -> no adoption; a proposal whose `pr:` names the PR -> no adoption;
  `_service_mode` = `SKIP` / `default_owner_for` = `pr-steward` -> no adoption;
  store answers `OWNED_BY_OTHER` -> no adoption; store answers `UNKNOWN` ->
  no adoption with reason `store-unknown`; a proposal appearing for an
  already-adopted PR -> `release` plus `outcome: released`; `acquire` not
  answering `OWNED_BY_ME` -> nothing written.
- [ ] T4. Fork and policy exclusion: `isCrossRepository: true` is rejected with
  reason `fork` and no snapshot, review, record or subprocess results; a PR
  touching `.github/workflows/**` is rejected with reason `policy-excluded`; a
  service absent from `SHEPHERD_ADOPT_SERVICES` is never enumerated.
- [ ] T5. Head-SHA pinning: a P2 re-anchored onto the current head but with
  `created_at` older than `head_pushed_at` never triggers adoption or a fix
  (the `mctl-agents#359`/`#336` mechanism); a head that moves between `decide`
  and mutation aborts the attempt with no fork and no record mutation; the
  `ExecutionClaim` and the recorded attempt carry the same `entity_version`.
- [ ] T6. Bounded remediation: five consecutive `address-review` cycles ->
  `outcome: review-stuck` plus `terminal(...)` and no sixth fork; a refusal
  sentinel (`EXIT_DELIBERATE_NO_OP`) does not charge a review attempt; a harness
  failure (`EXIT_ORPHANED_SUBAGENT`) charges `harness_failures` and caps at 3; a
  head change resets `refusals` via `refusals_head`.
- [ ] T7. Merge authority: `decide` is always called with `fix_only=True` for an
  adopted PR (asserted on the call, not only the outcome), a clean adopted PR in
  a `FULL`-mode service still yields `merge-ready`, and `run_shepherd.merge_pr`
  is not reachable from `orchestrator/pr_adoption.py` (import-level assertion).
- [ ] T8. Flag and rollout gating: flag off -> zero adoption calls and existing
  shepherd tests unchanged; `rollout.mode()` in `observe` -> records written and
  decisions logged but no implementer fork; `--dry-run --adopt-prs` -> no file,
  no `acquire`, no fork; one adoption candidate raising does not prevent the
  remaining candidates or the proposal-backed results from being summarised.
- [ ] T9. Evidence completeness: after adopt + one fix + terminalisation, a
  single `.prref.yaml` contains repo, PR number, head SHA per attempt,
  triggering reviewer login, finding digest, attempt ordinal, owner type and
  outcome; and every rejection path emits exactly one reason-slug log line, so
  "zero adoptions" is distinguishable from "never ran".

## Rollback

Three independent levels, cheapest first.

1. **Unset the flag.** `SHEPHERD_ADOPT_PRS` (or removing every entry from
   `SHEPHERD_ADOPT_SERVICES`) disables discovery, records, ownership calls and
   forks on the next tick. Every task above is additive and defaulted, so the
   proposal-backed shepherd path, `decide`, `apply_followup` and
   `review_feedback_one` behave exactly as before with the flag off — T8 asserts
   this. No Temporal workflow code changes, so no history incompatibility and no
   `workflow.patched` marker to unwind.
2. **Drop the rollout stage.** Setting `LIFECYCLE_ROLLOUT_MODE=observe` keeps
   discovery and evidence while making mutation unreachable, which is the
   diagnostic position: adoption volume and candidate quality stay observable
   while nothing can touch a branch.
3. **Revert the code.** `git revert` of the mctl-agents PR removes
   `orchestrator/pr_adoption.py` and the additive parameters. Residue to clean
   up afterwards, none of which breaks anything if left: (a) `adopted-prs/`
   directories in `mctl-gitops` — inert, read by nothing else, removable with a
   single gitops commit; (b) lifecycle ownership rows for
   `(pull-request, review-remediation)` with `proposal_ref: ""` — release or
   terminalise them with the audited recovery operation so the reconcile sweep
   does not keep reporting `handoff-incomplete`; (c) the `mctl-gitops` CWFT
   pathspec from task 9, which is harmless on its own and can be reverted
   separately.

In-flight PRs at rollback time are left exactly where they are: the fix commits
already pushed remain on their branches and are merged or closed by the
repository's normal human process, because adoption never granted merge
authority and never opened a PR of its own.
