# Tasks: issue-292-fix-lifecycle-steward-owned-repos-have-n

All work is in `mctlhq/mctl-agents` unless a task says otherwise. Follow
`CONTRIBUTING.md`: English only, no emoji, `warn:`/`info:`/`error:` log
prefixes, and `uv run pytest tests/` + `uv run ruff check orchestrator config
tests` + `uv run mypy` green before the PR.

- [ ] 1. Add the service-mode resolver to `orchestrator/run_shepherd.py`.
  Factor the body of `_skip_services_from_env` (line 316) into
  `_service_set_from_env(var: str) -> frozenset[str]` keeping the
  unknown-name `warn:` behaviour, then define module constants
  `SHEPHERD_SKIP_SERVICES`, `SHEPHERD_FIX_ONLY_SERVICES`,
  `NEVER_MERGE_SERVICES = frozenset({"mctl-academy"})`, the mode literals
  `FULL`/`FIX_ONLY`/`SKIP`, and
  `_service_mode(service, *, force_fix_only=False) -> str` with the precedence
  from `design.md` §1 (fix-only beats skip; `NEVER_MERGE_SERVICES` never
  resolves to `FULL`). Emit a one-line `warn:` at import naming any service
  present in both env lists.
  — DoD: `_skip_services_from_env` is either gone or a thin alias, the new
  constants exist, and with both env vars unset every service resolves to
  `FULL` except `mctl-academy`.

- [ ] 2. Thread the mode through discovery (depends on 1). Add
  `mode: str = FULL` to `ProposalRef` (line 358), add a `fix_only: bool = False`
  parameter to `_discover_refs` (line 492), replace the
  `service in SHEPHERD_SKIP_SERVICES` test at line 518 with
  `_service_mode(service, force_fix_only=fix_only) == SKIP`, keep the existing
  `shepherd: skipping <svc> (SHEPHERD_SKIP_SERVICES; owned by another PR
  lifecycle)` line for the skip branch, and set `mode=` on each constructed
  `ProposalRef`. Reconcile mode stays unfiltered. Update the `_discover_refs`
  docstring (lines 505-508), which currently claims skipped services are never
  discovered.
  — DoD: a proposal under a fix-only service is returned by `_discover_refs`
  in normal mode with `ref.mode == FIX_ONLY`; a skip-only service still logs
  and returns nothing; reconcile behaviour is byte-identical.

- [ ] 3. Add the `defer-merge` decision to `decide()` (depends on 1). Add a
  keyword-only `fix_only: bool = False` to `decide` (line 1138) and return
  `("defer-merge", None)` instead of `("merge", None)` at the final return.
  Change nothing above it, so `wait` / `address-review` / `flip-to-merged` /
  `flip-to-rejected` are identical in both modes. Update the docstring's
  "one of the five decisions" wording.
  — DoD: `decide` stays pure and side-effect free; the same
  clean-green-settled fixture yields `merge` with `fix_only=False` and
  `defer-merge` with `fix_only=True`.

- [ ] 4. Handle `defer-merge` in `process_one` (depends on 2, 3). Pass
  `fix_only=(ref.mode == FIX_ONLY)` into the `decide()` call (line ~1607); add
  a `defer-merge` branch above the `merge` branch that prints the `info:` line
  from `design.md` §4, calls
  `_update_status_if_changed(ref, ref.status, merge_owner="pr-steward")`, and
  returns `ShepherdResult(decision="defer-merge", notes="merge owned by
  pr-steward")`. Add `merge_owner=None` to the `update_status(...)` calls in
  the `flip-to-merged`, `flip-to-rejected` and `merge` branches so the field is
  removed on terminal states. Add the defensive re-check described in
  `design.md` §4 before `merge_pr(pr)`.
  — DoD: a fix-only proposal whose PR is clean and green gets `merge_owner:
  pr-steward` written exactly once and `status` unchanged; `merge_pr` is never
  called; `address-review` and the `MAX_REVIEW_ATTEMPTS`/`review-stuck` paths
  are unchanged.

- [ ] 5. Add the never-merge guard to `merge_pr` (depends on 1). At the top of
  `merge_pr` (line 1509) derive `service = pr.repo.split("/")[-1]`; if it is in
  `NEVER_MERGE_SERVICES`, print an `error:` line and `return (False, None)`
  before `refresh_github_token()` or any `gh` invocation.
  — DoD: calling `merge_pr` directly with an `mctlhq/mctl-academy` snapshot
  runs no subprocess and returns `(False, None)`.

- [ ] 6. Add the `--fix-only` CLI flag (depends on 2, 4). In
  `run_shepherd.main()` (line 2174) add `--fix-only` (`action="store_true"`);
  exit 2 with a message when combined with `--reconcile`; forward it to
  `_discover_refs(..., fix_only=args.fix_only)` and force `ref.mode = FIX_ONLY`
  on every discovered ref for the run. Leave the `--dry-run` short-circuit and
  the `spent_estimate` budget loop untouched (`defer-merge` is not charged).
  — DoD: `--fix-only --service mctl-telegram --slug <slug>` discovers and
  processes the proposal without merging; `--fix-only --reconcile` exits 2;
  `--fix-only --dry-run` forks nothing.

- [ ] 7. Add `defer-merge` to the summary and the module docstring (depends on
  4, 6). Ensure `_print_summary` (line 2158) prints the decision and its notes
  (it already does generically — confirm with a test), and extend the
  `run_shepherd.py` module docstring's `Env:` and `Usage:` blocks with
  `SHEPHERD_FIX_ONLY_SERVICES`, the three modes, and the `--fix-only` example.
  — DoD: `=== Shepherd summary ===` shows
  `mctl-telegram/<slug>: defer-merge  (merge owned by pr-steward)`.

- [ ] 8. Update the docs (depends on 1-7). `README.md` "Tier 3 — PR shepherd":
  document the three service modes, the sixth decision, the never-merge
  constant, and the `--fix-only` one-shot; update the quoted `decide()`
  pseudo-code. `docs/agent-inventory.yaml` shepherd entry (line 146): note that
  merge is conditional on service mode and that `mctl-academy` is never
  mergeable by an agent. `docs/adr/006-dev-loop-merge-deploy-monitor.md`: add a
  short addendum to §6.1 recording that `SHEPHERD_SKIP_SERVICES` no longer
  implies "no in-loop review fixing", and that a DevLoop claiming
  `shepherd_in_loop` on a skipped repo previously orphaned the proposal from
  both drivers.
  — DoD: `uv run pytest tests/test_agent_inventory.py tests/test_diagram_facts.py`
  passes; no README statement contradicts the code.

- [ ] 9. Write the gitops rollout note into the PR body (depends on 8). The
  companion `mctl-gitops` change is not in this repo, so spell it out exactly:
  in both `cronworkflow-mctl-agents-shepherd.yaml` and
  `cwft-mctl-agents-shepherd.yaml`, set
  `SHEPHERD_FIX_ONLY_SERVICES: "mctl-design,mctl-telegram,mctl-gitops,mctl-pairdesk"`
  and reduce `SHEPHERD_SKIP_SERVICES` to `"mctl-academy"`. Both files matter —
  the CWFT env is what `DevLoopWorkflow._shepherd_tick` inherits. Note that the
  two edits are order-independent because fix-only wins over skip.
  — DoD: the PR body contains the exact env values and names both files.

## Tests

Add to `tests/test_run_shepherd.py`, following its existing conventions:
module-level `def test_*(...) -> None`, the `make_pr` / `make_finding` /
`make_status_yaml` / `make_ref` / `read_status` factories,
`monkeypatch.setattr(run_shepherd, "<CONSTANT>", frozenset({...}))` for the
module constants, and `unittest.mock.patch.object(run_shepherd, ...)` for
subprocess boundaries. Put them under a new banner comment beside the existing
`# SHEPHERD_SKIP_SERVICES: per-service opt-out (pr-steward-owned repos)`
section at line 221.

- [ ] T1. `test_fix_only_services_from_env_parses_comma_and_space` and
  `test_fix_only_services_from_env_warns_on_unknown` — mirror
  `test_skip_services_from_env_parses_comma_and_space` (line 229) and
  `test_skip_services_from_env_warns_on_unknown` (line 237) for the new var.
- [ ] T2. `test_service_mode_fix_only_wins_over_skip` — a service in both env
  lists resolves to `FIX_ONLY` and a `warn:` naming it is printed (`capsys`).
- [ ] T3. `test_service_mode_defaults_unchanged_when_env_unset` — with both
  vars empty, every entry of `config.settings.SERVICES` resolves to `FULL`
  except `mctl-academy`.
- [ ] T4. `test_discover_includes_fix_only_service` — counterpart to
  `test_discover_skips_listed_service` (line 245): the proposal is returned,
  `ref.mode == FIX_ONLY`, and no `skipping` line is printed.
- [ ] T5. `test_discover_force_fix_only_overrides_skip_list` —
  `_discover_refs(..., fix_only=True)` returns a proposal for a service listed
  in `SHEPHERD_SKIP_SERVICES` (the `--fix-only` one-shot on a still-skipped
  repo).
- [ ] T6. `test_decide_defer_merge_in_fix_only` — the `test_decide_merge`
  fixture (line 167) with `fix_only=True` returns `("defer-merge", None)`.
- [ ] T7. `test_decide_fix_only_does_not_change_non_merge_decisions` —
  parametrised over the `wait` / `address-review` / `flip-to-merged` /
  `flip-to-rejected` fixtures already in the file (lines 953-1027): the
  decision is identical with and without `fix_only=True`.
- [ ] T8. `test_process_one_defer_merge_writes_merge_owner_once` — a fix-only
  ref with a clean, green, settled PR: `read_status(ref)["merge_owner"] ==
  "pr-steward"`, `status` unchanged, `merge_pr` patched and asserted
  not called. Run `process_one` twice and assert the file's `updated_at` is
  unchanged on the second tick (the `_update_status_if_changed` contract).
- [ ] T9. `test_process_one_fix_only_still_applies_review_feedback` — a
  fix-only ref with a P1 finding on `HEAD_SHA` reaches `apply_followup`
  (patched), `trigger_review` is called, `review_attempts` becomes 1, and the
  status ends at `implemented` — i.e. the `address-review` path is untouched by
  the mode. This is the regression test for the issue itself.
- [ ] T10. `test_process_one_fix_only_flips_to_merged_when_steward_merges` — a
  fix-only ref whose PR is `merged=True` still flips to terminal `merged` and
  `merge_owner` is removed from `.status.yaml`.
- [ ] T11. `test_merge_pr_refuses_never_merge_service` — `merge_pr` with an
  `mctlhq/mctl-academy` snapshot returns `(False, None)`, prints an `error:`
  line, and `subprocess.run` / `refresh_github_token` are never called.
- [ ] T12. `test_decide_never_returns_merge_for_academy` — `decide` for a
  `mctl-academy` PR in every otherwise-mergeable fixture never yields `merge`.
- [ ] T13. `test_main_rejects_fix_only_with_reconcile` — `SystemExit` with code
  2, in the style of the existing `main()` tests such as
  `test_main_applies_the_ownership_filter_only_in_sweep_mode` (line 2621).
- [ ] T14. `test_print_summary_includes_defer_merge` — the summary line for a
  `defer-merge` result contains the decision and the notes.
- [ ] T15. Regression guard: `uv run pytest tests/test_diagram_facts.py` and
  `tests/test_agent_inventory.py` still pass — this change adds no
  `.status.yaml` *status* value, so `SHEPHERD_INPUT_STATUSES` /
  `RECONCILE_INPUT_STATUSES` (tracked by `tools/diagram_facts.py:_STATUS_SET_RE`)
  must be untouched.

## Rollback

The change is additive and env-gated, so rollback has three levels of
increasing blast radius:

1. **Config only, no deploy (seconds).** In `mctl-gitops`, clear
   `SHEPHERD_FIX_ONLY_SERVICES` and restore
   `SHEPHERD_SKIP_SERVICES: "mctl-design,mctl-telegram,mctl-gitops,mctl-pairdesk,mctl-academy"`
   in `cronworkflow-mctl-agents-shepherd.yaml` and
   `cwft-mctl-agents-shepherd.yaml`. `_service_mode` then resolves exactly as
   today and the shepherd returns to skipping all five repos on the next tick.
   No image rollback, no code change.
2. **Narrow the blast radius instead of reverting.** Remove only the offending
   service from `SHEPHERD_FIX_ONLY_SERVICES` (for example drop `mctl-gitops`
   and keep `mctl-telegram`), since the lists are per-service.
3. **Full revert (minutes).** Revert the mctl-agents PR and roll the shepherd
   agent version back with `mctl_rollback_agent agent_name=shepherd
   environment=production`. In-flight DevLoop executions keep whatever image
   they pinned; the next tick resolves the rolled-back one.

Residue after any rollback: `merge_owner: pr-steward` may remain on some
`.status.yaml` files. It is an unread extra key — `load_status` and
`update_status_file` preserve unknown fields, and no reader consults it — so it
is harmless and can be cleaned up lazily, or left to be removed by the next
terminal flip on a re-deployed version. Any follow-up commits the shepherd
already pushed live on `feat/agents-*` branches and are reviewable like any
other commit; nothing was merged, because merge was never enabled for these
repos in this design.
