# Design: issue-735-fix-evidence-never-bind-a-pr-subject-to

## Current state

Evidence collection (`orchestrator/evidence_producer.py`):

- `RunEvidence` holds `subject`, `subject_observed_at`, `pending_pr`
  (`(repository, number)` of a PR "whose head the producer reads itself at
  seal time", line ~259) and `pushed_head_sha`.
- `note_subject_pr(repository, number, head_sha=None)` (~line 480) binds
  `SubjectRef(kind="pull_request", revision=head_sha or pushed_head_sha)` when
  either is a full SHA; otherwise it sets `subject=None` and
  `pending_pr=(repository, number)`. Note it also *discards* an already-bound
  subject when called again without a head.
- `note_subject_pr_url(url)` (~line 500) parses a PR URL and calls
  `note_subject_pr` with no head.
- `note_pushed_head(sha)` records the commit this run pushed.
- `read_pr_head_sha(repository, number)` (~line 623) runs
  `gh api repos/<r>/pulls/<n> --jq .head.sha` with `READ_TIMEOUT_SECONDS`.
- `PrHeadReader = Callable[[str, int], str]` (line 176).
- `build(..., read_pr_head=None, ...)` (~line 726). Under Amendment 2, lines
  ~801-815: if `subject is None and pending_pr is not None` it uses
  `pushed_head_sha or (read_pr_head or read_pr_head_sha)(repository, number)`
  and binds the subject to the result, or on failure adds
  `Gap("subject", "observation_failed", True)`. This is the seal-time read the
  issue removes.
- `produce(..., read_pr_head=None, ...)` (~line 1027) forwards it.
- The module comment at lines ~105-114 counts "the PR head read at seal time"
  in the tail budget; `READ_TIMEOUT_SECONDS` is also used by
  `read_execution_request` (~line 643) and must stay.

Gap vocabulary (`orchestrator/execution_evidence.py:151-158`): `GAP_CODES =
{not_produced, store_unavailable, not_applicable, redacted_out, undecided,
observation_failed}`; `UNKNOWN_GAP_CODES = {observation_failed}` (always
required). There is no `not_observed` code.

Callers:

- Shepherd: `run_shepherd.py:1842` sets `head_sha = pr.get("headRefOid") or ""`;
  `process_one` calls `evidence_producer.note("note_subject_pr", pr.repo,
  pr.number, pr.head_sha)` at line 3777. An empty head falls into
  `pending_pr` and so into the seal-time read.
- Implementer: `run_implementer.py:2889-2890` calls
  `evidence.note_subject_pr_url(result.pr_url)` with no head.
  `_note_pushed_head` (line 3347, called at 3191 and 4944 after a push) is the
  only head source. `_preflight_existing_result` (line 3743) reads
  `headRefOid` for every existing PR into `ExistingResult.head_sha`, but the
  `open` / `merged` / `closed` / `needs-triage` branches at lines ~4487-4545
  return `ImplementResult(pr_url=existing.pr_url)` and drop the head, so these
  runs hit the seal-time read today. `ImplementResult` (line 809) has no head
  field.
- Investigator: `run_issue_investigator.py:3396` records issue subjects only.

Tests (`tests/test_evidence_producer.py`): `:449` unreadable head -> gap,
`:463` seal-time read binds the subject (the behaviour being removed), `:727`
pushed head wins over a moved head, `:835` pushed-after-named still wins,
`:850` shepherd `process_one` binds the head it read, `:882` the 10 s bound on
`_note_pushed_head` (local `git rev-parse`, unrelated to `read_pr_head_sha`).
Golden `evidence_id` vectors live in `tests/test_execution_evidence.py:299-315`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml:741`,
  `cwft-mctl-agents-investigate.yaml:815`, `cwft-mctl-agents-shepherd.yaml:759`:
  each sets `MCTL_EVIDENCE_AMENDMENT_2: "true"`, so the `subject` block and the
  seal-time read are live in production today.
- mctl MCP tools were not used: the change is library code with no
  tenant/service configuration involved.

## Proposed solution

1. `build()` never reads a head. Replace the Amendment 2 subject fallback:

   ```python
   subject, observed_at = evidence.subject, evidence.subject_observed_at
   if subject is None and evidence.pending_pr is not None:
       flags["subject"] = True
       repository, number = evidence.pending_pr
       if evidence.pushed_head_sha:   # defensive; note_* already folds it in
           subject = SubjectRef("pull_request", repository, str(number), evidence.pushed_head_sha)
       else:
           gaps.append(ee.Gap(block="subject", code="observation_failed", required=True))
   ```

   Keep the existing "pushed head wins regardless of order" behaviour, but
   resolve it at note time: `note_pushed_head(sha)` additionally binds the
   subject when `pending_pr` is set (subject at `sha`, `subject_observed_at`
   = now, i.e. push time, `pending_pr=None`). The branch in `build()` above
   then stays only as a defensive fallback, and no `_utc_now_iso()` stamp at
   seal time pretends an observation.

   Gap code: `observation_failed`. It is already in `GAP_CODES` and
   `UNKNOWN_GAP_CODES` (forced `required=True`), so mctl-api already accepts
   it; `not_observed` would need an mctl-api schema change, which B1 excludes.
   The PR description states this choice.

2. Delete `read_pr_head_sha`, `PrHeadReader`, and the `read_pr_head`
   parameter of `build()` and `produce()`. Keep `READ_TIMEOUT_SECONDS` (used by
   `read_execution_request`). Update the tail-budget comment (~lines 105-114),
   the `pending_pr` comment (now: "a PR named without an observed head; sealed
   as a required subject gap"), and the `note_subject_pr` docstring. Update the
   `run_implementer.py:2861` docstring ("its head is read at seal time").

3. `note_subject_pr` no longer discards an already-observed subject: when
   called with no usable head and `self.subject` is already a `pull_request`
   for the same `(repository, number)`, leave it as is. This matters because
   the implementer names the PR twice (preflight, then
   `_record_implementer_evidence` at 2890). Add an optional `head_sha`
   argument to `note_subject_pr_url(url, head_sha=None)` and forward it.

4. Implementer passes the head it observed. Add `pr_head_sha: str | None =
   None` to `ImplementResult`. In `implement_one`'s preflight branches
   (`open`, `merged`, `closed`, `needs-triage` with a PR) set
   `pr_head_sha=existing.head_sha`. At line 2890 call
   `evidence.note_subject_pr_url(result.pr_url, result.pr_head_sha)`. A
   validated full SHA is required by `note_subject_pr` already
   (`_GIT_SHA_RE`), so a malformed `headRefOid` still yields the gap. No new
   GitHub reads are added: the head is the one the preflight already read
   before deciding.

5. Shepherd: no code change. `process_one` already passes `headRefOid`; an
   empty one now yields the gap with no `gh` call. Covered by a new test.

No envelope schema change: subject keys, gap codes and hashing are untouched,
so any envelope whose subject is unchanged has the same `evidence_id`.

## Alternatives

- Keep the read but bound it to "head at the time the PR was named" (store a
  timestamp, read the head as-of that time via the timeline API). Dropped: it
  is still a substituted observation the run did not make, adds a GitHub
  call on the run tail, and the timeline is not authoritative for force
  pushes.
- Add a new `not_observed` gap code. Dropped for B1: `GAP_CODES` is shared
  with mctl-api, which rejects unknown codes, so it would need a coordinated
  mctl-api release; `observation_failed` already means "an unknown, never an
  observed absence" and is forced required.
- Have the implementer re-read the PR head itself right after naming it.
  Dropped: it is the same seal-time substitution moved earlier; the
  preflight head is the one the run actually decided on.

## Platform impact

- Migrations: none. No schema or API change; mctl-api already accepts
  `subject`/`observation_failed`.
- Backward compatibility: envelopes with a bound subject are byte-identical.
  Runs that previously got a seal-time subject (implementer error-after-PR,
  failed `_capture_head_sha`, shepherd with empty `headRefOid`) now seal
  `INCOMPLETE` with a required `subject` gap. Implementer preflight runs keep
  a bound subject, now from the preflight head. Consumers that count
  `INCOMPLETE` envelopes may see a small rise; that rise is the previously
  hidden unknown.
- Resource impact: one fewer `gh api` call (up to 5 s) on affected run tails.
- Risks: (a) a caller that relied on `read_pr_head` injection breaks at import
  / call time — only tests use it (grep: `tests/test_evidence_producer.py`
  lines 457, 467, 738, 846); they are updated. (b) The "keep an already-bound
  subject" rule could keep a stale subject if a run switches PRs; mitigated by
  only keeping it for the same `(repository, number)`.
