# Design: issue-813-fix-security-harden-landed-binding-corre

## Current state
- `orchestrator/run_security_verifier.py`
  - `_DEV_LOOP_ID_RE = re.compile(r"^dev-loop-[A-Za-z0-9_.-]+?-([A-Za-z0-9_.-]+)-(\d+)$")` (line 35).
  - `default_merged_lookup(client, workflow_id)` (lines 45-69) parses `(repo, number)` from the id, checks
    `client.get_dev_loop(workflow_id)` is finished, then calls
    `orchestrator.temporal.activities.proposals.find_proposal_slug(repo, number)` and
    `orchestrator.temporal.activities.pr_state.get_pr_state(repo, slug)`.
  - `MergedLookup = Callable[[SecurityFindingsClient, str], tuple[str, str] | None]`.
  - `_bind_missed` (lines 129-157) lists `fixing` occurrences, reads each, and calls
    `merged_lookup(client, attempt.devloop_workflow_id)` - the occurrence's repository is available
    (`occ.repository`, `summary.repository`) but unused.
- `orchestrator/security_findings/landed.py::bind_landed` (lines 49-86): lists `fixing`, filters with
  `repository_matches(summary.repository, target_repo)`, then on a failed `client.get_occurrence(summary.id)`
  appends `LandedOutcome(summary.id, UNKNOWN)` (line 64) before the `attempt.devloop_workflow_id != workflow_id`
  check (line 68). Called by `orchestrator/temporal/activities/security_findings.py::_bind`, whose result feeds
  `DevLoopResult.security` (`orchestrator/temporal/workflows/dev_loop.py` ~4485-4540).
- `orchestrator/security_findings/contract.py::parse_occurrence` sets `Occurrence.repository` from
  `subject.repository` (documented normalised form `host/owner/repo`, e.g. `github.com/mctlhq/svc`).
- Workflow ids are built as `f"dev-loop-{owner}-{repo}-{number}"` with owner fixed to `mctlhq`
  (`orchestrator/temporal/issue_ref.py::workflow_id_for`, `parse_issue_url`).
- Tests: `tests/test_security_findings.py` (fake store `tests/security_findings_fake.py`, default seed repo
  `github.com/mctlhq/svc`); sweep tests pass `merged_lookup=lambda c, w: ...` / `lambda *_: None`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows`, `$MCTL_GITOPS_ROOT/helm-charts`, `platform-gitops/services`,
  `platform-gitops/tenants`: grep for `run_security_verifier` / `security-verif` found nothing - the verifier
  sweep is not scheduled yet, consistent with the module docstring ("scheduled later by a CronWorkflow").
- No mctl MCP calls were needed; the change is library/CLI code with no deployed config.

## Proposed solution
### P2-1: repository identity from the occurrence
1. Add to `landed.py` (shared, pure) `def mctlhq_repo_name(subject_repository: str) -> str`: lowercase, strip
   `.git` and trailing `/`, split on `/`; accept `github.com/mctlhq/<repo>` or `mctlhq/<repo>`; return `<repo>`
   only if it matches `^[a-z0-9_.-]+$`; else `""`. Constant `SUPPORTED_OWNER = "mctlhq"`.
2. Add `def issue_number_for(workflow_id: str, repo: str) -> str`: with `prefix = f"dev-loop-{SUPPORTED_OWNER}-{repo}-"`,
   return the remainder iff `workflow_id.startswith(prefix)` and the remainder is all ASCII digits; else `""`.
   No regex groups over the owner/repo part; only the terminal number is parsed and the rest is verified by
   exact equality.
3. Change `MergedLookup` to `Callable[[SecurityFindingsClient, str, str], tuple[str, str] | None]` taking
   `(client, workflow_id, repo)`; `default_merged_lookup` computes `number = issue_number_for(workflow_id, repo)`,
   returns `None` if `not repo or not number`, then proceeds as today with that `repo`.
4. `_bind_missed`: `repo = mctlhq_repo_name(occ.repository or summary.repository)`; if empty, emit
   `occurrence_id=..., skipped="repository_unsupported"` and continue; else call
   `merged_lookup(client, attempt.devloop_workflow_id, repo)`. Delete `_DEV_LOOP_ID_RE` and the `re` import.

### P2-2: no outcome for an unread candidate
In `bind_landed`, replace `out.append(LandedOutcome(summary.id, UNKNOWN))` with a stderr warning
(`warn: security landed binding skipped unread candidate <id> (<verdict>/<code>) for <workflow_id>; the verifier
sweep will recover it`) and `continue`. Correlation is established only after a successful read with
`attempt.devloop_workflow_id == workflow_id`; record_fix `unknown` after that point still emits
`LandedOutcome(occ.id, UNKNOWN, attempt.id)` because ownership was proven. The listing-failure unscoped marker
`LandedOutcome("", UNKNOWN)` stays. Update the module docstring to state the invariant.

## Alternatives
- Fix the regex (greedy owner / anchored `mctlhq`): still parses identity from an ambiguous string and leaves
  the fallback dependent on id formatting; rejected per the issue's required fix.
- Pass the repository via the `repository` list filter: the client deliberately does not guess the filter
  format (landed.py docstring); unnecessary since the full read already carries `subject.repository`.
- Emit an unscoped diagnostic `LandedOutcome("", "unread")` for skipped candidates: changes the result
  vocabulary consumers read; log-only keeps `DevLoopResult.security` strictly proven matches. Recorded as an
  open question.

## Platform impact
- No migrations, no Temporal workflow changes (activity signature and return shape unchanged), so no
  `workflow.patched` gate is needed. `DevLoopResult.security` may contain fewer entries (never wrong ones).
- `MergedLookup` signature change is internal (only `sweep` and tests use it).
- Risk: an occurrence with an empty/foreign repository is no longer looked up in the fallback; mitigated by the
  explicit `skipped` line and by the DevLoop hook path, which is unaffected. Risk: a skipped unread candidate in
  the hook is not bound; mitigated by the sweep fallback re-reading it next run.
