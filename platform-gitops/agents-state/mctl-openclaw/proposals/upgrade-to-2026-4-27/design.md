# Design: upgrade-to-2026-4-27

## Current state

All three tenants (`admins`, `labs`, `ovk`) run **openclaw 2026.3.14** (March 14, 2026), deployed via Docker → mctl-gitops → ArgoCD. State (auth tokens, channel sessions) is stored in per-tenant S3 buckets and restored on pod startup via the `restore-state` readiness probe. A per-tenant s3-sync canary Argo CronWorkflow validates that pods continue writing fresh timestamps to S3.

See `context/architecture.md` §"State guards" and `context/decisions/0002-s3-state-with-canary-and-probe.md` for the full protection model.

**Exposed CVEs in 2026.3.14 (unpatched):**
- CVE-2026-41353 (CVSS 8.1) — fixed in 2026.3.22
- CVE-2026-41371 (CVSS 8.5), CVE-2026-41349 (CVSS 8.7), CVE-2026-41342, CVE-2026-41359 — all fixed in 2026.3.28
- CVE-2026-41352 (CVSS 8.8) — fixed in 2026.3.31

**Additional improvements in 2026.4.x not yet deployed:**
- 2026.4.25: OpenTelemetry expansion, plugin registry cold path, PWA/Web Push
- 2026.4.26: Bearer-token echo fix in `device.token.rotate`, Google Live Talk, Docker CA bundle
- 2026.4.27: Manifest-first plugin startup, Telegram/Slack reliability fixes, QQBot/Tencent Yuanbao channel expansion, DeepInfra provider

## Proposed solution

**Bump the openclaw image tag from `2026.3.14` to `2026.4.27`** in mctl-gitops Helm values, following the mandatory promotion sequence defined in ADR-0001:

```
labs  →  (24 h soak)  →  admins  →  (24 h soak)  →  ovk
```

**Rollout procedure for each tenant (per ADR-0002):**

1. Stop the s3-sync canary CronWorkflow for the target tenant.
2. Apply the image tag bump via a gitops PR merge → ArgoCD sync.
3. Monitor the `restore-state` readiness probe; ArgoCD will not mark the rollout successful until the probe passes.
4. Restart the s3-sync canary with the post-rollout delay (to avoid false alerts from the canary catching the deliberate stop).
5. Observe for 24 hours: check S3-sync canary, channel connectivity (especially Telegram, Slack in ovk), and memory usage (critical in labs).

**Memory check for `labs`:** Before promoting to `labs`, measure the pod's RSS/heap before and after the upgrade in a staging environment. If memory delta exceeds 50 MB, treat as risky and require explicit operator sign-off before continuing.

No schema migrations or API changes are required; 2026.3.14 → 2026.4.27 is a same-major upgrade within the 2026.x series. Plugin manifest-first startup (2026.4.27) is backward compatible with existing YAML skills.

## Alternatives

**A. Cherry-pick individual CVE patches onto 2026.3.14** — Rejected. Six CVEs across five patch versions would require maintaining a long-lived fork branch. The upstream project does not backport patches; the only supported remediation path is upgrading to the fixed release.

**B. Upgrade only to 2026.3.31 (last patched version before 2026.4.x)** — Rejected. All CVEs are fixed by 2026.3.31, but skipping 2026.4.x means deferring the bearer-token echo fix (2026.4.26) and the Telegram/Slack reliability improvements (2026.4.27) that directly benefit `ovk`. The incremental risk of going to 2026.4.27 is lower than a second upgrade cycle.

**C. Upgrade tenants simultaneously** — Rejected by ADR-0001. Simultaneous upgrade removes `labs` as a canary for `ovk`. The sequential promotion sequence is mandatory.

## Platform impact

### Migrations
None required. openclaw's plugin manifest-first startup (2026.4.27) reads existing manifests and falls back to legacy detection; no YAML skill edits needed.

### Backward compatibility
The 2026.4.x series does not introduce breaking changes to the plugin SDK or REST API surface used by our extensions. The bearer-token echo fix (2026.4.26) changes response payload format for `device.token.rotate` — any internal tooling that parses the rotated token from the response must be updated.

### Resource impact (especially for `labs`)
- The 2026.4.25 release moved the plugin registry to a cold persisted path, which may marginally reduce steady-state heap usage.
- QQBot and Tencent Yuanbao channels (2026.4.27) are opt-in via config; they will NOT be enabled in `labs` or `ovk` without an explicit config change, so no memory increase from channel expansion.
- OpenTelemetry coverage expansion may add a small memory overhead (~5–15 MB); this must be measured during the `labs` soak before promoting to `admins`/`ovk`. Flag as risky for `labs` if delta > 50 MB.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `restore-state` probe timeout during S3 restore on slow channel (WhatsApp Web, iMessage) | Do not shorten probe timeout; monitor restore logs and extend timeout if needed before ovk rollout |
| False s3-sync canary alerts during rollout stop/restart | Follow ADR-0002 stop→rollout→delayed-restart sequence; update canary alert suppression window |
| Memory regression in `labs` | Measure RSS delta before promoting; abort if > 50 MB |
| Bearer-token echo fix breaks internal tooling | Audit and update any script that reads `device.token.rotate` responses before ovk rollout |
| Telegram/Slack reliability fixes introduce regressions | Covered by labs soak: run 24 h of channel connectivity checks before promoting |
