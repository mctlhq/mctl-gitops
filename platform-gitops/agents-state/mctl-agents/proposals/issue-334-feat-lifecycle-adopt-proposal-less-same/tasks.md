# Tasks: issue-334-feat-lifecycle-adopt-proposal-less-same

All tasks land in one PR against `mctlhq/mctl-agents`. No sibling repository is
touched; no task requires a human step or a post-merge production action.

- [ ] 1. Widen `PRSnapshot` with the two fields adoption needs — add
  `head_branch: str = ""` and `is_cross_repository: bool = False` to the
  dataclass in `orchestrator/run_shepherd.py` (L958-975), and request
  `headRefName isCrossRepository headRepositoryOwner{login}
  baseRepository{owner{login}}` in the `_fetch_pr_snapshot` GraphQL query
  (L1352), populating both from the response. — DoD: both fields default so
  every existing `PRSnapshot(...)` construction site and every fixture in
  `tests/test_run_shepherd.py` still constructs; `_fetch_pr_snapshot` sets
  `is_cross_repository` true when `isCrossRepository` is true OR the head
  repository owner differs from the base repository owner; `pytest
  tests/test_run_shepherd.py` passes unchanged.

- [ ] 2. Add the flag surface (depends on 1) — in a new
  `orchestrator/pr_adoption.py`, add `adoption_enabled()` reading
  `SHEPHERD_ADOPT_PRS` (default false), `adopt_repos()` reading
  `SHEPHERD_ADOPT_REPOS` through the existing
  `run_shepherd._service_set_from_env` (default empty), and
  `max_prs_per_tick()` reading `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` (default 1).
  Document all three, commented out, in `.env.example`. — DoD: with none of the
  three set, `adoption_enabled()` is False and `adopt_repos()` is empty; an
  unrecognised repo name in the allowlist produces the same `warn:` line
  `_service_set_from_env` already emits and is dropped.

- [ ] 3. Implement the `PRRef` record type (depends on 2) — in
  `orchestrator/pr_adoption.py`, add `ADOPTED_DIRNAME`, `PRREF_FILENAME`,
  `PRREF_KIND`, `slug_for(number)`, `record_dir(state_dir, service, number)`, a
  `PRRef` dataclass subclassing `run_shepherd.ProposalRef` whose
  `__post_init__` points `status_path` at `.prref.yaml` and whose `mode` is
  `run_shepherd.FIX_ONLY` at construction, plus `load_prref` / `write_prref`
  built on `orchestrator/proposal_state.py::load_status` and
  `update_status_file`, and `append_evidence(...)` capped at `MAX_EVIDENCE = 20`
  entries with the finding body truncated. — DoD: a round-trip writes and reads
  the schema in design.md §1 including `kind: pr-ref`; no new YAML writer is
  introduced; `PRRef.mode` is `FIX_ONLY` regardless of what the caller passes;
  an evidence append on an unchanged PR leaves the file byte-identical.

- [ ] 4. Implement the ownership and safety gates (depends on 3) — in
  `orchestrator/pr_adoption.py`, add pure-ish predicates:
  `_is_fork(pr)` (from task 1's fields), `_is_agents_branch(head_branch)`
  (`feat/agents-` prefix), `_owned_by_proposal(state_dir, pr_url)` (one cached
  pass over `<svc>/proposals/*/.status.yaml` for a matching `pr:`),
  `_devloop_free(service, slug)` wrapping `run_shepherd._dev_loop_owns_answer`
  and requiring `LEGACY_FREE` (fail closed on `LEGACY_UNKNOWN`),
  `_mode_permits(service)` requiring `run_shepherd._service_mode(service) !=
  SKIP`, and `_store_permits(entity)` consulting
  `lifecycle.client.OwnershipClient().get(...)` on
  `PHASE_REVIEW_REMEDIATION` only when `lifecycle.rollout.computes_new_answer()`
  and admitting only `UNOWNED` / `OWNED_BY_ME`. — DoD: each gate is a separate
  function with its own refusal reason string; every gate refuses on an
  unanswerable input; no gate raises out of the discovery pass.

- [ ] 5. Implement discovery (depends on 4) — add
  `discover_adoptable(state_dir, *, budget)` running the pipeline in design.md
  §2: per allowlisted repo, `gh api graphql` for open PRs, apply the gates in
  order, then `run_shepherd._fetch_pr_snapshot` + `read_codex_review` +
  `fresh_findings_p1_p2(pr.head_sha, pr.head_pushed_at)`, and adopt only PRs
  with at least one fresh P1/P2 from `GATING_BOTS`. On adoption write
  `.prref.yaml` with the first evidence entry and — when
  `rollout.records_writes()` — call `OwnershipClient().acquire(...,
  proposal_ref="", policy_ref=lifecycle.policy.policy_ref_for(service))`,
  treating any ownership failure as "do not adopt". Also add re-discovery of
  existing `.prref.yaml` records. — DoD: returns at most `max_prs_per_tick()`
  refs; a PR failing any gate is skipped with a one-line reason on stdout; an
  unreachable ownership store yields zero adoptions and zero exceptions.

- [ ] 6. Thread the record through the shepherd (depends on 5) — in
  `orchestrator/run_shepherd.py`: add an optional `status_path` parameter to
  `find_pr_for_proposal` (L1320) and pass `ref.status_path` from `process_one`;
  add `adopted_pr: str | None = None` to `apply_followup` (L2062) which
  substitutes `--adopted-pr <pr-url>` for `--slug` in the subprocess argv
  (L2124-2136) and changes nothing else; in `main()`, after
  `_filter_dev_loop_owned` and only when adoption is enabled and neither
  `--reconcile` nor `--slug` is set, extend `refs` with
  `pr_adoption.discover_adoptable(...)`; add a `--adopt-prs` CLI override; and
  print the `mctlhq/mctl-gitops#1278` durability warning when adoption is
  enabled. — DoD: with `SHEPHERD_ADOPT_PRS` unset, `main()`'s argv to the
  implementer and its stdout are byte-identical to today; `_print_summary`
  renders a `PRRef` without change.

- [ ] 7. Accept a proposal-less target in the implementer (depends on 3) — in
  `orchestrator/run_implementer.py`: add `--adopted-pr <pr-url>`, valid only
  with `--review-feedback` and mutually exclusive with `--slug` (exit 2
  otherwise); add `build_adopted_ref(state_dir, pr_url)` returning a
  `ProposalRef` whose `proposal_dir` is
  `<state-dir>/<service>/adopted-prs/pr-<n>/` and whose `status_path` is
  `.prref.yaml`, exiting 2 when the record is absent; add a pre-clone
  `isCrossRepository` re-check that exits 2 on a fork. — DoD: `--adopted-pr`
  never creates a record; `find_accepted_proposals` is not called on this path;
  a fork URL exits 2 before `_clone_target` runs.

- [ ] 8. Parameterise the branch and the prompt (depends on 7) — change
  `review_feedback_one(ref, bundle, dry_run=False, branch=None)` so
  `branch = branch or f"feat/agents-{ref.slug}"` (replacing the literal at
  L1664), and `_build_prompt(ref, review_feedback=None, branch=None,
  adopted=False)` so the hardcoded branch at L1299 uses the same value and the
  adopted variant drops the `$PROPOSAL_DIR` spec-file sentence and the
  `Proposal: platform-gitops/agents-state/...` trailer in favour of
  `PR: <url>` and the subject `fix(review): address P1/P2 findings on
  <repo>#<n>`. The adopted call passes `head_branch` read from `.prref.yaml`.
  — DoD: with `branch=None` and `adopted=False` both functions produce output
  identical to today (pinned by a test); the existing claim acquisition at
  L1711-1719, the refusal marker handling and
  `--force-with-lease={branch}:{old_head}` are unmodified.

- [ ] 9. Documentation (depends on 6, 8) — extend the README "Tier 3 — PR
  shepherd" section with an "Adopted PRs" subsection covering the record path,
  the three env vars, the FIX_ONLY-always rule, and the
  `mctlhq/mctl-gitops#1278` dependency; add a short note to
  `docs/adr/010-lifecycle-ownership-contract.md`'s pilot-path-4 paragraph
  recording that discovery shipped as `orchestrator/pr_adoption.py` with the
  shepherd acquiring directly as `shepherd` rather than via `reconciler`, and
  why. — DoD: `uv run python -m tools.check_diagrams` (or the repo's existing
  docs check) still passes; no ADR decision is changed, only annotated.

## Tests

New file `tests/test_pr_adoption.py` plus additions to
`tests/test_run_shepherd.py`, following the existing conventions there (GitHub
API and the implementer subprocess mocked at the module boundary, `.prref.yaml`
round-tripping through a real `tmp_path`).

- [ ] T1. End-to-end adoption: a manual/ChatGPT-authored open same-repo PR with
  a fresh P1 from `claude[bot]` on the current head and no proposal is
  discovered, adopted (`.prref.yaml` written with evidence), driven through
  `process_one` to `address-review`, the implementer fork is asserted to carry
  `--adopted-pr` and NOT `--slug`, and a follow-up tick with a clean review
  ends in `defer-merge` with no `merge_pr()` call.
- [ ] T2. Fork refusal: `is_cross_repository` true is never adopted, and
  `--adopted-pr` on a fork URL exits 2 before `_clone_target` is called.
- [ ] T3. Ownership races, one test per gate — (a) a `.status.yaml` elsewhere
  carrying the same `pr:` URL; (b) a `feat/agents-*` head branch; (c)
  `_dev_loop_owns_answer` returning `LEGACY_OWNED`; (d) it returning
  `LEGACY_UNKNOWN` (must also refuse — the opposite of the sweep's fail-open);
  (e) `_service_mode` resolving `SKIP`; (f) the ownership store answering
  `OWNED_BY_OTHER`; (g) the store answering `UNKNOWN`. Each asserts zero
  adoptions and no `.prref.yaml` written.
- [ ] T4. Head-SHA pinning: a P1 whose `created_at` predates `head_pushed_at`
  does not trigger adoption; a record whose stored `head_sha` is stale is
  re-pinned and `refusals` reset before any action.
- [ ] T5. Bounds: `review_attempts` reaching `MAX_REVIEW_ATTEMPTS`,
  `harness_failures` reaching `MAX_HARNESS_FAILURES`, and `refusals` reaching
  `MAX_REFUSALS` each flip the `.prref.yaml` to `review-stuck` with evidence;
  exit codes 47 / 48 / 49 / 46 charge exactly what they charge for a proposal.
- [ ] T6. Never merges: `decide()` on an adopted ref always returns
  `defer-merge` and never `merge`, for a FULL-mode service as well as a
  fix-only one; `process_one`'s defensive re-check also refuses.
- [ ] T7. Default-off equivalence: with `SHEPHERD_ADOPT_PRS` unset,
  `_discover_refs` output, `main()`'s stdout and the implementer argv are
  identical to the pre-change behaviour; `discover_adoptable` is never called.
- [ ] T8. Backward-compat pins: `review_feedback_one(..., branch=None)` still
  resolves `feat/agents-<slug>`, and `_build_prompt(ref, review_feedback=b)`
  with no new kwargs produces the exact string it produces today.
- [ ] T9. Evidence schema: an adoption and a fix attempt each append an entry
  carrying `repo`, `pr`, `head_sha`, `reviewer`, `finding`, `attempt`,
  `owner_type`, `outcome`; the list is capped at `MAX_EVIDENCE` and the finding
  body is truncated.
- [ ] T10. Per-tick cap: with three adoptable PRs and
  `SHEPHERD_ADOPT_MAX_PRS_PER_TICK=1`, exactly one implementer fork occurs and
  the skipped candidates are logged rather than silently dropped.

## Rollback

The feature is inert by construction, so rollback is graded rather than
all-or-nothing:

1. **Immediate, no deploy.** Unset `SHEPHERD_ADOPT_PRS` (or empty
   `SHEPHERD_ADOPT_REPOS`) in the shepherd CronWorkflow's env. Discovery stops
   on the next tick; no code path touches `adopted-prs/` again. Since every
   other change is a defaulted keyword parameter or a defaulted dataclass
   field, the shepherd and the implementer behave exactly as they did before
   this PR.
2. **Narrower.** Remove a single repository from `SHEPHERD_ADOPT_REPOS` to stop
   adopting there while leaving the rest on; or set
   `SHEPHERD_ADOPT_MAX_PRS_PER_TICK=0` to keep discovery observable while
   performing no fix attempts.
3. **Code revert.** Revert the PR. The only durable artefacts are
   `adopted-prs/**` directories in `mctl-gitops` — and while
   `mctlhq/mctl-gitops#1278` has not landed, none exist, because the CWFT does
   not stage that path. If it has landed, `git rm -r` the
   `agents-state/*/adopted-prs/` directories; nothing else in the pipeline
   reads them.
4. **In-flight PRs.** A follow-up commit already pushed to an adopted PR stays
   on that PR. It is an ordinary commit on the PR's own branch, reviewable and
   revertable by the repository's normal process; no branch was created and no
   PR was opened, so there is nothing to clean up on GitHub.
