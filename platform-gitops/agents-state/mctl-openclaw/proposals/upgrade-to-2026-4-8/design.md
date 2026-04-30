# Design: upgrade-to-2026-4-8

## Current state
All three tenants (`labs`, `admins`, `ovk`) run openclaw 2026.3.14, as recorded in `context/current-version.md`. Deployments are managed via Docker images built from the openclaw upstream fork, published to mctl-gitops, and applied by ArgoCD per the architecture in `context/architecture.md`. State (auth tokens, channel sessions) is persisted to per-tenant S3 buckets and restored on pod startup, protected by the s3-sync canary and restore-state readiness probe (ADR-0002). Rollout order is mandated by ADR-0001: `labs` → `admins` → `ovk`.

Four CVEs disclosed on 2026-04-28 expose privilege-escalation and integrity-bypass vulnerabilities in core openclaw components (token rotation, node pairing, plugin archive download, gateway HTTP auth). All are fixed in 2026.4.8.

## Proposed solution
Upgrade the openclaw dependency in the fork to `2026.4.8` by updating the version pin in `package.json` (and `package-lock.json`), rebuilding the Docker image, and rolling out to each tenant in order.

**Step 1 — Evaluate memory footprint.** Before deploying to `labs`, build the 2026.4.8 image locally and measure RSS under a representative workload. Compare against the 2026.3.14 baseline. If the increase exceeds 50 MB, the upgrade is flagged as risky for `labs` and a mitigation (e.g., resource limit adjustment with platform approval) must be agreed before proceeding.

**Step 2 — Update fork and cut release image.** Bump the `openclaw` version in `package.json` from `2026.3.14` to `2026.4.8`, run `npm install` to regenerate `package-lock.json`, build and push the Docker image tagged `2026.4.8`.

**Step 3 — Roll out to `labs`.** Update the `labs` helm release value `image.tag` in mctl-gitops. Before applying: pause the s3-sync canary (Argo CronWorkflow suspended). ArgoCD applies the change; the pod must pass the restore-state readiness probe. After pod is ready: resume the canary with the standard delay. Observe for at least one day (canary passing, no alert, channels healthy).

**Step 4 — Roll out to `admins`.** Same canary pause/resume procedure. Observe for one day.

**Step 5 — Roll out to `ovk`.** Same canary pause/resume procedure. Confirm channels healthy post-rollout.

**Step 6 — Update version record.** Update `context/current-version.md` to 2026.4.8 for all tenants and create an ADR in `context/decisions/` documenting the change.

This approach is chosen because it is the minimum-change path to remediation: it moves to the single stable release that fixes all four CVEs without introducing unrelated upstream changes (the beta track is excluded). It reuses the existing rollout and state-guard infrastructure without modification.

## Alternatives

**A. Apply individual CVE patches to 2026.3.14 as a fork patch.** This avoids the risk of any 2026.4.x behaviour changes but requires manually porting four separate fixes, maintaining the patches in the fork indefinitely, and re-verifying they are correct. The upstream fix in 2026.4.8 is already reviewed and tested; re-implementing is higher effort with lower confidence. Dropped.

**B. Upgrade directly to the latest upstream beta 2026.4.29-beta.4.** This would include all CVE fixes plus several weeks of additional changes, none of which have been validated on our fork or tenants. The additional untested surface area is unjustified for a security-driven upgrade. Dropped.

**C. Roll out all three tenants simultaneously.** Eliminates the canary benefit of the ADR-0001 order. If the upgrade introduces a regression (e.g., a restore-state failure), it would hit all three tenants including `ovk` at the same time. Explicitly prohibited by ADR-0001. Dropped.

## Platform impact

**Migrations.** No schema or S3 structure changes are expected between 2026.3.14 and 2026.4.8 based on upstream release notes. If upstream changelog identifies any database migration, it must be handled before the pod starts (init container or startup hook) — verify against upstream changelog during task 2.

**Backward compatibility.** This is a patch-level stable upgrade. Plugin SDK API changes are not expected. Extensions in `extensions/*` must be smoke-tested after the `labs` rollout.

**Resource impact — `labs`.** The `labs` tenant is close to its memory limit. The memory footprint of 2026.4.8 must be measured before deployment (see Step 1 above). If the footprint increases by more than 50 MB, this upgrade is flagged as risky for `labs` and requires explicit platform approval before proceeding. This risk is flagged here in accordance with CLAUDE.md.

**Risks and mitigations.**
- Risk: Restore-state probe fails after upgrade due to a new startup behaviour. Mitigation: the probe timeout is unchanged; if the pod does not become ready within the existing timeout, ArgoCD rolls back automatically.
- Risk: A channel loses connectivity post-upgrade (especially WhatsApp Baileys, which is sensitive to core changes). Mitigation: observe all channels on `labs` for at least one day before promoting.
- Risk: Memory regression on `labs`. Mitigation: mandatory pre-deployment baseline measurement in task 1; block on > 50 MB increase.
- Risk: Canary false-positive during rollout window. Mitigation: canary is suspended before rollout and restarted after pod is ready, per ADR-0002 procedure.
