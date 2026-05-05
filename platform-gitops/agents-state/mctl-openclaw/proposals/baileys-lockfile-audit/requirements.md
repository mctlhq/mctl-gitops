# Audit npm lockfile to confirm Baileys dependency is the official whiskeysockets package, not malicious "lotusbail"

## Context

The mctl-openclaw workspace uses `@whiskeysockets/baileys` to implement the WhatsApp Web channel for all three tenants. The npm package `lotusbail` — a malicious Baileys fork with approximately 56,000 downloads — is a known typosquat that exfiltrates WhatsApp auth tokens, messages, contacts, and media through a hidden socket wrapper. Per `context/architecture.md` and ADR-0002, WhatsApp auth tokens are stored in S3; a compromise of the Baileys dependency would directly expose all S3-backed session state for every tenant.

The `baileys-registry-lockdown` proposal (already in `proposals/`) established scope-pin and integrity controls. This proposal addresses an orthogonal and more immediate concern: confirming that the current `package-lock.json` across all three tenant builds does not already reference `lotusbail` or any other non-official resolution for the Baileys dependency, and that the lockfile integrity hashes match the official `registry.npmjs.org` distribution. This audit must be completed before any other rollout (including `upgrade-to-2026-5-3`) proceeds, because a compromised lockfile would survive an image tag bump unchanged.

## User stories

- AS a security operator I WANT to confirm the npm lockfile references only the official `@whiskeysockets/baileys` package SO THAT I know WhatsApp session state is not being exfiltrated by a malicious substitute.
- AS a platform operator I WANT the audit to cover all three tenants (`labs`, `admins`, `ovk`) SO THAT no tenant is silently running a compromised build.
- AS a security operator I WANT a documented audit result SO THAT future audits have a clean baseline and the finding is recorded for compliance purposes.
- AS a platform operator I WANT to be blocked from proceeding with any other rollout IF `lotusbail` is found SO THAT a compromised dependency is not promoted to production.

## Acceptance criteria (EARS)

- WHEN the audit is initiated THE SYSTEM SHALL inspect the `package-lock.json` (or equivalent lockfile) for all three tenants and identify every entry whose package name matches `baileys`, `lotusbail`, or any name resolving to a Baileys-compatible API.
- WHEN the audit inspects a Baileys-related lockfile entry THE SYSTEM SHALL verify that the `resolved` field starts with `https://registry.npmjs.org/@whiskeysockets/baileys/`.
- WHEN the audit inspects a Baileys-related lockfile entry THE SYSTEM SHALL verify that the `integrity` (sha512) hash matches the value published on the official registry for the declared version.
- IF any lockfile entry references the package name `lotusbail` THEN THE SYSTEM SHALL immediately raise a P0 security incident, halt all other rollouts, and quarantine the affected build.
- IF any Baileys-related lockfile entry resolves to a URL other than `https://registry.npmjs.org/@whiskeysockets/baileys/` THEN THE SYSTEM SHALL treat the finding as a security incident requiring investigation before any rollout proceeds.
- IF any Baileys-related lockfile entry carries an `integrity` hash that does not match the official registry THEN THE SYSTEM SHALL treat the finding as a security incident requiring investigation before any rollout proceeds.
- WHEN all three tenants pass the audit THE SYSTEM SHALL produce a written audit record confirming the package name, resolved URL, version, and integrity hash for `@whiskeysockets/baileys` in each tenant's lockfile.
- WHILE the audit record is clean THE SYSTEM SHALL allow other rollouts to proceed (the blocking condition is lifted).
- IF a clean audit record exists THEN THE SYSTEM SHALL confirm that `baileys-registry-lockdown` controls (scope pin in `.npmrc`, `npm ci` enforcement) are in place or schedule them as an immediate follow-on (if not already deployed).

## Out of scope

- Installing or configuring the scope-pin `.npmrc` control (covered by `baileys-registry-lockdown`).
- Auditing npm packages other than Baileys and its direct dependency chain for supply-chain risk (covered by `npm-supply-chain-audit`).
- Changes to the WhatsApp channel extension code or configuration.
- Changes to S3 state layout or auth token rotation procedures.
- Any Kubernetes or ArgoCD manifest changes.
