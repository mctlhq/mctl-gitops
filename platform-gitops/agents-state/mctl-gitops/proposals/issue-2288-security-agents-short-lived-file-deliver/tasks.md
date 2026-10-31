# Tasks: issue-2288-security-agents-short-lived-file-deliver

- [ ] 1. Add `platform-gitops/governance/agent-credential-delivery.yaml`
  with one entry per `secretKeyRef` env entry in
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`
  (CWFT, template, env var, secret, key, `agent_image`, `model_driven`,
  `classification`, `delivery`, `file_env`, `mount_path`, `reader`,
  `residual`), all initially `delivery: env-seed`. — DoD: every row of the
  design's inventory table is present; no values; `notify-telegram` rows are
  marked `agent_image: false`.
- [ ] 2. Add `scripts/validate-agent-credential-delivery.py` implementing
  the four rules in design.md section 4, with `--selftest` (pass on the
  migrated fixture, fail on the fixture with the env seed restored).
  (depends on 1) — DoD: green on the repo as-is; `--selftest` exits 0 and
  prints both the expected pass and the expected failure.
- [ ] 3. Wire `--selftest` and the real run of the validator into
  `.github/workflows/validate-manifests.yml` next to
  `scripts/validate-agent-pod-security.py`; add
  `tests/test_agent_credential_delivery.py`. (depends on 2) — DoD: CI job
  runs both steps; the test copies a CWFT to a temp dir, re-adds a
  migrated `secretKeyRef`, and asserts a non-zero exit.
- [ ] 4. Confirm with mctlhq/mctl-agents#920 which entrypoints read
  `GITHUB_TOKEN_FILE` before their first credentialed call with no env seed
  (`run_issue_investigator`, `run_implementer`, `run_shepherd` and
  `--reconcile`, `run_all`, `run_scout`, `run_usage_collector`), and the
  minimum `agent_image` for each. Phase 1 starts only after the #920 release
  (which adds `refresh_github_token()` to `run_all`) is the pinned
  `agent_image`. — DoD: list recorded in the inventory
  `reader` field; any entrypoint without support stays `env-seed`.
- [ ] 5. Phase 1 `github-token` migration (depends on 3, 4): remove the
  `GITHUB_TOKEN` `secretKeyRef` from each supported agent-image step; add or
  reuse a `github-token-file` Secret volume with `defaultMode: 0440`, mounted
  `readOnly: true` at `/var/run/gh` only in that container; set
  `GITHUB_TOKEN_FILE=/var/run/gh/github-token`; rewrite shell guards at
  `cwft-mctl-agents-investigate.yaml:480`, `cwft-mctl-agents-implement.yaml:517`,
  `cwft-mctl-agents-shepherd.yaml:538` to test `-s "$GITHUB_TOKEN_FILE"`;
  replace every `gh auth setup-git` call (investigate:486, implement:518,
  shepherd:539) with the command-scoped
  `GITHUB_TOKEN="$(cat "$GITHUB_TOKEN_FILE")" gh auth setup-git` (design
  section 2: setup-git exits 1 without a token and the scripts run under
  `set -e`);
  update the stale "only seeds the very first call" comments; flip the
  inventory rows to `delivery: file`. — DoD: validator green; `helm`/kubeconform
  checks in `validate-manifests.yml` green; no `GITHUB_TOKEN` `secretKeyRef`
  in any migrated agent-image step.
- [ ] 6. Real-run verification for phase 1 (depends on 5): after ArgoCD
  sync (~3 min), run one investigate, implement (or shepherd review-fix),
  shepherd, run (single service), scout, reconcile (dry run acceptable) and
  usage-collector workflow. — DoD: each succeeds including its gh/git
  operation (clone, issue comment, push/PR as applicable); for one
  run longer than 30 min, the logs or a rotation timestamp show the token
  file changed and the next gh call succeeded.
- [ ] 7. Phase 2 is out of scope: it moved to mctl-gitops#2296. Do not
  migrate any credential other than `github-token` here.
- [ ] 8. Completion report on issue #2288 and in the final PR: per inventory
  row, the three claims `NO_LONG_LIVED_SECRET_ENV_SEED`,
  `SHORT_LIVED_OR_ROTATABLE`, `MODEL_SHELL_CANNOT_READ_CREDENTIAL_BYTES`
  stated separately; residual credentials (at least the Claude OAuth tokens,
  `mctl-token`, usage/evidence writer tokens, Telegram tokens) listed by
  name with limitation and follow-up owner. — DoD: no row claims model-shell
  isolation; only `github-token` claims short-lived/rotatable.
- [ ] 9. Add a short runbook section (in
  `docs/runbooks/agents-app-secret-exposure.md` or a new
  `docs/runbooks/agent-credential-delivery.md` linked from `CLAUDE.md`)
  describing the inventory, the validator, and rollback. — DoD: linked from
  `CLAUDE.md` Secrets Management section.

## Tests

- [ ] T1. `scripts/validate-agent-credential-delivery.py --selftest`
  passes the clean fixture and fails the mutated one (env seed restored).
- [ ] T2. `tests/test_agent_credential_delivery.py`: real repo passes;
  re-adding `GITHUB_TOKEN` `secretKeyRef` to `run-investigator` in a temp
  copy fails with a message naming the CWFT, template and variable.
- [ ] T3. Same test: adding an unlisted `secretKeyRef` to an agent-image
  step fails; adding one to `notify-telegram` (non-agent image) passes.
- [ ] T4. Same test: a migrated credential volume with `defaultMode: 0644`
  or without `readOnly: true`, or mounted into an initContainer, fails.
- [ ] T5. Existing `scripts/validate-agent-pod-security.py` and
  `tests/test_policy_checkpoint_coverage.py` still pass.
- [ ] T6. Live: task 6 real runs, including an observed rotation of
  `/var/run/gh/github-token` followed by a successful gh/git call.

## Rollback

Revert the phase 1 PR, which restores the
`env[].valueFrom.secretKeyRef` entry, the previous `*_FILE` wiring and shell
guards, and flips the inventory row back to `delivery: env-seed` in the same
commit (so the validator stays green). ArgoCD re-syncs in about 3 min;
in-flight workflows are unaffected because Argo snapshots templates at
submit. If the validator itself misfires, revert task 3's
`validate-manifests.yml` wiring; the manifests are unaffected. No Vault or
Secret data changes are made by this proposal, so there is nothing to
restore there.
