# Assess and plan upgrade path from 2026.7.11-beta.2 to a patched mainline/LTS release

## Context
All three tenants (`admins`, `labs`, `ovk`) are still deployed on image tag
`2026.7.11-beta.2`, unchanged across at least three consecutive weekly research
passes. Upstream has since moved three release trains ahead: `2026.7.35` (new
extended-stable/LTS, release notes explicitly cite "critical security
updates"), `2026.9.5`, and `2026.9.6` (current mainline "latest"). A
third-party signal (unverified against the primary GHSA page) states that
`2026.8.1+` resolves the two Sep-11 High-severity GHSA advisories our
deployed baseline predates. Several adjacent signals (a CCB Belgium "critical
1-click RCE" advisory, an Infosecurity Magazine "six new vulnerabilities"
headline, and a betterclaw.io aggregate CVE count that jumped from ">138" to
"543" week-over-week) are not yet cross-referenced to a specific GHSA/CVE ID
and must be resolved, not acted on blindly.

A related, narrower proposal (`ghsa-batch-2026-09-11-upgrade-assessment`) and
older upgrade-path proposals (`openclaw-cve-upgrade`,
`openclaw-upgrade-cve-batch`, `openclaw-upgrade-2026-5-12`) already exist in
`proposals/`. This proposal reflects today's fresher baseline (three trains
behind, not two, plus the `labs` quota resize) and is intended to supersede
and consolidate that prior work, not run a fourth parallel upgrade track.

## User stories
- AS the service owner I WANT a concrete, validated upgrade target and rollout
  plan SO THAT all three tenants close the multi-release-train security gap
  safely.
- AS the `labs` canary operator I WANT explicit memory headroom budgeting
  before and during the canary rollout SO THAT `labs` does not breach its
  memory quota.
- AS a security reviewer I WANT the unconfirmed adjacent advisories (CCB
  Belgium, Infosecurity, betterclaw.io aggregate) resolved to specific
  GHSA/CVE IDs SO THAT we know if they add exposure beyond what is already
  tracked.

## Acceptance criteria (EARS)
- WHEN the assessment begins THE SYSTEM SHALL enumerate, for the deployed
  baseline `2026.7.11-beta.2`, which currently-published GHSA advisories are
  within its affected version range, using only the primary
  `openclaw/openclaw` security advisories page as the source of truth.
- WHEN a candidate upgrade target is selected THE SYSTEM SHALL confirm, via
  upstream release notes/changelog (not third-party summaries), that the
  target resolves the confirmed advisories, and SHALL document the
  mainline-vs-LTS choice with rationale.
- WHEN the CCB Belgium advisory, the Infosecurity "six new vulnerabilities"
  article, and the betterclaw.io aggregate are reviewed THE SYSTEM SHALL
  cross-reference each to a specific GHSA/CVE ID and affected-version range,
  or explicitly record it as unconfirmed/not actionable.
- WHEN the upgrade is rolled out THE SYSTEM SHALL follow the `labs` →
  `admins` → `ovk` order mandated by ADR-0001, with an explicit observation
  window in `labs` before promoting further.
- WHILE a rollout is in progress in any tenant THE SYSTEM SHALL keep the
  s3-sync canary paused for the rollout duration and restarted with delay
  afterward, and SHALL NOT shorten the restore-state probe timeout, per
  ADR-0002.
- WHILE the `labs` canary step is running THE SYSTEM SHALL monitor `labs`
  `limits.memory` usage against its (recently resized) 14Gi quota and SHALL
  halt promotion IF usage attributable to the upgrade exceeds an agreed
  safety threshold.
- IF the target version increases `labs` steady-state memory footprint over
  its pre-upgrade baseline THEN THE SYSTEM SHALL document the increase and
  obtain explicit sign-off before promoting to `admins`/`ovk`.
- WHEN the rollout completes successfully in all three tenants THE SYSTEM
  SHALL update `context/current-version.md` with the new version, per-tenant
  confirmation, and the date.

## Out of scope
- The narrower Sep-11 GHSA-batch-only patch already tracked in
  `ghsa-batch-2026-09-11-upgrade-assessment` — this proposal should be
  reconciled with (and supersede) it rather than executed in parallel.
- CVE-2026-48063 (Baileys) — tracked separately
  (`baileys-cve-48063-version-check`, `baileys-cve-48063-vendored-version-check`).
- The `ovk` empty-logs/pod-health investigation — tracked separately.
- Any restart of `ovk` outside the standard, canary-gated rollout described
  here.
- Adopting `nix-openclaw` packaging changes.
