# Tasks: issue-1225-spike-runtime-choose-shared-assistant-pr

- [ ] 1. Create `docs/reports/assistant-runtime-boundary-spike.md` with the verdict
  block at the top: recommended `REUSE_EXISTING`, a status line ("Recommendation, owner
  decides on mctlhq/.github#324") and the runtime blockers (Temporal client auth
  mctl-gitops#2456, #1048, sanctioned provider API). — DoD: exactly one verdict token
  appears in the verdict line, and the blockers are listed.
- [ ] 2. (depends on 1) Write the boundary glossary for Temporal namespace, Kubernetes
  namespace, GitHub repository and MCTL tenant: what each isolates, what it does not, and
  current state. Cite `infra-components/data/temporal/networkpolicy.yaml` and
  `tenant-namespace-job.yaml`. — DoD: each boundary has a source-backed current-state row.
- [ ] 3. (depends on 1) Write the current-topology inventory from design.md "Deployed
  state checked" and the clone facts (`Dockerfile.agent-worker`, release-please and
  preview-deploy image jobs, `docs/adr/0008-managed-runtime.md`, `internal/netsafe`,
  `go.mod` without Temporal). — DoD: every row is labelled source-backed with a path, or
  "not observed".
- [ ] 4. (depends on 2, 3) Write the A/B/C comparison table on these axes: queue topology,
  worker image lifecycle, release governance, runtime security, build/release CI,
  secrets, kill switch, failure modes, cost. — DoD: 9 axes x 3 options, each cell
  labelled source-backed or model-only.
- [ ] 5. (depends on 4) Write the queue topology and kill-switch sections: shared
  `mctl-assistants` only behind the authorizer plus mctl-api tenant/user checks;
  `assistants-control` / `assistants-provider-<provider>`; layered kill switches. —
  DoD: the multi-tenant use of the shared namespace is stated as blocked until S2.
- [ ] 6. (depends on 4) Write the recommendation rationale, and the option C promotion
  triggers (second provider or surface, distinct merge/publish permissions, dependency or
  license isolation). Include the checklist a later repo-creation approval must fill:
  name, visibility, automation, branch protection, CI, release, permissions. — DoD:
  triggers and checklist are present, and no repository is created.
- [ ] 7. (depends on 6) Add the cross-repo ownership map and slices S0-S8 with the
  dependency graph and the approval each slice needs. — DoD: the graph matches design.md
  and is acyclic. Slices past S0 are marked as not approved.
- [ ] 8. (depends on 7) Add draft decision text for .github#324: the recommended verdict,
  the conditions, a `DEFER` fallback naming the evidence that would settle it (mctl-api
  and mctl-agents source review), and an explicit statement that the owner decides. —
  DoD: the draft does not claim a decision has been made.
- [ ] 9. (depends on 1) Add references with the observed status as of 2026-11-07:
  #1184 / PR #1187 (implemented, merge not observed), mctl-api#948 (proposed),
  .github#322, #324, #173, mctl-gitops#2456, #2457, #1048, ADR 0008. Include an
  open-questions section copied from requirements.md. — DoD: every link is present and
  no status is upgraded.

## Tests

- [ ] T1. `go test ./docs/...` passes unchanged.
- [ ] T2. `git diff --stat origin/main` shows only `docs/reports/assistant-runtime-boundary-spike.md`.
- [ ] T3. `grep -E 'REUSE_EXISTING|NEW_ASSISTANTS_RUNTIME_REPO|NEW_PROVIDER_ADAPTER_REPO|DEFER'`
  on the verdict line yields exactly one token.
- [ ] T4. Manual review: no real Telegram IDs, names or handles, no credentials, and no
  real Glovo endpoints. Personas are limited to Alice, Bob and Carol.
- [ ] T5. Manual review: every comparison cell and inventory row carries a
  source-backed or model-only label.

## Rollback

Revert the single documentation commit, or delete
`docs/reports/assistant-runtime-boundary-spike.md`. Nothing else is touched: no
code, image, GitOps, flag or credential.
