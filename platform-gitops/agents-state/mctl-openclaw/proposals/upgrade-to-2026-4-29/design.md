# Design: upgrade-to-2026-4-29

## Current state

All three tenants (`admins`, `labs`, `ovk`) run **openclaw 2026.3.14** (March 14, 2026). Deployments are managed via Docker → mctl-gitops → ArgoCD, with per-tenant Helm releases in separate Kubernetes namespaces. Per-tenant S3 buckets hold auth tokens and channel sessions; the `restore-state` readiness probe must pass before a pod is declared ready, and an Argo CronWorkflow s3-sync canary validates ongoing write health (see `context/architecture.md` §"State guards" and `context/decisions/0002-s3-state-with-canary-and-probe.md`).

The current version carries seven unpatched CVEs:

| CVE | CVSS | Description |
|-----|------|-------------|
| CVE-2026-42422 | 8.8 | Token-role bypass via `device.token.rotate` |
| CVE-2026-42426 | 8.8 | Improper authorization in `node.pair.approve` |
| CVE-2026-42428 | 7.1 | Missing plugin integrity verification |
| CVE-2026-42429 | 7.1 | Gateway plugin HTTP auth privilege escalation |
| CVE-2026-42423 | — | `strictInlineEval` approval-timeout bypass (eval execution) |
| CVE-2026-41912 | — | SSRF policy bypass |
| CVE-2026-41914 | — | QQ Bot media SSRF |

Four previous upgrade proposals (`upgrade-to-2026-4-8`, `upgrade-to-2026-4-25`, `upgrade-to-2026-4-26`, `upgrade-to-2026-4-27`) targeted earlier 2026.4.x releases and are now superseded. None has been executed; all tenants remain on 2026.3.14.

## Proposed solution

**Bump the openclaw image tag from `2026.3.14` to `2026.4.29`** in each tenant's Helm values file inside mctl-gitops, following the mandatory promotion sequence from ADR-0001:

```
labs  →  (24 h soak)  →  admins  →  (24 h soak)  →  ovk
```

### Rollout procedure per tenant (ADR-0002 compliant)

1. **Stop the s3-sync canary** CronWorkflow for the target tenant (suspend the Argo CronWorkflow object).
2. Open a gitops PR that updates `image.tag` to `2026.4.29` in the target tenant's `values.yaml`.
3. Merge the PR; ArgoCD syncs and schedules the new pod.
4. **Monitor the `restore-state` readiness probe**. ArgoCD will not mark the rollout successful until the probe passes. Do not proceed past this step manually.
5. **Restart the s3-sync canary** with the post-rollout delay specified in ADR-0002.
6. **24-hour soak** — observe s3-sync canary health, channel connectivity, pod RSS memory (critical in `labs`), and absence of restore-state probe failures.
7. If soak is clean, proceed to the next tenant in sequence; otherwise investigate and hold.

### Scheduling for `ovk`

The `ovk` rollout must be scheduled during the pre-approved low-traffic maintenance window. Restarts of `ovk` are painful (high SLA); the 24-hour soak on `admins` provides the final gate.

### What v2026.4.29 changes for us

Security fixes (directly motivated):
- Closes all 7 CVEs listed above.
- HTML tag sanitization (prevents script-sequence injection via channel message content).
- Timing-safe credential comparison (mitigates timing-based credential brute-force).

Reliability improvements (directly motivated):
- Gateway slow-startup and stale-session recovery fixes — reduces restore-state probe timeouts that have been observed in prior rollout attempts.

Passive improvements (no config change required to benefit):
- Channel reliability: Discord startup, Slack Block Kit rendering, Telegram message resilience, WhatsApp delivery, Teams/Matrix edge cases.
- Active-run steering enabled by default (behavioral, not a breaking change).

New opt-in features (not activated by this proposal):
- People-aware wiki memory, NVIDIA/Bedrock Opus 4.7 provider, new channel modes.

### No new dependencies

The 2026.3.14 → 2026.4.29 changelog introduces no new npm packages. Plugin SDK interfaces are unchanged. The memory footprint of the `labs` pod is expected to remain within its current budget; this must be confirmed empirically during the `labs` soak (see Platform impact below).

## Alternatives

**A. Cherry-pick individual CVE patches onto 2026.3.14.** Rejected. The upstream project does not backport security patches. Maintaining a diverged fork branch carrying seven cherry-picks across multiple upstream commits is operationally unsustainable and untestable against the upstream test matrix.

**B. Upgrade to the closest previous stable (2026.4.27) instead of waiting for 2026.4.29.** Rejected. v2026.4.27 does not contain the seven 2026.4.28+ CVE fixes or the gateway slow-startup/stale-session recovery improvements. Taking a second upgrade cycle from 2026.4.27 to 2026.4.29 would double the rollout cost with no benefit. v2026.4.29 became stable on 2026-04-30 and is the correct single target.

**C. Upgrade all three tenants simultaneously.** Rejected by ADR-0001. Simultaneous upgrade eliminates `labs` as a canary. If v2026.4.29 carries an unexpected regression, it would immediately hit the production `ovk` tenant with no roll-back gate. The sequential promotion sequence is mandatory and non-negotiable.

## Platform impact

### Migrations

None required. The 2026.3.14 → 2026.4.29 series is a same-major upgrade; no S3 schema changes, no Helm value renames, no plugin SDK breaking changes. Existing YAML skills in all three tenants are fully compatible.

### Backward compatibility

The 2026.4.x series does not break the plugin SDK or REST API surface used by our `extensions/*` packages. One behavioral change to note: the `device.token.rotate` bearer-token response format was corrected in 2026.4.26. Any internal script or tooling that parses the rotated token value from the API response must be verified before the `ovk` rollout. This audit is tracked as a separate backlog item and is out of scope for this proposal, but it is a prerequisite gate for the `ovk` step.

### Resource impact (especially for `labs`)

- The upstream changelog documents no new npm dependencies and no significant allocator changes. Expected RSS delta: negligible (< 10 MB).
- During the `labs` 24-hour soak, pod RSS must be measured before and after the upgrade. If the delta exceeds **50 MB**, the promotion to `admins` is blocked until an operator provides explicit written sign-off (see requirements §AC-7).
- New opt-in features (people-aware wiki memory, NVIDIA/Bedrock Opus 4.7 provider) are NOT enabled by this proposal, so there is no footprint contribution from them.
- The `labs` tenant is flagged risky for any memory-increasing change per `context/architecture.md`; this proposal is assessed as low risk absent evidence from the soak.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Restore-state probe times out during S3 restore (WhatsApp Web, iMessage are slow) | Do not reduce probe timeout; extend it if `labs` soak reveals slow restore. Log restore progress during soak. |
| False s3-sync canary alerts during rollout pause/restart | Follow ADR-0002 stop → rollout → delayed-restart; apply alert suppression window for the deliberate stop interval. |
| Memory regression in `labs` | Measure RSS delta at 1 h, 6 h, 24 h post-upgrade. Block on > 50 MB delta. |
| Gateway slow-startup fix introduces a timing regression on `ovk` startup | Covered by `labs` and `admins` soak periods; restore-state probe is the automated gate. |
| Channel behavior changes (Discord, Slack, Telegram, WhatsApp) cause unexpected errors on `ovk` | Run connectivity checks across all active channels during `labs` soak and `admins` soak. Confirm no error-rate spike before proceeding. |
| `ovk` rollout overlaps peak traffic | Schedule rollout in the pre-approved low-traffic maintenance window only. |
