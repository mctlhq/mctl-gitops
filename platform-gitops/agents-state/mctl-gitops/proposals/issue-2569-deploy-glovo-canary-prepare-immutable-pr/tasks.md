# Tasks: issue-2569-deploy-glovo-canary-prepare-immutable-pr

- [ ] 1. Fix the provider drift (M15). In `deploy/staged/glovo-m1/provider-worker/values.yaml`, remove
  `TEMPORAL_NAMESPACE`, `envFrom` and the Temporal ExternalSecret, and add the `MCTL_BRIDGE_URL`
  placeholder and the `glovo-provider-bridge` ExternalSecret (names only). Replace
  `netpol/worker-to-temporal.yaml` with `netpol/provider-egress-bridge.yaml` (DNS plus the `mctl-api`
  namespace only). Drop the provider namespace from `temporal-namespaces.patch.md`.
  - DoD: no `TEMPORAL` string in the provider files, and the new netpol passes `kubeconform -strict`.
- [ ] 2. Replace `netpol/facade-to-control.yaml` with `netpol/facade-egress.yaml`,
  `netpol/control-ingress-deny.yaml` and `netpol/control-egress.yaml`, matching CROSSWALK section 1
  (the facade talks to mctl-api only).
  - DoD: all three render and pass kubeconform, and `target-paths.yaml` lists them at phase p1.
- [ ] 3. Update `facade/values.yaml`:
  - add `image.digest: ""`, the HTTPS-only traefik annotations and `OAUTH_PROTECTED_RESOURCE_METADATA`;
  - add `GLOVO_TEAM_SELECTOR: explicit` and `MCTL_API_URL`;
  - add a `/readyz` readiness probe and the `otel` block;
  - remove `GLOVO_TEAM_FALLBACK`.

  Drop `GLOVO_TEAM_FALLBACK` from `compatibility.yaml` and `budgets.yaml`, and add the new keys to
  `compatibility.yaml.envKeys`.
  - DoD: the facade still has `ingress.enabled: false`, `GLOVO_ENABLED: "false"` and an empty allowlist.
- [ ] 4. Add `dns.patch.md`: the text-only P2 hunk for `reservedPlatformHosts` (`glovo.mctl.ai:
  [labs]`), the wildcard DNS note and the `glovo-mcp-tls` / `letsencrypt-prod` certificate.
  - DoD: no reconciled file changes.
- [ ] 5. Extend `provenance.yaml` with `sourceHead`, `buildWorkflow`, `provenanceAttestation`,
  `vulnScan`, `releaseOwner` and `ghcrConfirmed: false` for facade, provider and control. Add `images.md`
  with the per-repo build contract (pinned HEAD, digest via regctl, SPDX SBOM, attest-build-provenance,
  a vulnerability gate that blocks on critical, a separately authorized release).
  - DoD: every field is pending or well-formed, and no digest is claimed.
- [ ] 6. Add `api-migration/`:
  - `roles.patch.md`, with the `glovo_migrator`/`glovo_runtime` hunks for shared-pg
    `cluster.yaml`/`databases.yaml`, marked as decided by mctl-api#1004 / A15 #2563;
  - `migration-job.yaml`, a staged Job with a pending digest, `backoffLimit: 0` and a hardened context;
  - `grants-proof.sql`, read-only ownership and grant queries.

  Update `secrets-map.md`.
  - DoD: the Job passes kubeconform, and nothing under `platform-gitops/infra-components/` changes.
- [ ] 7. Add `evidence.yaml`, `EVIDENCE.md` and `holds.yaml`, each with the informational banner. Use
  the slot list and hold list from design.md section 5.
  - DoD: every slot is `pending` with empty evidence, and every hold is `held` with owner and
    requiredApproval filled (`<owner-pending>` where unknown).
- [ ] 8. (depends on 1-7) Update `scripts/validate-glovo-m1-staging.py`:
  - invert the provider check;
  - refuse `GLOVO_TEAM_FALLBACK` under `STAGED`;
  - require `GLOVO_TEAM_SELECTOR == "explicit"`;
  - validate the `image.digest` format;
  - extend `check_provenance` with the new keys and the `ghcrConfirmed` rule;
  - add `check_evidence` and `check_holds`;
  - add `--policy p1` (selftest only);
  - render with a sample digest, and run kubeconform on `api-migration/*.yaml`.

  Extend `target-paths.yaml`.
  - DoD: `--selftest` and the full run both exit 0 locally, and every new refusal has a selftest case.
- [ ] 9. (depends on 8) Update `README.md` (fix the M16 link, replace the obsolete-artifacts section),
  `CROSSWALK.md` (mark M14-M16 resolved by #2569), `docs/runbooks/glovo-m1.md` (point the P1/P2
  checklists at `EVIDENCE.md`/`holds.yaml`) and the comment on the `glovo-m1` CI job.
  - DoD: the docs are consistent, and no runbook step implies approval.

## Tests

- [ ] T1. `scripts/validate-glovo-m1-staging.py --selftest` exits 0, and each of these mutations is
  refused (exit 6):
  - a provider `TEMPORAL_NAMESPACE`;
  - `GLOVO_TEAM_FALLBACK` in any staged file;
  - `GLOVO_TEAM_SELECTOR` other than `explicit`;
  - a malformed `image.digest`;
  - `ghcrConfirmed: true` with a pending digest;
  - a missing provenance key;
  - a missing evidence slot;
  - an evidence slot not pending;
  - a missing hold;
  - `ingress.enabled: true`;
  - a non-empty allowlist;
  - a Glovo file under `platform-gitops/services/`.
- [ ] T2. `--policy p1` against the P0 tree is refused, which proves the P1 detector fires on pending
  fields. It passes on a fixture with complete fields.
- [ ] T3. The full validator run exits 0 on the PR tree with helm and kubeconform installed. Each values
  file renders with and without a sample digest. The netpols and the migration Job pass
  `kubeconform -strict`.
- [ ] T4. The `glovo-m1` CI job is green on the PR, and `git diff --stat origin/main` shows no path under
  `platform-gitops/` except `agents-state/`.
- [ ] T5. Manual: `helm template` of the facade with `ingress.enabled=true` shows exactly two Ingress
  paths (`/mcp`, `/.well-known/oauth-protected-resource`) on host `glovo.mctl.ai`, with TLS secret
  `glovo-mcp-tls`.

## Rollback

P0 creates no cluster, DNS, Vault, Temporal or registry state. Rollback is a revert of the P0 PR: the
staged package and validator go back to the #2470 shape, and the leak guard keeps working in both
versions. If the new validator wrongly blocks unrelated PRs, revert only the validator commit; the
staged files are inert on their own.
