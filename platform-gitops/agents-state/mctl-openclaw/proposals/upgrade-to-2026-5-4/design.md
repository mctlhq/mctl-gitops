# Design: upgrade-to-2026-5-4

## Current state

All three tenants (`admins`, `labs`, `ovk`) are pinned to **openclaw 2026.3.14**
(see `context/current-version.md`, last updated 2026-04-26). The image tag is
managed via the mctl-gitops repository and deployed by ArgoCD to separate
Kubernetes namespaces.

Three confirmed vulnerabilities are present in 2026.3.14:

| CVE | CVSS | Description | Fixed in |
|-----|------|-------------|----------|
| CVE-2026-43534 | 9.1 Critical | External hook metadata processed as trusted system events; hook-name injection into higher-trust agent context | 2026.4.10 |
| CVE-2026-42435 | unknown | Shell-wrapper detection bypass; env-var injection at argv level | 2026.4.12 |
| CVE-2026-42436 | unknown | Auth bypass on browser snapshot, screenshot, and tab routes | 2026.4.14 |

Additional CVEs patched between 2026.3.14 and 2026.5.4 (CVE-2026-41394,
CVE-2026-42422, CVE-2026-41390, CVE-2026-41395, CVE-2026-33579, CVE-2026-41358)
are subsumed by this upgrade as a precaution; individual exposure assessments
were not confirmed.

The rollout pipeline follows ADR-0001 (labs → admins → ovk, never skip) and
ADR-0002 (stop s3-sync canary before rollout, restart after; restore-state
readiness probe gates ArgoCD success). No state migrations are known to be
required for this version range.

## Proposed solution

### Version target

Pin all three tenants to **openclaw 2026.5.4** (stable, released 2026-05-05).
This is the earliest stable release that contains all three required CVE fixes
and additionally includes gateway startup and plugin-loading performance
improvements that may reduce peak RAM in `labs`.

### GitOps flow

1. Open a PR in mctl-gitops that updates the `image.tag` value for the `labs`
   Helm release from `2026.3.14` to `2026.5.4`. No other values are changed
   in this PR.
2. Review the upstream changelog between 2026.3.14 and 2026.5.4 for any
   breaking changes in configuration keys, environment variables, or plugin
   APIs. If breaking changes are found, they must be handled in the same PR
   before merge.
3. Merge the PR. ArgoCD detects the change and schedules the rollout for `labs`.
4. After `labs` is confirmed healthy (restore-state probe passed, canary
   restarted, memory within limit), open a second PR for `admins`.
5. After `admins` is confirmed healthy, open a third PR for `ovk`.
6. After all three tenants are healthy, update `context/current-version.md`
   and add an ADR recording the upgrade decision.

Each PR is a separate gitops commit so that the rollout is independently
auditable and individually reversible via a single git revert.

### Canary and probe protocol (per ADR-0002)

For each tenant, in order:

1. **Stop canary** — suspend the Argo CronWorkflow `s3-sync-canary-<tenant>`.
   Confirm suspension before proceeding.
2. **Apply image tag** — merge the gitops PR; ArgoCD rolls out the new pod.
3. **Wait for probe** — ArgoCD waits for the restore-state readiness probe to
   pass. Do not treat the rollout as successful until ArgoCD reports `Healthy`.
4. **Observe** — for `labs` only, record peak memory usage over a minimum
   30-minute window after the pod is ready.
5. **Restart canary** — resume `s3-sync-canary-<tenant>` after at least one
   full canary cycle has elapsed since pod readiness to avoid false alerts.

If the probe does not pass within the configured timeout at any tenant,
ArgoCD marks the rollout `Degraded`. The operator must investigate before
re-attempting the upgrade or initiating rollback.

### Memory validation gate for labs

After the `labs` rollout is healthy, an operator must confirm that the
observed peak RSS of the openclaw pod is below the tenant memory limit. This
is a manual gate (check via `kubectl top pod` or equivalent mctl metrics)
before the `admins` PR is merged. The startup-performance improvements in
2026.5.4 are expected to lower peak RAM, but this must be measured, not
assumed.

## Alternatives

### Option A: Backport individual CVE patches to 2026.3.14

Cherry-pick only the three CVE fixes from upstream into a fork-specific
2026.3.14-mctl build. This would minimise the change surface.

**Rejected** because: (1) the three fixes span three different minor versions
(4.10, 4.12, 4.14), making clean cherry-picks non-trivial; (2) maintaining a
fork-specific patch set adds permanent operational overhead; (3) 2026.5.4 is
stable and already in production at upstream, so the risk of upgrading is low;
(4) the additional CVEs subsumed by the upgrade would remain unaddressed.

### Option B: Stay on 2026.3.14 and deploy a WAF rule to mitigate CVEs

Place a Web Application Firewall rule in front of the hook-metadata ingestion
path (CVE-2026-43534) and the browser routes (CVE-2026-42436) to filter
malicious payloads.

**Rejected** because: (1) CVE-2026-42435 is a shell injection at the argv
level inside the process — a WAF cannot intercept in-process calls; (2) WAF
rules for logic-level vulnerabilities are fragile and easy to bypass; (3) this
approach leaves all three CVEs incompletely mitigated and does not satisfy the
acceptance criteria for CVE closure.

### Option C: Hotfix only the ovk tenant to 2026.5.4, skip labs and admins

Apply the upgrade directly to `ovk` because it is the highest-SLA, most
exposed tenant.

**Rejected** because: ADR-0001 explicitly prohibits skipping the
labs → admins → ovk order. `labs` exists specifically as a canary for `ovk`.
Bypassing it would remove the memory-validation gate and increase blast radius
for the production customer.

## Platform impact

### Migrations

No database schema changes or S3 bucket restructuring are expected between
2026.3.14 and 2026.5.4. The upstream changelog must be verified against this
assumption during the changelog-review task (Task 1). If any config-key
renames or environment-variable changes are found, they must be applied in the
gitops PR before the image tag is updated.

### Backward compatibility

The plugin SDK interface may have changed across seven minor versions. All
extensions in `extensions/*` that import `openclaw/plugin-sdk/*` must be
verified against the 2026.5.4 SDK changelog before the `labs` rollout
proceeds. If a breaking change is found, the extension must be updated in the
same gitops PR.

### Resource impact

**RISKY for `labs`** — The `labs` tenant is close to its memory limit
(see `context/architecture.md`). Although the startup optimisations in 2026.5.4
are expected to reduce peak RAM, this is not guaranteed. Memory usage must be
measured for a minimum of 30 minutes after the `labs` pod is ready before
promoting to `admins` and `ovk`. If peak RSS meets or exceeds the tenant limit,
promotion is blocked until the memory issue is resolved.

For `admins` and `ovk` there is no known memory constraint. However, if
`labs` shows an increase, the rollout to `admins` and `ovk` must also be
treated as risky until the cause is identified.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `labs` memory usage increases rather than decreases | Low | 30-minute observation gate; block promotion if limit is approached |
| Plugin SDK breaking change causes extension failures | Low–Medium | Pre-rollout changelog review and extension compatibility check |
| Restore-state probe timeout under heavier startup workload (new plugin loading) | Low | Monitor probe duration in `labs`; extend timeout in Helm values if needed before `admins`/`ovk` rollouts |
| False-positive canary alerts during pod startup | Known/Managed | Canary stopped before rollout, restarted only after one full cycle post-readiness (ADR-0002) |
| Silent loss of S3 sync if canary restart is skipped | Known/Managed | Canary restart is a mandatory step in the rollout runbook; ArgoCD sync hook can enforce ordering |
| Upstream patch introduces regression in a channel adapter | Low | `labs` observation window catches regressions before `ovk` is affected |
