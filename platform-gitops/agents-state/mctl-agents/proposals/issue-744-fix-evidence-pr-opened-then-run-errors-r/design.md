# Design: issue-744-fix-evidence-pr-opened-then-run-errors-r

## Current state

Code read at commit `102d30a` (tag 1.89.0 release merge).

Evidence producer (`orchestrator/evidence_producer.py`):

- `RunEvidence.pending_pr` (line ~256) holds a PR named without an observed
  head; `RunEvidence.pushed_head_sha` holds the commit this run pushed.
- `note_pushed_head(sha)` (line ~473) stores the head and, if `pending_pr` is
  set, binds `subject` to it.
- `note_subject_pr(repo, number, head_sha)` / `note_subject_pr_url(url, head_sha)`
  (lines ~490-515) bind `subject` to `head_sha or pushed_head_sha`; with neither
  they set `pending_pr`. A later call for the same PR without a head keeps an
  already-bound subject.
- `build()` (lines ~790-810, Amendment 2): `pending_pr` without a head becomes
  `Gap(subject, observation_failed, required=True)`; no subject and no gap
  becomes `Gap(subject, not_applicable, required=False)`.
- Module-level `note(method, *args)` (line ~558) applies to the active run and
  never raises.

Implementer (`orchestrator/run_implementer.py`):

- `implement_one` (line ~4262) wraps `_implement_one` in
  `evidence_producer.run(STAGE_IMPLEMENTER)` and afterwards calls
  `_note_implement_evidence(evidence, result, ...)` (line ~2860), which calls
  `evidence.note_subject_pr_url(result.pr_url, result.pr_head_sha)` only when
  `result.pr_url` is truthy. This is the only place the PR is ever named.
- `_implement_one` new-PR path (lines ~4946-4980): `pr_url =
  _push_and_open_pr(...)`; `_note_pushed_head(target)`; `_note_pushed(target,
  obs)`; `update_status_yaml(ref, "implemented", pr=pr_url, ...)`;
  `_release_claim(...)`; return `ImplementResult(pr_url=pr_url)`. Every
  `except` arm (lines ~4982-5221: `ImplementerFenced`, `ImplementerClaimRefused`,
  `PolicyRefused`, `ImplementerOrphanedSubagent`, `ImplementerOperationTimeout`,
  `RateLimitExhaustedError`, `CalledProcessError`, `SystemExit`, `Exception`)
  returns `pr_url=None`. So a raise from `update_status_yaml` after the PR is
  open drops the PR from evidence -> `not_applicable`. This is the issue's bug.
- `_implement_one` preflight arms (lines ~4481-4546): `_preflight_existing_result`
  may itself open a PR (`_open_pr_for_branch`, line ~3826) or observe one; the
  `open` / `merged` / `closed` arms call `update_status_yaml` before returning
  an `ImplementResult` with `pr_url`, and the `needs-triage` arm calls
  `_mark_needs_triage`. These calls sit outside the main `try`, so a raise
  escapes `_implement_one`; `evidence_producer.run` records the exception as
  the outcome, but `_note_implement_evidence` never runs -> no subject ->
  `not_applicable`. Same class.
- `review_feedback_one` / `_review_feedback_one` (lines ~2897-3300): the PR URL
  is already known before the push (`pre_status = _load_status(...)`,
  `parsed_pr = _parse_pr_url(pre_status["pr"])`, line ~3037). After
  `_push_followup(...)` (line ~3193) it calls `_note_pushed_head(target)`,
  `_note_pushed(target, obs)`, then re-reads `.status.yaml` for `pr_url`
  (line ~3203). A raise from `_note_pushed`'s `_read_remaining_work` or from
  `_load_status` lands in an `except` arm with `pr_url=None`: the pushed head is
  recorded but no PR, so `subject` seals as `not_applicable`. Same class.
- `_note_pushed_head(repo_dir)` (line ~3350) reads HEAD with a 10 s bound and
  calls `evidence_producer.note("note_pushed_head", sha)`; never fatal.

Existing tests: `tests/test_evidence_producer.py` covers the producer
primitives (`test_a_pr_named_without_a_head_is_a_required_subject_gap`,
`test_the_implementer_subject_is_the_commit_it_pushed_not_the_head_at_seal_time`,
`test_note_pushed_head_reads_the_local_clone_whatever_the_flag`) and
`test_the_implementer_binds_the_preflight_head`. No test drives
`implement_one` through a post-PR failure.

Deployed state checked:

- `$MCTL_GITOPS_ROOT` listing: present (README.md, agents-state, services,
  tenants, ...); `services/` holds tenants `admins`, `karabu`, `labs`. Not
  needed further: the change is confined to an orchestrator library and its
  tests and does not touch any deployed configuration, env var, or service.
- `MCTL_EVIDENCE_AMENDMENT_2` (the flag gating `subject` emission) was not
  checked in deployed config; the fix is correct whether it is on or off (with
  it off, `subject` is not emitted at all). Not observed; recorded, not assumed.
- No mctl MCP tools were called; none were needed for this code-only change.

## Proposed solution

Name the PR to the active run evidence at the moment the implementer learns it
exists, not only from the final `ImplementResult`.

1. Add a small helper in `run_implementer.py`:

   ```python
   def _note_subject_pr(pr_url: str | None, head_sha: str | None = None) -> None:
       """Name the PR this run acted on to its evidence as soon as it is known,
       so a later failure seals a bound subject or a required gap, never
       `not_applicable` (mctlhq/mctl-agents#744). Never fatal."""
       if pr_url:
           evidence_producer.note("note_subject_pr_url", pr_url, head_sha)
   ```

2. `_implement_one` new-PR path: immediately after `pr_url =
   _push_and_open_pr(...)`, call `_note_pushed_head(target)` (already there)
   and then `_note_subject_pr(pr_url)`, before `_note_pushed`,
   `update_status_yaml` and `_release_claim`. Ordering does not matter for
   correctness (`note_pushed_head` binds a pending PR and `note_subject_pr`
   folds in `pushed_head_sha`), but placing it right after `_note_pushed_head`
   makes the bound case the common one. If HEAD could not be read, the subject
   stays `pending_pr` and seals as a required `observation_failed` gap.

3. `_implement_one` preflight arms: in the `open`, `merged`, `closed` and
   `needs-triage` arms, call `_note_subject_pr(existing.pr_url,
   existing.head_sha)` before `update_status_yaml` / `_mark_needs_triage`.

4. `_review_feedback_one`: keep the pre-push `pre_status["pr"]` string (the
   value `parsed_pr` is derived from) in a local, and right after
   `_note_pushed_head(target)` call `_note_subject_pr(pre_pr_url)`. The
   post-push re-read for the result surface stays as is; the later
   `_note_implement_evidence` call naming the same PR without a head keeps the
   bound subject (existing `note_subject_pr` rule). If the post-push read yields
   a different URL than the pre-push one, the later call rebinds to it as today
   (no regression).

5. `_note_implement_evidence` is unchanged: on success it re-names the same PR,
   which is a no-op on a bound subject; on failure it no longer needs to.

Why here: the evidence producer already models "PR known, head unknown" as a
required gap; the only defect is that the runner tells it about the PR too
late. Fixing the call site keeps the producer contract and schema untouched.

## Alternatives

- Return the PR URL on failure arms (`ImplementResult(pr_url=pr_url,
  error=...)`). Rejected: `pr_url` drives outcome mapping
  (`_note_implement_evidence`), workdir cleanup in `finally`
  (`result.pr_url is not None` removes the target dir kept for post-mortem),
  exit codes and the shepherd's classification. Overloading it would change
  failure semantics far beyond evidence.
- Make `build()` emit a required `subject` gap whenever `pushed_head_sha` is set
  without a subject. Rejected as the primary fix: it does not name the PR that
  exists (weaker evidence than a bound subject), and it would also change the
  push-without-PR case, which is out of scope (see Open questions in
  requirements.md). It could be a later defence-in-depth change.
- Record the PR inside `_push_and_open_pr` / `_open_pr_for_branch`. Rejected:
  `_open_pr_for_branch` is also used by preflight where the head comes from the
  GitHub API, and binding there would precede `_note_pushed_head`; the call
  sites already have the right context, so the helper is called there.

## Platform impact

- No migrations, no schema change, no config or deploy change. Evidence
  envelopes for affected failure runs change from `subject: not_applicable` to a
  bound `pull_request` subject (or a required gap, making them `incomplete`),
  which is the intended, more accurate reading. Only with
  `MCTL_EVIDENCE_AMENDMENT_2` enabled is `subject` emitted at all.
- Resource impact: one extra in-memory call per path; no network calls.
- Risk: a subject bound on a failed run could be read as "this run succeeded on
  that PR". Mitigation: outcome remains `failed` / `refused` from
  `_note_implement_evidence`; subject only says what the run acted on.
- Risk: helper raising and breaking the run. Mitigation: it goes through
  `evidence_producer.note`, which swallows and logs.
