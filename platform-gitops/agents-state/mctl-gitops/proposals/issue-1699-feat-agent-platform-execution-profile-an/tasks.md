# Tasks: issue-1699-feat-agent-platform-execution-profile-an

- [ ] 1. Re-verify the pin: fetch `agents/_manifests/authoring-canary/agent.yaml`
  at the current head of mctlhq/mctl-agents#598 and at
  `15afef703a2d5dbf23ff64a862e3fbe5cfd54d4e`, compute sha256 of the raw bytes. —
  DoD: both equal `4af4245df12133259961558f52a409cbf1ca8cca2ed08d5476942c22f62fe513`
  (or, if the head differs, the new hash is used everywhere below and noted in
  the PR); the head SHA to record is written down.
- [ ] 2. `policy.yaml`: add `inert-read-only` to `spec.knownPolicies` and a new
  `spec.uncalledProfiles: [authoring-canary-default]`, each with a comment saying
  why (see design.md). — DoD: no other policy entry changed.
- [ ] 3. `scripts/validate-agent-platform.py` (depends on 2): add
  `Policy.uncalled_profiles`; add the `uncalled` parameter to
  `validate_profile_against_cwft` (error on `budgetEnv`, error on any
  `cluster-templates/*.yaml` that contains the entrypoint module token, skip only
  the budget comparison, keep the timeout comparison); in `validate_catalog`
  pass the flag and report `uncalledProfiles` entries that match no loaded
  profile. — DoD: running the script on `main`'s catalog (without the new
  profile) gives the same result as before except the stale-entry error for
  `authoring-canary-default`, which disappears once task 4 lands.
- [ ] 4. Add `platform-gitops/agent-platform/execution-profiles/authoring-canary-default/profile.yaml`
  (depends on 2) exactly as in design.md section 2, with a header comment giving
  the source of every value (manifest, `build_authoring_canary_options`,
  `activeDeadlineSeconds: 3600`, no caller, no `budgetEnv`). — DoD: schema-valid,
  tools `Read/Glob/Grep`, budget `0.01`, timeout `3600`, all repo writes false,
  `kubernetes: none`, no skills/mutation scopes/approval gates/evidence.
- [ ] 5. Add `platform-gitops/agent-platform/releases/shadow/authoring-canary.yaml`
  (depends on 1, 4) shaped like `releases/shadow/mentor.yaml`, with the path,
  contentHash and gitSha from task 1, `compatibility-fixture`,
  `promotable: false`, `bindingRevision: 1`. — DoD: validator accepts it;
  comment names `15afef7` and the re-pin runbook.
- [ ] 6. Selftest fixtures under `scripts/tests/fixtures/agent-platform/` (depends
  on 3), each with its own full `policy.yaml` copy and, where noted,
  `cluster-templates/cwft-mctl-agents-run.yaml` with several `*_BUDGET_USD`:
  - `valid/uncalled-profile-without-budget-env/` (listed, no `budgetEnv`, no
    reference in templates, timeout matches `activeDeadlineSeconds`);
  - `invalid/uncalled-profile-with-caller/` (template mentions the entrypoint
    module);
  - `invalid/uncalled-profile-with-budget-env/`;
  - `invalid/uncalled-profile-timeout-mismatch/` (timeout still checked);
  - `invalid/uncalled-profiles-stale-entry/` (lists a profile that does not exist);
  - `invalid/unlisted-profile-without-budget-env/` (same profile, not listed:
    fails as today). — DoD: `--selftest` passes with all new cases.
- [ ] 7. `platform-gitops/agent-platform/README.md` (depends on 3-6): add the
  canary row to the effective-value table, a "Profiles with no caller"
  subsection, and the new fixtures to the expectation table. — DoD: docs
  describe the exemption and its verification.
- [ ] 8. Open the PR (feature branch, not main) referencing mctlhq/mctl-gitops#1699,
  mctl-agents#596/#598/#470; state that it must not be auto-merged and that #598
  should merge first or together. — DoD: PR open, `Validate Manifests` green,
  no `cwft-*`/`cronworkflow-*` file in the diff.

## Tests

- [ ] T1. `python3 scripts/validate-agent-platform.py --selftest` passes:
  "validated 7 execution profile(s), 7 release intent(s)" and all fixtures ok.
- [ ] T2. Negative check by hand: temporarily add `# run_authoring_canary` to a
  copy of `cwft-mctl-agents-run.yaml` in a fixture -> validator fails with the
  "has a caller" error (covered permanently by
  `invalid/uncalled-profile-with-caller/`).
- [ ] T3. `git diff --name-only main` contains no file under
  `platform-gitops/argo-workflows/`; `grep -rn "authoring.canary\|AUTHORING_CANARY"
  platform-gitops/argo-workflows/` returns nothing.
- [ ] T4. In mctl-agents with #598 checked out and `MCTL_GITOPS_ROOT` pointing
  at this branch: `uv run python -m orchestrator.validate_manifest` and the full
  test suite pass (catalog-profile check compares `authoring-canary-default`
  with `build_authoring_canary_options`).
- [ ] T5. After merge, re-run the `binding hash` job on mctlhq/mctl-agents#598
  -> `authoring-canary: match`.
- [ ] T6. `validate-profile-version-bumps.py` passes (new profile, nothing to
  compare).

## Rollback

Revert the merge commit. Nothing at run time reads the new profile or binding
(the canary has no caller and is v1alpha1), no template or ArgoCD-synced
manifest changes, and the validator change is additive, so a revert only
returns #598's `binding hash` to `authoring-canary: missing` and blocks the
canary's promotion. If the validator change alone misbehaves, emptying
`uncalledProfiles` restores the previous behavior for every profile (and then
the canary profile must be removed in the same PR, since it would fail the
budget check).
