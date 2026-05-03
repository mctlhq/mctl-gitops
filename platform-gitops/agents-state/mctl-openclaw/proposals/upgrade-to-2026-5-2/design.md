# Design: upgrade-to-2026-5-2

## Current state

All three tenants (`admins`, `labs`, `ovk`) run **openclaw 2026.3.14** (March 14, 2026). Deployments are managed via Docker image → mctl-gitops → ArgoCD, with per-tenant Helm releases in separate Kubernetes namespaces. Per-tenant S3 buckets hold auth tokens and channel sessions; the `restore-state` readiness probe must pass before a pod is declared ready, and an Argo CronWorkflow s3-sync canary validates ongoing write health (see `context/architecture.md` §"State guards" and `context/decisions/0002-s3-state-with-canary-and-probe.md`). Promotion order is mandated by ADR-0001: `labs → admins → ovk`, with observation periods between each step.

The current version carries ten unpatched CVEs and a CWE-532 credential-leak defect:

| CVE / defect | CVSS | Description | Fixed in |
|---|---|---|---|
| CVE-2026-42422 | 8.8 | Token-role bypass via `device.token.rotate` | 2026.4.29 |
| CVE-2026-42426 | 8.8 | Improper authorization in `node.pair.approve` | 2026.4.29 |
| CVE-2026-42428 | 7.1 | Missing plugin integrity verification | 2026.4.29 |
| CVE-2026-42429 | 7.1 | Gateway plugin HTTP auth privilege escalation | 2026.4.29 |
| CVE-2026-42423 | — | `strictInlineEval` approval-timeout bypass (eval execution) | 2026.4.29 |
| CVE-2026-41912 | — | SSRF policy bypass | 2026.4.29 |
| CVE-2026-41914 | — | QQ Bot media SSRF | 2026.4.29 |
| CVE-2026-41394 | — | Plugin-auth HTTP route auth bypass (unauthenticated operator-write access) | 2026.3.31 |
| CVE-2026-41395 | — | Plivo V3 webhook replay bypass via query-parameter reordering | 2026.3.28 |
| CVE-2026-41390 | — | Exec allowlist bypass via shell wrappers (`/usr/bin/script`, etc.) | 2026.3.28 |
| CWE-532 | — | `?password=`, `?token=`, `Authorization:` headers written to logs in plain text | 2026.5.2 |

All five previous upgrade proposals targeting 2026.4.x releases (`upgrade-to-2026-4-8`, `upgrade-to-2026-4-25`, `upgrade-to-2026-4-26`, `upgrade-to-2026-4-27`, `upgrade-to-2026-4-29`) are now superseded by v2026.5.2, which became the latest stable release on 2026-05-02. None of those proposals was executed; all tenants remain on 2026.3.14.

## Proposed solution

**Bump the openclaw image tag from `2026.3.14` to `2026.5.2`** in each tenant's Helm values file inside mctl-gitops, following the mandatory promotion sequence from ADR-0001:

```
labs  →  (24 h soak)  →  admins  →  (24 h soak)  →  ovk
```

### Rollout procedure per tenant (ADR-0002 compliant)

1. **Stop the s3-sync canary** CronWorkflow for the target tenant (set `.spec.suspend: true` on the Argo CronWorkflow object).
2. Open a gitops PR that updates `image.tag` to `2026.5.2` in the target tenant's `values.yaml`.
3. Merge the PR; ArgoCD syncs and schedules the new pod.
4. **Monitor the `restore-state` readiness probe.** ArgoCD will not mark the rollout successful until the probe passes. Do not proceed past this step manually.
5. **Restart the s3-sync canary** with the post-rollout delay specified in ADR-0002.
6. **24-hour soak** — observe s3-sync canary health, channel connectivity, pod RSS memory (critical for `labs`), log output for absence of credential values, and absence of restore-state probe failures.
7. If soak is clean, proceed to the next tenant in sequence; otherwise investigate and hold.

### Scheduling for `ovk`

The `ovk` rollout must be scheduled during the pre-approved low-traffic maintenance window. Restarts of `ovk` are painful (high SLA per `context/architecture.md`); the 24-hour soak on `admins` is the final automated gate.

### What v2026.5.2 changes for this deployment

**Security fixes (directly motivated):**
- Closes all ten CVEs listed above.
- CWE-532 log sanitization: `?password=` and `?token=` query parameters and `Authorization:` header values are redacted from all log output.
- Keychain credential handling for OpenAI Realtime sessions (passive improvement; no config change needed).
- SSRF guards for web search providers (extends CVE-2026-41912 / CVE-2026-41914 mitigations).

**Reliability improvements (directly motivated):**
- Gateway startup skips plugin-backed auth-profile overlays during secrets preflight, reducing startup latency and restore-state probe timeout risk.
- Plugin runtime-deps stale roots pruned after upgrade.

**Memory footprint improvements (positive for `labs`):**
- `@openclaw/acpx` externalized as an opt-in peer dependency — not installed by default. Reduces base package size.
- `@openclaw/diagnostics-otel` externalized as an opt-in peer dependency — not installed by default. Reduces base package size.
- Expected net RSS delta for `labs`: negative (footprint reduction). This is the first upgrade in this series that is assessed as low-to-no risk for the memory-constrained `labs` tenant, and may provide headroom for future feature proposals.

**Passive improvements (no config change required to benefit):**
- Grok 4.3 added as default xAI chat model.
- ClawHub artifact metadata persistence.
- Enhanced Slack threading and Discord component handling.

**New opt-in feature (NOT activated in this proposal):**
- `git:` plugin installs with version control support — explicitly disabled. Tracked in `git-plugin-install-allowlist`. The new attack surface introduced by this feature requires a dedicated allowlist proposal before any activation.

### No net new npm dependencies

The externalization of `@openclaw/acpx` and `@openclaw/diagnostics-otel` reduces the default dependency tree. No net-new npm packages are added to the base install. Plugin SDK interfaces are unchanged.

## Alternatives

**A. Cherry-pick individual CVE patches onto 2026.3.14.**
Rejected. The upstream project does not backport security patches to older stable branches. Maintaining a diverged fork branch carrying ten cherry-picks across multiple upstream commits (spanning 2026.3.28, 2026.3.31, 2026.4.29, and 2026.5.2) is operationally unsustainable and untestable against the upstream CI matrix.

**B. Upgrade to 2026.4.29 first, then to 2026.5.2 in a second cycle.**
Rejected. This would double the rollout cost (six tenant rollouts instead of three) for no security benefit: 2026.5.2 is stable and available today. The CWE-532 credential-leak defect and the startup-latency improvement are only available in 2026.5.2, not in 2026.4.29. Skipping directly to 2026.5.2 is the correct single target.

**C. Upgrade all three tenants simultaneously.**
Rejected by ADR-0001. Simultaneous upgrade eliminates `labs` as a canary. If v2026.5.2 carries an unexpected regression, it would immediately reach the production `ovk` tenant with no roll-back gate. The sequential promotion sequence is mandatory and non-negotiable.

## Platform impact

### Migrations

None required. The 2026.3.14 → 2026.5.2 path is a same-major upgrade series; no S3 schema changes, no Helm value renames, no plugin SDK breaking changes. Existing YAML skills in all three tenants are fully compatible.

### Backward compatibility

The 2026.4.x and 2026.5.x series do not break the plugin SDK or REST API surface used by `extensions/*` packages. One behavioral change introduced in 2026.4.26 must be verified before the `ovk` rollout: the `device.token.rotate` bearer-token response format was corrected. Any internal script or tooling that parses the rotated token value from the API response must be verified and updated before the `ovk` step. This audit is a prerequisite gate for the `ovk` rollout and is tracked explicitly in tasks.md.

Log output will change: credential values that were previously visible in logs will be replaced by redaction markers after the upgrade. Any log-based monitoring or alerting that pattern-matches on credential strings must be reviewed to ensure it does not break.

### Resource impact (especially for `labs`)

- The externalization of `@openclaw/acpx` and `@openclaw/diagnostics-otel` is expected to reduce the base package footprint. The net RSS delta for `labs` is expected to be zero or negative.
- The `labs` tenant is flagged as close to its memory limit per `context/architecture.md`. This upgrade is assessed as **low risk** for `labs` and may free headroom. The empirical RSS measurement during the `labs` soak (at 1 h, 6 h, and 24 h) will confirm this.
- If the RSS delta unexpectedly exceeds +50 MB above pre-upgrade baseline, promotion to `admins` is blocked until an operator provides explicit written sign-off (see requirements §AC-7).
- New opt-in packages (`@openclaw/acpx`, `@openclaw/diagnostics-otel`) are NOT installed in this proposal, so they contribute zero footprint.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Restore-state probe times out during S3 restore | Do not reduce probe timeout; the startup-latency improvement in 2026.5.2 reduces this risk. Log restore progress during `labs` soak. |
| False s3-sync canary alerts during rollout pause/restart | Follow ADR-0002 stop → rollout → delayed-restart; apply alert suppression window for the deliberate stop interval. |
| Memory regression in `labs` (unexpected, given footprint reduction) | Measure RSS delta at 1 h, 6 h, 24 h post-upgrade. Block promotion on > 50 MB delta. |
| Log-based monitoring breaks due to credential redaction | Audit monitoring rules before `labs` rollout; update any rule that matches credential string patterns in logs. |
| `git:` plugin install surface activated accidentally | Confirm `git:` plugin install remains disabled in all tenant configurations before merging any gitops PR. |
| `ovk` rollout overlaps peak traffic | Schedule rollout in the pre-approved low-traffic maintenance window only. |
| Channel behavior changes cause errors on `ovk` | Run connectivity checks across all active channels during `labs` soak and `admins` soak. Confirm no error-rate spike before proceeding. |
| `device.token.rotate` response format change breaks internal tooling | Complete task 3 (audit) before `admins` soak ends; complete task 14 (fix) before `ovk` gitops PR is opened. |
