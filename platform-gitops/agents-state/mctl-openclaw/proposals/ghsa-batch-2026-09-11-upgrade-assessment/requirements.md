# Assess and patch the September 11 2026 GHSA batch (WhatsApp/Discord/Slack/exec-approval advisories)

## Context
On 2026-09-11, upstream `openclaw/openclaw` published 10 official GHSA security advisories. Several are directly fork-relevant: two High-severity issues (GHSA-3mq7-q27j-mq7q — exec approvals can outlive their reviewed working directory; GHSA-9m4p-cqp4-jppq — the WhatsApp login tool could reach non-owner turns) and two Moderate advisories touching channels we run in all three tenants (GHSA-xvwp-wmh2-fq48 — Discord asset uploads media-policy bypass; GHSA-v7hh-7676-rg67 — Slack file download authorization gap). All three tenants (`admins`, `labs`, `ovk`) are currently pinned to `2026.7.11-beta.2` per `mctl_get_service_status`, two monthly release trains behind current upstream (`2026.9.4`), so we cannot assume these advisories are already patched.

Compounding the uncertainty, `context/current-version.md` still records `2026.3.14` (stale since 2026-04-26) while upstream issue #151054 notes that the June-line extended-stable release (`2026.6.35`) does not document which of the 10 advisories it backports. We therefore have neither an accurate record of what we run nor a confirmed patch target. This proposal is about closing that gap: confirm exposure, pick a patched target version, and roll it out safely through the mandated tenant order, while also correcting our own version-tracking artifact.

## User stories
- AS a platform operator I WANT confirmation of which of the 10 September 11 GHSA advisories affect our deployed `2026.7.11-beta.2` baseline SO THAT I know our actual exposure before deciding on a patch.
- AS a platform operator I WANT a patched openclaw version rolled out through `labs` → `admins` → `ovk` SO THAT the WhatsApp, Discord, Slack, and exec-approval fixes are applied without risking the `ovk` SLA.
- AS the service owner I WANT `context/current-version.md` to reflect the real deployed version after the rollout SO THAT future assessments do not repeat this discrepancy.

## Acceptance criteria (EARS)
- WHEN the assessment task begins THE SYSTEM SHALL determine, for each of the 10 September 11 GHSA advisories, whether `2026.7.11-beta.2` is in the affected version range, using the primary GHSA advisory pages (not third-party aggregators) as the source of truth.
- WHEN a patched target version is selected THE SYSTEM SHALL confirm via upstream release notes or advisory "patched versions" fields that the target actually contains fixes for all fork-relevant advisories (WhatsApp, Discord, Slack, exec-approval) before rollout begins.
- WHEN the upgrade is rolled out THE SYSTEM SHALL follow the `labs` → `admins` → `ovk` order mandated by ADR-0001, with an observation window in `labs` before proceeding.
- WHILE a rollout is in progress in any tenant THE SYSTEM SHALL keep the s3-sync canary and restore-state probe behavior exactly as defined in ADR-0002 (canary paused for rollout duration and restarted with delay; probe timeout unchanged).
- IF the extended-stable (LTS) line's backport coverage of the 10 advisories cannot be confirmed (per issue #151054) THEN THE SYSTEM SHALL prefer a `2026.9.x` target with an explicit changelog/advisory cross-reference over the LTS line, or document the accepted residual risk if LTS is chosen instead.
- WHEN the rollout to all three tenants completes successfully THE SYSTEM SHALL update `context/current-version.md` with the new version, per-tenant confirmation, and the date of the update, and SHALL record the decision in a new ADR if any tenant ends up on a different version than the others.
- IF any of the two remaining unconfirmed CVEs (CVE-2026-41301, CVE-2026-32922) later gets corroborated on the official advisories page THEN THE SYSTEM SHALL re-run this assessment against the newly confirmed advisory.

## Out of scope
- Patching CVE-2026-48063 (Baileys) — already tracked by the existing `baileys-cve-48063-version-check` proposal.
- The `@slack/socket-mode` 3.0.1 leaked-socket fix — tracked by `slack-socket-mode-update`.
- Investigating the `ovk` pod-health / silent-canary anomaly — tracked separately (`ovk-s3-sync-canary-and-pod-health-investigation`).
- Restarting or rolling back `ovk` outside of the standard patch rollout described here.
- Adopting `nix-openclaw` packaging changes — out of our Docker → mctl-gitops → ArgoCD build path.
