# Design: prometheus-security-patch

## Current state

Prometheus v3.11.3 is the latest upstream release as of 2026-05-03. The platform deploys
Prometheus through Helm chart values files managed in this GitOps repository. Version pins
for the Prometheus image and Helm chart are scattered across:

- `platform-gitops/services/<tenant>/prometheus/` — per-tenant values overrides
- `platform-gitops/helm-charts/base-service/` — shared base chart defaults

The actual pinned values have not been audited against v3.11.3. It is possible that one or
more files still reference an earlier patch version. Additionally, the Prometheus configuration
may not explicitly set `auth.credentials_in_debug_log: false` (or the equivalent flag in
v3.11.x), leaving credential exposure as a latent risk if debug logging is ever enabled.

Three security issues are addressed by v3.11.3:
1. AzureAD OAuth credential exposure in logs.
2. Snappy decompression DoS on the remote-write endpoint.
3. Stored XSS in the heatmap chart UI.

## Proposed solution

The solution is a targeted values-file audit and update:

**Step 1 — Audit.**
Use `grep` across `platform-gitops/services/` and `platform-gitops/helm-charts/` to locate
every reference to a Prometheus image tag or Helm chart version. Produce a list of all files
and their current pin values.

**Step 2 — Update version pins.**
For every file referencing a Prometheus image tag or chart version below v3.11.3, update
the pin to `v3.11.3`. This is a one-line change per file. ArgoCD will detect the diff and
reconcile on the next sync cycle.

**Step 3 — Audit credential logging configuration.**
Check each Prometheus values file for the `auth.credentials_in_debug_log` key (or its
equivalent in the chart's `values.yaml`). If the key is absent or set to `true`, add or
correct it to `false`. This ensures the AzureAD credential exposure fix is active at the
configuration level even if it is also patched in the binary.

**Step 4 — Commit and verify sync.**
Commit all changes in a single PR. After ArgoCD syncs, verify the running Prometheus pod
image tag matches v3.11.3.

This is a pure configuration change. No new components are introduced and no schema changes
are required.

## Alternatives

**Wait for an operator auto-update pipeline.**
Some teams rely on Renovate Bot or Dependabot to bump version pins automatically. No such
pipeline is configured for this repository. Waiting would leave the credential exposure
vulnerability active for an indeterminate period. Rejected.

**Full Prometheus Operator upgrade.**
Upgrading the Prometheus Operator itself would bundle the patch but introduces broader
surface area changes (CRD versions, RBAC, webhook configurations). The risk surface is
much larger than needed for a patch-level image pin update. Rejected for this proposal;
tracked separately.

**Pin to latest floating tag (`:latest` or `:v3`).**
Using a floating tag would always pull the newest image on pod restart, removing the need
for manual pin management. However, this violates the platform's GitOps immutability
principle and makes rollback impossible. Rejected.

## Platform impact

- **Migrations:** None. Prometheus configuration schema is unchanged between the
  pre-patch version and v3.11.3.
- **Backward compatibility:** Patch-level update (v3.11.x). No breaking API or
  configuration changes expected. Prometheus data on-disk is not affected.
- **Resource impact:** A patch-level image update has no expected memory or CPU delta.
  No `labs` memory risk. If `labs` runs Prometheus, this proposal has no adverse impact
  on its memory quota.
- **Risks and mitigations:**
  - Risk: The pin update triggers a Prometheus pod restart, causing a brief scrape gap.
    Mitigation: ArgoCD rolling update strategy ensures a short (seconds-level) gap; alert
    rules are unaffected.
  - Risk: A values file has an undocumented transitive dependency on an older Prometheus
    feature removed in v3.11.3. Mitigation: review the v3.11.3 changelog for breaking
    changes before committing; no breaking changes are documented for this patch release.
