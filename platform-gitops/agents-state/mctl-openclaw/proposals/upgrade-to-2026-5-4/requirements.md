# Upgrade openclaw from 2026.3.14 to 2026.5.4

## Context

All three mctl-openclaw tenants (`admins`, `labs`, `ovk`) are currently running
openclaw 2026.3.14. Three confirmed vulnerabilities in our version range are
actively exploitable: CVE-2026-43534 (CVSS 9.1 Critical — untrusted external
hook metadata is escalated to a higher-trust agent context), CVE-2026-42435
(shell injection via argv-level environment-variable injection), and
CVE-2026-42436 (authentication bypass on browser snapshot, screenshot, and tab
routes). Additional CVEs patched between 2026.3.14 and 2026.5.4
(CVE-2026-41394, CVE-2026-42422, CVE-2026-41390, CVE-2026-41395,
CVE-2026-33579, CVE-2026-41358) are subsumed by this upgrade as a precaution.

Version 2026.5.4, released 2026-05-05, is the current stable release.
Upgrading closes all CVEs above in a single operation and additionally delivers
gateway startup and plugin-loading performance improvements. The `labs` tenant
is near its memory limit; the startup-time improvements in 2026.5.4 may reduce
peak RAM, but this must be measured, not assumed, before the upgrade is
promoted to `admins` and `ovk`. Rollout order and state-guard procedures are
governed by ADR-0001 and ADR-0002.

## User stories

- AS a platform operator I WANT all three openclaw tenants upgraded to
  2026.5.4 SO THAT the three confirmed CVEs (CVE-2026-43534, CVE-2026-42435,
  CVE-2026-42436) are closed and our exposure to hook-name injection, shell
  injection, and auth bypass is eliminated.

- AS a platform operator responsible for the `labs` tenant I WANT the memory
  footprint of 2026.5.4 validated under real load in `labs` before the upgrade
  is promoted to `admins` and `ovk` SO THAT we do not breach the `labs` memory
  limit or carry an untested RAM regression into production.

- AS an SRE on-call for the `ovk` production tenant I WANT the restore-state
  readiness probe to gate every rollout SO THAT channel auth tokens are
  confirmed restored from S3 before traffic is accepted and we do not lose
  production customer sessions.

## Acceptance criteria (EARS)

### Rollout order

- WHEN the upgrade of any tenant is initiated THE SYSTEM SHALL apply the
  change to `labs` first, then `admins`, then `ovk`, and SHALL NOT allow
  `admins` or `ovk` to proceed until the preceding tenant's ArgoCD rollout is
  marked successful.

- IF the `labs` rollout fails or the restore-state probe does not pass within
  the configured timeout THEN THE SYSTEM SHALL halt promotion and SHALL NOT
  apply the new image tag to `admins` or `ovk`.

### Canary lifecycle

- WHEN a tenant rollout begins THE SYSTEM SHALL stop the s3-sync canary
  workflow for that tenant before the new pod is scheduled.

- WHEN a tenant rollout is marked successful by ArgoCD THE SYSTEM SHALL
  restart the s3-sync canary workflow for that tenant after a minimum delay
  of one canary cycle, so that no false-alert cycles are emitted during pod
  startup.

- WHILE the s3-sync canary for a tenant is stopped THE SYSTEM SHALL surface
  a visible status indicating the canary is suspended so that on-call
  engineers are not misled by absent alerts.

### Restore-state probe

- WHEN the upgraded pod starts THE SYSTEM SHALL pass the restore-state
  readiness probe (confirming auth/sessions restored from S3) before ArgoCD
  marks the rollout successful and before the canary is restarted.

### Memory validation (labs)

- WHEN the `labs` rollout is marked successful THE SYSTEM SHALL record peak
  memory usage of the upgraded pod under representative load over a minimum
  observation window of 30 minutes.

- IF the observed peak memory in `labs` equals or exceeds the tenant memory
  limit THEN THE SYSTEM SHALL block promotion to `admins` and `ovk` and SHALL
  raise a blocking issue for operator review.

### CVE closure

- WHEN the upgrade to 2026.5.4 is applied to a tenant THE SYSTEM SHALL run
  on a version that includes the upstream fixes for CVE-2026-43534
  (fixed 2026.4.10), CVE-2026-42435 (fixed 2026.4.12), and CVE-2026-42436
  (fixed 2026.4.14).

### Rollback

- IF a rollback is triggered for any tenant THEN THE SYSTEM SHALL restore the
  previous image tag (2026.3.14) via the gitops repository, stop the canary,
  wait for the restore-state probe to pass on the old image, then restart the
  canary.

- WHILE a rollback is in progress THE SYSTEM SHALL NOT apply any further
  version changes to the affected tenant until an operator explicitly
  re-approves the upgrade.

## Out of scope

- Upgrading Node.js or TypeScript versions — no confirmed Node.js version is
  recorded in context; a separate proposal is required once the deployed
  version is identified.
- Adopting pre-release versions of openclaw (2026.5.4-beta.*) — only the
  stable 2026.5.4 tag is in scope.
- Upgrading Baileys, discord.js, or Slack SDK dependencies — covered by
  separate proposals (`baileys-supply-chain-audit`, `discord-js-dm-fix`).
- Merging tenants or changing the three-tenant deployment topology (explicitly
  rejected in ADR-0001).
- Replacing S3 state storage or modifying the canary/probe thresholds beyond
  what is needed for this rollout.
- Changes to shared YAML skills or remote-skill registrations.
