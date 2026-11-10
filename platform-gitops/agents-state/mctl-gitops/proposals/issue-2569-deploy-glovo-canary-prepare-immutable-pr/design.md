# Design: issue-2569-deploy-glovo-canary-prepare-immutable-pr

## Current state

### The inert package from #2470

- `deploy/staged/glovo-m1/` holds staged values, nothing more. Its README states that no Argo CD
  ApplicationSet, Application or `manifest-generate-paths` matches `deploy/`. The package contains:
  - `facade/values.yaml`, chart base-service, target `services/labs/glovo-mcp`, P2. It sets
    `ingress.enabled: false`, host `glovo.mctl.ai` with path `/mcp`, and an `extraIngresses` entry for
    `/.well-known/oauth-protected-resource`. Its env includes `OAUTH_RESOURCE`, `GLOVO_ENABLED: "false"`,
    `GLOVO_ALLOWLIST: ""` and the withdrawn `GLOVO_TEAM_FALLBACK: "false"`. The image is `tag: "0.0.0"`
    with no digest.
  - `provider-worker/values.yaml`. It still carries `TEMPORAL_NAMESPACE: mctl-assistants-provider-glovo`
    and a `glovo-provider-temporal` ExternalSecret. That is obsolete per README "Obsolete staged
    artifacts" and CROSSWALK M15, because the provider is now a #968 bridge client (tg#1262).
  - `control-worker/values.yaml`, target `services/admins/assistants-control`, with
    `TEMPORAL_NAMESPACE: mctl-assistants`.
  - `provider-tenant/values.yaml`, chart tenant, with `allowClusterEgress: false` and
    `allowInternetEgress: false`.
  - `netpol/facade-to-control.yaml`, ingress to the control worker from `labs-glovo-mcp`. This does not
    match CROSSWALK section 1, where the facade talks only to mctl-api `/api/v1/glovo/facade/*`.
  - `netpol/worker-to-temporal.yaml`, provider egress to Temporal 7233. Obsolete (M15).
  - `provenance.yaml`: repository, digest, sourceRepo, commit, sbom and buildRun, all `<...-pending>`. It
    has no vulnerability scan, no provenance attestation, no release owner and no GHCR-confirmed flag.
  - `compatibility.yaml` and `budgets.yaml` both still list `GLOVO_TEAM_FALLBACK` (M14).
  - `gate.yaml` is informational and never an unlock. `target-paths.yaml` maps each file to its target.
    `secrets-map.md` is names only. `temporal-namespaces.patch.md` still lists the provider namespace
    (M15). `CROSSWALK.md` holds contracts C1-C10, mismatches M1-M17 and the ordered gates.
- `scripts/validate-glovo-m1-staging.py` (309 lines) does the following:
  - `check_staged_values` asserts the facade/provider/control/tenant invariants. It currently *requires*
    the obsolete provider `TEMPORAL_NAMESPACE` and ExternalSecret, and requires `GLOVO_TEAM_FALLBACK ==
    "false"`.
  - `check_provenance` checks shape only.
  - `leak_guard` is deny-only on `platform-gitops/**` (excluding `agents-state/`), using regex
    `glovo|mctl-assistants` plus the staged image repositories.
  - `render_checks` runs helm template and kubeconform on the three values files, the tenant and
    `netpol/*.yaml`.
  - `--selftest` mutates a fixture copy and expects refusal.
  - Exit codes are 0, 6 (refused) and 7 (unknown).
- `.github/workflows/validate-manifests.yml` job `glovo-m1` (around line 1129) installs Helm v3.16.4 and
  kubeconform, then runs `--selftest` followed by the full validator.
- `docs/runbooks/glovo-m1.md` describes the inertness argument (prune/selfHeal ApplicationSet plus the
  proxied `*.mctl.ai` wildcard DNS), the phase map, the P1/P2 checklists, the negative matrix, the kill
  switch and rollback.

### Related platform facts

- `platform-gitops/helm-charts/base-service/values.yaml:9-10` already supports `image.digest`
  (`sha256:<64 hex>`, rendered as `repository:tag@digest` via `base-service.imageRef` in
  `templates/deployment.yaml:67`). Digest pinning therefore needs no chart change.
- `platform-gitops/bootstrap/values.yaml` `reservedPlatformHosts` (lines ~553-587) is enforced by
  `bootstrap/templates/system/admission-policies.yaml`. `glovo.mctl.ai` is not reserved; the runbook
  defers that to P2.
- `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml` declares the `managed.roles`
  (`mctl-api` at line 191), and `databases.yaml` lines 48-89 give the mctl-api databases, owned by role
  `mctl-api`. No Glovo roles exist, and adding one there would trip the leak guard by design.
- `platform-gitops/infra-components/data/temporal/tenant-namespace-job.yaml` registers only `kuptsi` and
  `mctl-agents`. `networkpolicy.yaml` admits mctl-api, the admins mctl-agents workers and kuptsi-app.
  Per CROSSWALK section 4 there is no Temporal client auth yet.
- The image supply-chain pattern in this repo is `.github/workflows/erpact-images.yaml`. It pushes, then
  reads the digest with `regctl image digest` (line 257) and exports it. Facade/provider/control images
  are built in mctl-telegram and mctl-agents, not here.
- The F2 roles `glovo_migrator` (DDL through `glovo.ApplySchema`) and `glovo_runtime` (DML only) are
  named in `platform-gitops/agents-state/mctl-api/proposals/issue-990-.../requirements.md` (amendment
  F2) and in CROSSWALK C3.
- The holds are documented in
  `agents-state/mctl-gitops/proposals/issue-2523-deploy-plan-mctl-api-4-155-0-dark-bridge/` and
  `issue-2528-security-release-enforce-mctl-api-4-155/`: the release hold on mctl-api 4.155.0 (#934),
  which depends on mctl-agents#993 Part M and #1007 B4.

### Deployed state checked

- `bootstrap/templates/mctl-platform/mctl-api.yaml:45` pins mctl-api to `tag: "4.154.0"`, with no
  `GLOVO`/`BRIDGE` env in the file (grep). This matches the #2523/#2528 proposals: 4.155.0 is held.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` shows image `ghcr.io/mctlhq/mctl-telegram`,
  tag `0.137.1`.
- `mctl_get_service_status(labs, mctl-telegram)` returned Synced/Healthy, tag 0.137.1, host `tg.mctl.ai`.
  No Glovo facade is deployed.
- `mctl_list_services(admins)` returned `complete: true`, 8 services, none of them `assistants-control`
  or Glovo-related.
- `$MCTL_GITOPS_ROOT/services` lists tenants admins, karabu, labs and namax66, and `tenants/` lists
  admins, commerce-proof, erpact, karabu, labs, mctl and namax66. There is no
  `mctl-assistants-provider-glovo` tenant.
- Not observed: GHCR for `ghcr.io/mctlhq/glovo-*` (no tool in this run). Image existence is unknown, not
  absent. mctl-api#1004 and A15 #2563 content was not readable at a pinned revision here. Live Temporal
  namespaces were not observed (CROSSWALK already marks them `NOT_OBSERVED`).

## Proposed solution

Evolve `deploy/staged/glovo-m1/` in place. The validator, CI job and runbook already treat it as the
inert package, and `target-paths.yaml` is its single map to targets. Every change is under `deploy/`,
`scripts/`, `docs/` and one CI job. Nothing reconciled changes.

### 1. Contract drift fixes (CROSSWALK M14-M16 plus the facade netpol)

- `provider-worker/values.yaml`: remove `TEMPORAL_NAMESPACE`, `envFrom` and the Temporal
  `extraExternalSecrets`. Add the `MCTL_BRIDGE_URL` placeholder and a bridge-provider credential
  ExternalSecret (`glovo-provider-bridge`, Vault path
  `teams/mctl-assistants-provider-glovo/provider-worker/bridge`, a name only, issuer gated on
  #2506/#2540).
- Replace `netpol/worker-to-temporal.yaml` with `netpol/provider-egress-bridge.yaml`. It allows egress
  to DNS (kube-system 53) and the `mctl-api` namespace on the API port only.
- Replace `netpol/facade-to-control.yaml` with three files:
  - `netpol/facade-egress.yaml`: facade egress to DNS, the `mctl-api` namespace and the ZITADEL issuer
    (for JWKS).
  - `netpol/control-ingress-deny.yaml`: the control worker accepts no ingress except metrics scraping
    from `monitoring`.
  - `netpol/control-egress.yaml`: the control worker egresses only to DNS, Temporal 7233 and mctl-api.
- `compatibility.yaml` and `budgets.yaml`: drop `GLOVO_TEAM_FALLBACK`. `temporal-namespaces.patch.md`:
  drop the provider namespace and keep `mctl-assistants`.
- README: fix the M16 link, and replace the "Obsolete staged artifacts" section with a "Resolved in
  #2569" note.
- `secrets-map.md`: update the provider row, and add the facade OAuth audience row (none: public JWKS)
  and the mctl-api migration rows (names only).

### 2. MCP ingress, OAuth and the team selector (`facade/values.yaml`)

- Add `image.digest: ""` beside `tag`, so P1 fills one field. The validator allows only an empty value
  or `sha256:<64 hex>`.
- Keep `ingress.enabled: false`, the host, `/mcp` and the protected-resource metadata path. Add Traefik
  HTTPS-only annotations: `traefik.ingress.kubernetes.io/router.entrypoints: websecure` and
  `router.tls: "true"`.
- Env:
  - Keep `OAUTH_ISSUER_URL`, `OAUTH_RESOURCE=https://glovo.mctl.ai/mcp` (the audience) and
    `MCTL_API_URL=https://api.mctl.ai`.
  - Add `OAUTH_PROTECTED_RESOURCE_METADATA=https://glovo.mctl.ai/.well-known/oauth-protected-resource`.
  - Add `GLOVO_TEAM_SELECTOR: explicit`.
  - Keep `GLOVO_ENABLED: "false"` and `GLOVO_ALLOWLIST: ""`.
  - Remove `GLOVO_TEAM_FALLBACK`.
  - Key names stay placeholders bound by `compatibility.yaml` (tg#1264).
- Add a readiness probe on `/readyz`, so a 503-only service never reports Ready. Also add the
  base-service `otel` block, as the runbook OTel section expects.
- `dns.patch.md` (text only): P2 adds `glovo.mctl.ai: [labs]` to `reservedPlatformHosts` in the same PR
  as the Ingress. It states that the proxied wildcard already resolves, so no Cloudflare record is
  created, and that the certificate `glovo-mcp-tls` comes from `letsencrypt-prod`.

### 3. Immutable image contract (`provenance.yaml`, new `images.md`)

- Per image, `provenance.yaml` gains `sourceHead` (renamed from `commit`), `buildWorkflow` (repo path of
  the CI workflow), `provenanceAttestation`, `vulnScan` (report URL plus a severity gate), `releaseOwner`
  and `ghcrConfirmed: false`. All other fields stay `<...-pending>`.
- `images.md` gives the build contract each source repo must meet:
  - The image is built from a pinned HEAD, on a pinned runner image and pinned actions.
  - `regctl image digest` (or `docker buildx` metadata) is the digest source, following
    `erpact-images.yaml:257`.
  - The SBOM is SPDX, provenance comes from `actions/attest-build-provenance`, and the vulnerability scan
    blocks on critical.
  - Publishing happens only through the source repo's separately authorized release gate.
- Three images: facade from mctl-telegram (tg#1235/#1259 plus the #1264 fix), provider from
  mctl-telegram (tg#1262), control from mctl-agents (#1044). Building is out of scope here.

### 4. Staged mctl-api F2 migration (`api-migration/`)

- `api-migration/roles.patch.md` (text): add the roles `glovo_migrator` (owns the Glovo schema, DDL) and
  `glovo_runtime` (DML grants only, no ownership) as shared-pg managed roles with Vault-backed
  passwords, *or* have them created by A15, whichever #1004/A15 decides. The patch quotes the exact
  `cluster.yaml` and `databases.yaml` hunks P1 would apply.
- `api-migration/migration-job.yaml`: a staged `batch/v1` Job that runs the mctl-api image (digest
  placeholder) with `glovo-migrate`, `envFrom` a `glovo-migrator-db` Secret, `restartPolicy: Never`,
  `backoffLimit: 0` and the hardened securityContext. It is rendered by kubeconform only.
- `api-migration/grants-proof.sql`: read-only queries that produce the evidence for the
  `db-migration-grants` slot. They check table owner = `glovo_migrator`, that `glovo_runtime` has no
  `CREATE` on the schema, and that `glovo_runtime` has no `TRUNCATE`/`REFERENCES`.

### 5. Evidence checklist and hold registry

- `evidence.yaml`, one slot per item, each `{phase, owner, status: pending, evidence: ""}`. The slots
  are: `manifest-digest`, `image-digests`, `owner-grant-p1`, `owner-grant-p2`, `argo-synced-healthy`,
  `db-migration-grants`, `temporal-security-decision`, `scoped-secret-issuance`, `readiness-metrics`,
  `kill-switch-drill`, `rollback-drill`, `negative-matrix-2x2` (mctl-api#990), `mcp-client-e2e`,
  `oauth-two-tenant-isolation`, `approval-fence-revocation-ambiguous`, `operator-allowlist` and
  `not-503-only`.
- `holds.yaml` lists the holds with `{ref, owner, requiredApproval, evidence, state: held}`:
  - `mctl-api#934` (release hold)
  - `mctl-gitops#2523`
  - `mctl-gitops#2528`
  - `mctl-gitops#2457-p1`
  - `mctl-gitops#2457-p2`
  - `mctl-api#1004`
  - `temporal-isolation` (CROSSWALK section 4 node H)
  - `mctl-agents#993`
  - `mctl-agents#1007-b4`
- Both files carry the `gate.yaml` banner: informational, PR-editable, never an unlock.
- `EVIDENCE.md` gives each slot its procedure, in prose. The runbook P1/P2 checklists point at it.

### 6. Validator and CI

`scripts/validate-glovo-m1-staging.py`:

- Invert the provider check: refuse `TEMPORAL_*` and any Temporal ExternalSecret.
- Refuse `GLOVO_TEAM_FALLBACK` anywhere under `STAGED`.
- Require `GLOVO_TEAM_SELECTOR == "explicit"`.
- Check the `image.digest` format.
- Extend `check_provenance` with the new keys and the `ghcrConfirmed` consistency rule.
- Add `check_evidence` (every required slot present; all `pending` in P0) and `check_holds` (exact
  required set; never consulted by `leak_guard`).
- Add `--policy p1` (`check_provenance_p1`: no pending field), exercised by selftest only.
- `render_checks` adds a pass with `--set image.digest=sha256:<zeros>` for each values file, plus
  kubeconform on `api-migration/*.yaml` and every netpol.
- New selftest cases for each new refusal.

`target-paths.yaml` lists the new netpols and the migration Job.

The CI job `glovo-m1` stays as is. It already runs `--selftest` then the full run. Only its trigger
comment is updated.

## Alternatives

1. **A new package `deploy/staged/glovo-canary/`, keeping `glovo-m1/` as history.** Dropped. It forks
   the validator, `target-paths.yaml` and runbook, and gives two sources of truth for the same
   `glovo.mctl.ai` target. The leak guard is global anyway.
2. **Stage directly in `platform-gitops/services/labs/glovo-mcp/` with `ingress.enabled: false` and no
   Application, or a disabled ApplicationSet selector.** Dropped. The `apps` ApplicationSet syncs every
   `services/*/*` with prune/selfHeal (runbook "Why it is inert"), so a values file there would deploy
   the facade within seconds. That breaks P0 "no apply". It would also require weakening the leak guard.
3. **Build and publish the three images from this repo (like `erpact-images.yaml`).** Dropped. The
   sources live in mctl-telegram and mctl-agents, and the issue requires releases to go through a
   separately authorized gate. Here we record only the contract and the confirmed outputs.
4. **Enforce the P1 provenance policy in CI now.** Dropped. The runbook says that changing the CI policy
   is part of the P1 activation PR, behind a trusted grant. Shipping it as selftest-only proves that the
   detector works without changing the gate.

## Platform impact

- **Cluster:** none. No reconciled path changes. The leak guard and the new checks run on every PR via
  the existing `glovo-m1` job. CI time grows by a few helm renders, under a minute.
- **Backward compatibility:** the validator now refuses the old provider Temporal shape and
  `GLOVO_TEAM_FALLBACK`. Both are only in `deploy/staged/glovo-m1/`, which this PR rewrites in the same
  commit.
- **Risks and mitigations:**
  - *Someone reads `evidence.yaml`, `holds.yaml` or `provenance.yaml` as approval.* Each file carries the
    banner. The validator never treats them as unlocks. P0 requires all slots pending and all holds
    `held`.
  - *A future P1 PR copies the facade values into `services/labs/` with `ingress.enabled: true`.* The
    leak guard refuses this until the P1/P2 PR changes the CI policy under a trusted grant (runbook).
  - *Placeholder env keys diverge from the merged facade (tg#1264).* `compatibility.yaml.envKeys` is the
    single list. P1 must refuse a mismatch. This is recorded as an open question.
  - *The staged migration Job is mistaken for runnable.* It lives under `deploy/`, uses a pending digest
    and references a Secret that does not exist.
  - *DNS:* the wildcard already resolves `glovo.mctl.ai` to traefik. Without an Ingress it returns 404,
    not the service. P2 reserves the host in the same PR as the Ingress.
