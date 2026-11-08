# Tasks: issue-2470-deploy-glovo-m1-gitops-images-oauth-tls

Scope: P0 only. Nothing here may add files under `platform-gitops/services/`,
`platform-gitops/tenants/`, `platform-gitops/infra-components/`,
`platform-gitops/bootstrap/` or `platform-gitops/argo-workflows/`. The one
exception is optional task 7, which needs its own explicit approval.

- [ ] 1. Create `deploy/staged/glovo-m1/README.md` and `gate.yaml`.
  - `gate.yaml` holds phase state: `p0: approved`, `p1: blocked`,
    `p2: blocked`, `p3: out-of-scope`, with an approval issue URL per phase.
  - DoD: README maps P0/P1/P2/P3 to their approvals (#2470, a separate P1
    issue, a separate P2 activation GO), links #2457, .github#324, #2469,
    mctl-agents#1043, mctl-api#953/#954 and mctl-telegram#1048, and states
    that labs is a hosting workspace only.
- [ ] 2. Write `provenance.yaml`, `compatibility.yaml`, `budgets.yaml` and
  `target-paths.yaml` (depends on 1).
  - `provenance.yaml`: one entry per image (facade, provider, control) with
    the GHCR repo, `digest` (`<digest-pending>` allowed in P0), source repo,
    commit SHA, SBOM reference and build run URL.
  - DoD: every staged values file is listed in `target-paths.yaml`, and the
    budgets list the rate limits, cost cap, canary size and kill-switch keys.
- [ ] 3. Write the staged base-service values (depends on 2):
  - `facade/values.yaml`
    - `ingress.enabled: false`
    - `ingress.hosts: [glovo.mctl.ai]`, routing `/mcp` plus
      `/.well-known/oauth-protected-resource` only
    - TLS `glovo-mcp-tls` via `letsencrypt-prod`
    - OAuth issuer/audience env set to the MCTL issuer and resource
      `https://glovo.mctl.ai/mcp`
    - `AUTH_REQUIRED: "true"`
    - fail-closed kill switch, an empty allowlist and team fallback off
    - the hardened security context copied from
      `services/labs/mctl-telegram/values.yaml`
  - `provider-worker/values.yaml`: no Ingress, no exposed Service port, and
    Temporal identity `mctl-assistants-provider-glovo:write` via an
    ExternalSecret reference.
  - `control-worker/values.yaml`: Temporal identity `mctl-assistants:write`.
  - `provider-tenant/values.yaml`: tenant chart values with
    `allowInternetEgress: false`.
  - DoD: `helm template` with base-service (or the tenant chart) succeeds for
    each file, and `kubeconform -strict` passes.
- [ ] 4. Write `secrets-map.md`, `temporal-namespaces.patch.md` and `netpol/`
  (depends on 3).
  - `secrets-map.md`: Vault paths, ExternalSecret names and consumers. No
    values.
  - `temporal-namespaces.patch.md`: the text lines P1 would add to
    `infra-components/data/temporal/tenant-namespace-job.yaml` and to the
    `allow-temporal-ingress` peers.
  - `netpol/`: least-privilege facade->control and worker->Temporal policies.
  - DoD: no secret-shaped value (checked by the existing `security.yml`
    scanning), and the netpols render with kubeconform.
- [ ] 5. Add `scripts/validate-glovo-m1-staging.py` with `--selftest`
  (depends on 3, 4).
  - Checks: render plus kubeconform; the provider has no
    Ingress/LoadBalancer/NodePort; the facade host and paths are exact; the
    fail-closed defaults hold; provenance is checked in P0 or P1 mode
    according to `gate.yaml`.
  - Leak guard: in P0, no `glovo.mctl.ai`, `mctl-assistants`, provider workloads or provenance images may appear in reconciled `platform-gitops/**` (excluding `agents-state/`) **regardless of `gate.yaml` claims**. Later P1/P2 has a separate owner grant and externally verified gate.
  - Exit codes 0/6/7, as in `scripts/release-gate.py`.
  - DoD: the selftest covers each refusal, and the script passes on the P0
    tree.
- [ ] 6. Add a `glovo-m1` job to `.github/workflows/validate-manifests.yml`.
  The job runs the script, the reserved-hosts check on a render with
  `ingress.enabled=true`, and `scripts/validate-argocd-project-scope.py`
  against the target paths (depends on 5).
  - DoD: the job is green on the PR, and it is red on a test commit that adds
    `glovo.mctl.ai` under `platform-gitops/services/labs/` (that commit is
    dropped before merge).
- [ ] 7. (OPTIONAL, separately approvable hardening) Add `glovo.mctl.ai: []`
  to `reservedPlatformHosts` in `platform-gitops/bootstrap/values.yaml`
  (depends on 6).
  - DoD: `scripts/test-reserved-hosts-policy.sh --services --platform`
    passes, and the approver explicitly accepts this live but restrictive
    admission change. P2 later changes the entry to `[labs]`.
- [ ] 8. Write `docs/runbooks/glovo-m1.md` and link it from CLAUDE.md's
  Secrets/runbook list (depends on 1-6). It must include:
  - the P1 checklist (#2469 live evidence, JWT/TLS/authorizer slices,
    #1043 bridge, digests and SBOMs, kuptsi/DevLoop canary)
  - the P2 checklist (reserved host owner, cert, allowlist, explicit team,
    portal decision)
  - the negative test matrix
  - the MCP client smoke test
  - OTel signals
  - the kill switch and rollback procedures
  - canary limits
  - DoD: every acceptance criterion of #2470 is mapped to a phase and to an
    evidence slot.
- [ ] 9. After merge, verify that nothing went live.
  - DoD: `mctl_list_services labs` still shows 21 apps with no glovo entry,
    and there is no new Argo CD Application or Temporal namespace. The
    evidence is commented on #2470.

## AMEND 2026-11-08 — security tests for release approval provenance

- [ ] A1. CI **unconditionally** rejects new reconciled Glovo host, provider/control images and assistant namespaces in P0; `gate.yaml` cannot enable a P1/P2 exception.
- [ ] A2. Fake PR test: `gate.yaml p1:approved,p2:approved` plus forged approval issue URL AND reconciled valid provider Deployment; validator returns exit 6, never a pass or skip.
- [ ] A3. `gate.yaml` is explicitly informational. A future P1/P2 owner grant must be verified via trusted evidence outside PR-modifiable content, bound to phase/environment/manifest digest/image digest; without it rollout stays BLOCKED.
- [ ] A4. P0 contains no live GitOps apply, Temporal auth/namespaces, Cloudflare DNS, JWT credentials or user activation. The actual P1 and P2 remain separate issues and explicit owner approvals.

## Tests

- [ ] T1. `helm template` plus `kubeconform -strict` for every staged values
  file, with both `ingress.enabled=false` and `ingress.enabled=true`.
- [ ] T2. Leak guard negative test: `glovo.mctl.ai` in
  `platform-gitops/services/labs/x/values.yaml` makes the script exit 6. The
  same host in `deploy/staged/` passes.
- [ ] T3. A provider render with an added Ingress or a NodePort Service exits 6.
- [ ] T4. A facade with `GLOVO_ENABLED: "true"`, a non-empty allowlist or team
  fallback on while `gate.yaml` has `p2: blocked` exits 6.
- [ ] T5. Provenance: `<digest-pending>` passes with `p1: blocked` and fails
  with `p1: approved`. A semver tag in place of a digest fails in both modes.
- [ ] T6. A missing or unreadable `gate.yaml` exits 7 (refusal, not pass).
- [ ] T7. The reserved-hosts check on the `ingress.enabled=true` render: with
  task 7 applied, `glovo.mctl.ai` in labs is refused until the owner becomes
  `[labs]`.
- [ ] T8. Recorded in the runbook for P1/P2 execution, not run in P0. The
  negative matrix: two tenants with distinct users, foreign connection/order
  access, a missing or wrong audience, a revoked install, a replayed `aar_`,
  a provider calling control/DevLoop, an expired JWT, and fake basket
  idempotency.

## Rollback

P0 adds only non-reconciled files, one script and one CI job. To roll back,
revert the P0 PR. There is no cluster state to clean up. If optional task 7
was merged and blocks something unexpected, revert that commit alone. The
admission policy reloads from `reservedPlatformHosts` on the next bootstrap
sync. Rollback for P1/P2 (revert the activation PR so Argo CD prunes, kill
switch first) is defined in `docs/runbooks/glovo-m1.md` and is exercised in
those phases, not here.
