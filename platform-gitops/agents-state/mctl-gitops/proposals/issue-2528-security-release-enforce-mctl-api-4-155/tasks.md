# Tasks: issue-2528-security-release-enforce-mctl-api-4-155

- [ ] 1. Baseline inventory. Run the planned `forbidden_env` scan by hand
  (`grep -rnw` for the four names over the `env_sources` globs) and record the
  result in the PR description. Confirm that `mctl-api.yaml` has exactly one
  `repoURL: https://github.com/mctlhq/mctl-api.git` with a sibling 40-hex
  `targetRevision`. — DoD: a clean scan on `main` is recorded, or each hit is
  listed and escalated before task 3 merges.
- [ ] 2. Schema. Extend `_holds()` in `scripts/release-gate.py` with
  `chart_repo`, `require_pinned_chart`, `require_binding`, `source_repo`,
  `forbidden_env`, `env_sources`, and the record fields `digest`,
  `source_commit`, `release_head` and `chart_revision`. Unknown keys and
  malformed values are errors. Document them in the `release-gates.yaml` header
  comment. — DoD: `--selftest` covers each malformed field; the live policy still
  loads.
- [ ] 3. Offline checks (depends on 2). Add `chart_problems()` and
  `env_problems()` and call them from `hold_problems()` in both `check` and
  `verify`. Add the new fields to the `mctl-api-bootstrap` hold with
  `allow: []`. — DoD: `python3 scripts/release-gate.py verify` passes on the
  current tree; the T1-T6 cases are red when their rule is mutated out (MUTANTS).
- [ ] 4. Online `artifact` subcommand (depends on 2). Route all reads through
  the injectable `_fetch`, with exits 0/6/7, a 20 s timeout and no retries
  inside the tool. Skip below `held_from`. — DoD: T7-T10 pass with fake fetchers;
  no test touches the network.
- [ ] 5. Grant/effect separation (depends on 2). In `diff_problems()`, refuse a
  change set that touches `version_holds` or `scripts/release-gate.py` together
  with the held tag or chart `targetRevision`. — DoD: T11 passes;
  `tests/test_release_gate_diff.py` stays green.
- [ ] 6. Workflow wiring (depends on 3, 4). In `release-deploy.yaml` and
  `gitops-bump.yaml`, call `artifact --policy-rev origin/main` next to every
  `verify --policy-rev origin/main` in bump, `publish-direct` (inside the
  per-attempt `release_gate()`) and `publish-pr`. Add the needed
  `packages: read` permission only if task 8 confirms it is required. —
  DoD: T12-T15 pass in `tests/test_release_deploy_bump.py` /
  `tests/test_release_bump_pr_route.py` style harnesses against a disposable
  bare remote.
- [ ] 7. PR trust (depends on 3, 5). In `validate-manifests.yml`, add a step
  that runs the base ref's `release-gate.py` with `python3 -I` from
  `$RUNNER_TEMP` (`verify`, `diff --base <merge-base> --head HEAD`, and
  `artifact` when held). Add `artifact` to `release-gate-watch.yml` daily. —
  DoD: T16 passes; a PR that edits the script cannot turn its own check green.
- [ ] 8. GHCR access decision. Determine whether `ghcr.io/mctlhq/mctl-api`
  manifests are readable anonymously or need `GITHUB_TOKEN` with `packages:
  read`, and whether the chart at `a5b9ef9c` supports `image.digest`. — DoD: the
  answer is recorded in the runbook. If digest values are supported, open a
  follow-up for an offline `image.digest == allow.digest` check.
- [ ] 9. Runbook (depends on 3-7). Update `docs/runbooks/mctl-api-release-hold.md`:
  P7 KNOWN-ENFORCED, P9 partial, the new rows for artifact/env/separation, and
  P5b, P6, P8, P12 and Job-written Secrets still BLOCKING-UNKNOWN. Keep the
  dependency map (#934, #2523, #993, #992, #1007, #935, #1040, #1292). — DoD:
  every row cites a file and line on the implementation head.
- [ ] 10. Review. Independent review on the final head, plus a separate
  digest-bound owner approval, before merge. No allow record is added in this
  change. — DoD: the review is recorded; `allow: []` is unchanged.

## Tests

All tests use copies of the real bootstrap file and the policy in temp trees,
fake fetchers, and disposable bare git remotes. Every negative case asserts the
exit code and, for workflow harnesses, that the remote's `main` SHA is unchanged
and no `release-bump/*` ref was pushed.

- [ ] T1. Held 4.155.0, allow record missing `digest` (and each other bound
  field in turn): `check` exits 6.
- [ ] T2. Held version with a valid record, but the chart `targetRevision` is not
  equal to `chart_revision`: refused in `check` and `verify`.
- [ ] T3. Chart `targetRevision: main` at 4.154.0: `verify` refused (chart main
  drift).
- [ ] T4. Two `mctl-api.git` sources, or none: UNKNOWN refusal.
- [ ] T5. Each forbidden key added to the values `env`, then as a `secretKey` in
  `mctl-api-secrets.yaml`, then in a `.tf` under `zitadel-iac`: refused at
  4.154.0.
- [ ] T6. An `env_sources` glob that matches nothing, or an unreadable file:
  UNKNOWN refusal.
- [ ] T7. `artifact`: GHCR digest differs from the record: exit 6.
- [ ] T8. `artifact`: revision label differs from `source_commit`, or the
  label is absent: exit 6.
- [ ] T9. `artifact`: the git tag resolves to another commit, or the tag is
  absent: exit 6 or 7.
- [ ] T10. `artifact`: HTTP 500, timeout, malformed JSON, or a missing
  `Docker-Content-Digest`: exit 7.
- [ ] T11. One commit adds an allow record and bumps the tag: `diff` refused.
- [ ] T12. `release-deploy.yaml` route: a held bump with no record leaves the
  remote unchanged.
- [ ] T13. `gitops-bump.yaml` route: same as T12, and an expired record also
  leaves the remote unchanged.
- [ ] T14. Concurrent `main`: a record removed on the remote between bump and
  publish, so the retry after rebase refuses and no push happens.
- [ ] T15. Positive control: an ordinary bump below `held_from` publishes
  through both routes. A held bump with a complete record, matching chart and a
  fake-fetcher match publishes on the PR route.
- [ ] T16. PR trust: a PR copy of `release-gate.py` patched to always pass still
  fails the trusted-copy step.
- [ ] T17. Mutation: removing each new rule from the script turns at least one
  of T1-T11 red (extend MUTANTS in `tests/test_release_gate_bootstrap_hold.py`).

## Rollback

All changes are in git and grant nothing. To roll back, revert the
implementation PR: the gate returns to the current `version_holds` behaviour
(version plus allow record), which still refuses 4.155.0 with `allow: []`.

- If only the online check misbehaves, for example a GHCR outage blocking a
  legitimate held release, the fallback is a reviewed PR that removes the
  `artifact` calls from the workflows. Ordinary releases below `held_from` are
  never affected.
- If the `forbidden_env` scan produces a false positive, the fallback is a
  reviewed PR that narrows the `env_sources` globs.
- Never roll back by deleting the `mctl-api-bootstrap` hold: an absent hold
  removes all protection.
