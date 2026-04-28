# Design: upgrade-to-2026-4-25

## Current state
According to `context/architecture.md` and `context/current-version.md`, all three tenants (labs, admins, ovk) run openclaw 2026.3.14. Deployment follows Docker → mctl-gitops → ArgoCD. Rollout route: labs → admins → ovk (ADR 0001). State is protected by two mechanisms: the s3-sync canary (verifies S3 writes) and the restore-state readiness probe (verifies session restoration from S3 on pod start). The labs tenant is close to the memory limit — any RAM increase requires justification before rollout.

Five CVEs open in the current version:
- CVE-2026-41349 (CVSS 8.8) — fixed in >= 2026.3.28
- CVE-2026-41361 (High) — fixed in >= 2026.3.28
- CVE-2026-41359 (High) — fixed in >= 2026.3.28
- CVE-2026-41353 — fixed in >= 2026.3.22
- CVE-2026-41348 (CVSS 5.4) — fixed in >= 2026.3.31

## Proposed solution
Update the openclaw image tag from `2026.3.14` to `2026.4.25` in the gitops manifests of each tenant, in order: labs → admins → ovk.

**Step 0 — Pre-flight RAM check (labs)**
Before committing the change to the labs manifest, run a test pod with the 2026.4.25 image in an isolated namespace or via `kubectl run --restart=Never` with labs resource limits. Capture RSS/working set after the restore-state probe completes. If the increase exceeds 50MB relative to the current labs baseline — stop, open a ticket to raise the limit before continuing.

**Step 1 — labs rollout**
Update `image.tag` in the labs Helm values (`mctl-gitops/tenants/labs/values.yaml` or equivalent). ArgoCD applies the change. The s3-sync canary is paused for the rollout duration (annotation or manual suspend). After the readiness probe passes — resume the canary with a 60s delay. Observe for 1 hour: error metrics, WhatsApp/Telegram session healthchecks.

**Step 2 — admins rollout**
If no regressions appear in labs, repeat for admins. Blast radius is minimal (internal deploy), can be done without an extra window.

**Step 3 — ovk rollout**
Only after a successful run in labs and admins. Pick a maintenance window with minimal client activity. Specifically confirm the restore-state probe passes within timeout before traffic is switched. The s3-sync canary follows the same pattern: suspend → rollout → resume with delay.

**Why this approach:**
The labs → admins → ovk route is already pinned in ADR 0001 and proven in practice. A tag bump is the least invasive change: it does not touch channel configuration, skills, or extensions. The 2026.4.25 upstream image is a minor release without breaking changes in the public API (200+ internal changes). The pre-flight RAM check before labs mitigates the OOM risk specific to the labs tenant.

## Alternatives

**Alternative 1: An interim upgrade to 2026.3.31 (the minimum that closes all 5 CVEs)**
Version 2026.3.31 closes the last of the five CVEs (CVE-2026-41348). One could update to it instead of 2026.4.25. Dropped: there is no point performing two rollouts when 2026.4.25 is the current stable release and closes the same things with extra improvements. A double rollout doubles operational risk.

**Alternative 2: Targeted patch only for CVE-2026-41349 via configuration**
CVE-2026-41349 (agentic consent bypass) could in theory be mitigated via execution-approval policy configuration without bumping the version. Dropped: does not close the other four CVEs; a temporary workaround is worse than the upstream fix; creates upstream divergence that complicates future upgrades.

**Alternative 3: Upgrade only ovk (production), skip labs and admins**
Faster from a security exposure standpoint on production. Dropped: violates ADR 0001 (rollout route); labs is exactly the staging step before production; the labs OOM risk would not surface until production. Unacceptable for ovk with a high SLA.

## Platform impact

**Migration**
The change is only the image tag in gitops manifests. The 2026.4.25 changelog contains no breaking migration of S3 state schema (must be confirmed when reading the upstream CHANGELOG before rollout).

**Backward compatibility**
A minor release; upstream follows semver. The Plugin SDK and `extensions/*` should remain compatible. During the labs rollout verify that extensions build and load correctly.

**Resource impact**
- labs: HIGH RISK. The tenant is close to the RAM limit. Mandatory pre-flight RAM check with a test pod before committing to the labs manifest. If the increase exceeds 50MB — block and open a ticket to raise the limit.
- admins: LOW RISK. Internal deploy, limits are not critical.
- ovk: MEDIUM RISK. Restarts are painful for production SLA, but the restore-state probe guarantees session restoration from S3.

**Risks and mitigations**
- OOM in labs → pre-flight RAM check, block on delta > 50MB
- Loss of S3 sync → suspend the canary during rollout, resume with delay, alert if the canary does not recover
- Session loss in ovk → restore-state readiness probe, automatic rollback on failure
- Regression in extensions → smoke test in labs (WhatsApp + Telegram + Discord sessions) before promoting to admins/ovk
- An upstream breaking change in the CHANGELOG → CHANGELOG review before rollout
