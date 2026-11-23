# Tasks: issue-2567-fix-glovo-canary-reconcile-staged-gitops

- [ ] 1. Create branch `fix/issue-2567-glovo-staged-drift` from `main`; record the base commit and the
  #2563 state (OPEN/merged, head SHA) for the crosswalk. — DoD: both SHAs written in the PR body.
- [ ] 2. Add pre-fix fixtures under `scripts/fixtures/glovo-m1-prefix/` (copies of facade, provider,
  compatibility, budgets values and both old netpols as at `628471c`). (depends on 1) — DoD: files
  committed, no secret-shaped content.
- [ ] 3. Extend `scripts/validate-glovo-m1-staging.py` with the D1, D2, D5, D6, D7, D8, D9, D11 checks,
  the `FORBIDDEN_ENV` regex, the `_peers()` NetworkPolicy helper and the new render assertions; remove
  the `GLOVO_TEAM_FALLBACK` and provider Temporal requirements; add a selftest case per check plus the
  "pre-fix tree => exit 6" group. (depends on 2) — DoD: on this commit alone, default mode exits 6 on the
  unchanged staged tree (evidence for "fails before fix"), recorded in the PR body.
- [ ] 4. Update `facade/values.yaml` (D1-D4): image `ghcr.io/mctlhq/mctl-glovo-mcp`, `GLOVO_MCP_*` env,
  `GLOVO_MCP_ENABLED: "false"`, plan-only ExternalSecret mounted as a file, no `GLOVO_TEAM_FALLBACK`.
  (depends on 3) — DoD: validator facade checks pass.
- [ ] 5. Update `provider-worker/values.yaml` (D6): drop `TEMPORAL_NAMESPACE` and the Temporal
  ExternalSecret; add bridge env, `FAKE_ONLY`, file-mounted `glovo-provider-bridge` secret, probes on
  `:8081`. (depends on 3) — DoD: provider checks pass; render contains no `TEMPORAL_` env.
- [ ] 6. Replace `netpol/worker-to-temporal.yaml` and `netpol/facade-to-control.yaml` with
  `provider-egress-bridge.yaml`, `facade-egress.yaml`, `control-ingress-deny.yaml`,
  `control-egress.yaml` (D7-D9); update `target-paths.yaml` (D13). (depends on 3) — DoD: kubeconform
  strict passes; peer checks pass; old files gone.
- [ ] 7. Update `control-worker/values.yaml` image (D10) and `provenance.yaml` (D11: names,
  `deployable: false`, `nameStatus`). (depends on 3) — DoD: provenance checks pass; leak guard picks up
  new names.
- [ ] 8. Update `compatibility.yaml`, `budgets.yaml` (D5), `secrets-map.md`,
  `temporal-namespaces.patch.md` (D12), `README.md` (D14). Do not touch `db/`. (depends on 4-7) — DoD:
  no `GLOVO_TEAM_FALLBACK` or provider Temporal namespace anywhere under `deploy/staged/glovo-m1/`.
- [ ] 9. Write CROSSWALK v2 section 7 (D-table with source repo/revision/path/sha256, staged value,
  corrected value, owner, status) and section 8 (activation PR boundaries, P1/P2 human gates, missing
  evidence as UNKNOWN); mark M14-M16 FIXED. (depends on 8) — DoD: every D-row has all columns or an
  explicit UNKNOWN.
- [ ] 10. Update `docs/runbooks/glovo-m1.md` checklists, kill switch and negative test matrix. (depends
  on 8) — DoD: key names match the staged values; tests marked "run in P1/P2".
- [ ] 11. Open the PR (inert, staged-only) with the diff-scope evidence; get independent review; all CI
  green on final HEAD. (depends on 9, 10) — DoD: `validate-manifests` incl. `glovo-m1` green, review
  clean, no approval or activation claimed.

## Tests

- [ ] T1. `scripts/validate-glovo-m1-staging.py --selftest` passes on the final tree, including one case
  per new check (facade image, facade env subset, kill switch on, fallback key present, `*_DB_URL` in a
  worker, provider `TEMPORAL_*` key, provider Temporal secret, provider credential as env value,
  provider egress to `temporal`, provider internet egress, facade egress to control, facade egress to
  `temporal`, control non-empty ingress, `deployable: true` with pending digest).
- [ ] T2. Pre-fix fixture group: the `628471c` content exits 6; output names the failing D-check.
- [ ] T3. Default mode on the commit of task 3 exits 6; on final HEAD exits 0.
- [ ] T4. `helm template` of facade (ingress off/on), provider, control and tenant renders; kubeconform
  `-strict` passes for renders and all `netpol/*.yaml`.
- [ ] T5. Public MCP negative (static): facade render with ingress on has exactly host `glovo.mctl.ai`,
  paths `/mcp` and `/.well-known/oauth-protected-resource`; provider/control renders have no Ingress and
  ClusterIP Services only.
- [ ] T6. Leak guard unchanged: existing selftest cases still refuse Glovo/assistants references in
  `platform-gitops/**`; `git diff --name-only origin/main...HEAD` lists only
  `deploy/staged/glovo-m1/**` (not `db/`), `scripts/validate-glovo-m1-staging.py`,
  `scripts/fixtures/glovo-m1-prefix/**`, `docs/runbooks/glovo-m1.md`.
- [ ] T7. `grep -rn "GLOVO_TEAM_FALLBACK\|mctl-assistants-provider-glovo:write\|TEMPORAL_CLIENT_CREDENTIAL" deploy/staged/glovo-m1 --exclude-dir=db`
  returns only the CROSSWALK history rows.

## Rollback

The change is staged-only and inert: revert the PR commit(s) with `git revert` on a branch and merge
through the normal PR flow. No cluster, DNS, Vault or Temporal state exists to undo. If the new
validator wrongly blocks unrelated PRs, revert only the validator commit; the leak guard predates this
change and stays effective either way.
