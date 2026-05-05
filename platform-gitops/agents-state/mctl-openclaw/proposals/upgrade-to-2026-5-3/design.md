# Design: upgrade-to-2026-5-3

## Current state

All three tenants (`labs`, `admins`, `ovk`) run **openclaw 2026.3.14**. Deployments are managed through Docker image → mctl-gitops → ArgoCD, with per-tenant Helm value files in separate Kubernetes namespaces. Per-tenant S3 buckets store auth tokens and channel sessions. The `restore-state` readiness probe must pass before a pod is declared ready; an Argo CronWorkflow s3-sync canary validates ongoing S3 write health (see `context/architecture.md` §"State guards"). Promotion order is mandated by ADR-0001: `labs → admins → ovk`, with observation periods between each step.

The current version carries six unpatched HIGH/MEDIUM CVEs:

| CVE | CVSS | Description | Fixed in |
|---|---|---|---|
| CVE-2026-41394 | 8.8 | Unauthenticated plugin-auth HTTP routes receive operator write scope | 2026.3.31 |
| CVE-2026-42422 | 8.8 | `device.token.rotate` role bypass | 2026.4.29 |
| CVE-2026-33579 | — | Directory traversal + command injection in device pairing | 2026.5.3 |
| CVE-2026-41390 | 7.3 | Exec allowlist bypass via shell-script wrappers | 2026.3.28 |
| CVE-2026-41395 | 7.5/8.2 | Plivo webhook replay bypass via query-parameter reordering | 2026.3.28 |
| CVE-2026-41358 | 5.4 | Slack prompt injection | 2026.5.3 |

The prior proposal `upgrade-to-2026-5-2` identified v2026.5.2 as the target but did not execute. v2026.5.2 has since been found to carry two regressions — a gateway crash at approximately the 12-hour uptime mark and a Feishu channel authentication incompatibility — both resolved in v2026.5.3. The correct and only current stable promotion target is **v2026.5.3**.

## Proposed solution

**Bump the openclaw image tag from `2026.3.14` to `2026.5.3`** in each tenant's Helm values file inside mctl-gitops, following the mandatory promotion sequence from ADR-0001:

```
labs  →  (24 h soak)  →  admins  →  (24 h soak)  →  ovk
```

### Rollout procedure per tenant (ADR-0002 compliant)

1. **Stop the s3-sync canary** for the target tenant by setting `.spec.suspend: true` on the Argo CronWorkflow object.
2. Open a gitops PR updating `image.tag` to `2026.5.3` in the target tenant's `values.yaml`.
3. Merge the PR; ArgoCD syncs and schedules the new pod.
4. **Monitor the `restore-state` readiness probe.** ArgoCD will not mark the rollout successful until the probe passes. Do not proceed past this step manually.
5. **Restart the s3-sync canary** after the post-rollout delay specified in ADR-0002.
6. **24-hour soak** — observe: s3-sync canary health, pod RSS memory (critical for `labs`), channel connectivity across all active channels, gateway uptime past the 12-hour mark (regression regression-check for the v2026.5.2 crash), Feishu authentication (regression check for the v2026.5.2 incompatibility), and absence of restore-state probe failures.
7. If the soak is clean, proceed to the next tenant; otherwise investigate and hold.

### Scheduling for `ovk`

The `ovk` rollout must be scheduled during the pre-approved low-traffic maintenance window. Restarts of `ovk` are painful (high SLA per `context/architecture.md`). The 24-hour soak on `admins` is the final automated gate before `ovk` is touched.

### What v2026.5.3 changes for this deployment

**Security fixes (directly motivated):**
- Closes all six CVEs listed above.
- Carries forward all security fixes from the 2026.3.x and 2026.4.x series that were confirmed present in v2026.5.2 (log credential sanitization, SSRF guards, plugin integrity verification, gateway auth-profile startup fix).

**Regression fixes relative to v2026.5.2:**
- Gateway crash at ~12 h uptime: resolved in v2026.5.3.
- Feishu channel authentication incompatibility: resolved in v2026.5.3.

**Memory footprint (positive for `labs`):**
- Inherits v2026.5.2's externalization of `@openclaw/acpx` and `@openclaw/diagnostics-otel` as opt-in peer dependencies (not installed by default). Net RSS delta for `labs` is expected to be zero or negative, consistent with the assessment made in `upgrade-to-2026-5-2/design.md`.

**New opt-in feature (NOT activated in this proposal):**
- `git:` plugin installs — explicitly kept disabled. Tracked in `git-plugin-install-allowlist`.

### No net-new npm dependencies

The externalization of `@openclaw/acpx` and `@openclaw/diagnostics-otel` reduces the default dependency tree. No net-new npm packages are added to the base install.

## Alternatives

**A. Stay on 2026.3.14 and cherry-pick individual CVE patches.**
Rejected. The upstream project does not backport security patches. The six CVEs span commits from 2026.3.28 through 2026.5.3; maintaining a diverged fork branch with six cherry-picks is operationally unsustainable and untestable against the upstream CI matrix.

**B. Upgrade to v2026.5.2 as specified in the prior proposal.**
Rejected. v2026.5.2 has confirmed regressions (gateway crash at ~12 h, Feishu auth incompatibility). Rolling out a known-broken release to `labs` would consume rollout capacity without improving security posture and would need to be immediately superseded by a second rollout to v2026.5.3. Targeting v2026.5.3 directly is strictly better.

**C. Upgrade all three tenants simultaneously.**
Rejected by ADR-0001. Simultaneous upgrade eliminates `labs` as a canary. If v2026.5.3 carries an unexpected regression, it would immediately reach the production `ovk` tenant with no rollback gate. The sequential promotion sequence is mandatory and non-negotiable.

## Platform impact

### Migrations

None required. The 2026.3.14 → 2026.5.3 path is a same-major upgrade series; no S3 schema changes, no Helm value renames, no plugin SDK breaking changes. Existing YAML skills in all three tenants are fully compatible.

### Backward compatibility

The 2026.4.x and 2026.5.x series do not break the plugin SDK or REST API surface used by `extensions/*` packages. The `device.token.rotate` bearer-token response format was corrected in an earlier 2026.4.x release; any internal tooling or script that parses the rotated-token response must be verified before the `ovk` rollout. This audit is an explicit prerequisite gate tracked in tasks.md.

### Resource impact (especially for `labs`)

- Inherits the footprint reduction from v2026.5.2: `@openclaw/acpx` and `@openclaw/diagnostics-otel` are no longer installed by default.
- The `labs` tenant is flagged as close to its memory limit per `context/architecture.md`. This upgrade is assessed as **low risk** for `labs` and may free headroom.
- Empirical RSS measurements at 1 h, 6 h, and 24 h during the `labs` soak will confirm the delta. If RSS increases by more than +50 MB above the pre-upgrade baseline, promotion to `admins` is blocked until an operator provides explicit written sign-off.
- New opt-in packages are NOT installed in this proposal; they contribute zero footprint.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Restore-state probe timeout during S3 restore | Do not reduce probe timeout; the startup-latency improvement inherited from v2026.5.2 reduces this risk. Log restore progress during `labs` soak. |
| False s3-sync canary alerts during rollout pause/restart | Follow ADR-0002: stop → rollout → delayed restart; apply alert suppression window during the deliberate stop interval. |
| Memory regression in `labs` (unlikely given footprint reduction) | Measure RSS at 1 h, 6 h, 24 h post-upgrade. Block promotion on > 50 MB delta. |
| Feishu regression from v2026.5.2 persists in v2026.5.3 | Explicitly verify Feishu channel auth during `labs` soak before promoting. Block if errors are observed. |
| 12-hour gateway crash from v2026.5.2 persists in v2026.5.3 | Monitor gateway uptime past the 12-hour mark during each soak. Block promotion if crash is observed. |
| `device.token.rotate` response format change breaks internal tooling | Audit internal scripts and tooling before the `ovk` rollout; fix before opening the `ovk` gitops PR. |
| `git:` plugin install surface activated accidentally | Confirm `git:` plugin install remains disabled in all tenant configurations before merging any gitops PR. |
| `ovk` rollout overlaps peak traffic | Schedule rollout in the pre-approved low-traffic maintenance window only. |
| Channel behaviour changes cause errors on `ovk` | Run connectivity checks across all active channels during `labs` and `admins` soaks; confirm no error-rate spike before proceeding. |
