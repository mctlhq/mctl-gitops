# Baileys Supply Chain Audit

## Context

`mctl-openclaw` uses `@whiskeysockets/baileys` (the legitimate WhatsApp Web library) to power the WhatsApp channel across all three tenants: `admins`, `labs`, and `ovk`. A malicious npm package named **Lotusbail** — recorded at approximately 56,000 downloads — impersonates Baileys. It exfiltrates WhatsApp auth tokens, session keys, all messages, contacts, and media through a socket wrapper, and embeds 27 infinite-loop traps to defeat debuggers. Critically, persistence survives package removal until linked WhatsApp devices are manually revoked.

Our WhatsApp auth tokens and session state are stored in S3 per ADR-0002. A confirmed compromise would expose production customer data in the `ovk` tenant. The `labs` tenant is memory-constrained; any remediation must not increase its memory footprint. The purpose of this proposal is to close the current gap: there is no automated guard that prevents a Baileys-adjacent malicious package from entering the dependency tree, and there is no documented revocation runbook for the event of a compromise.

## User stories

- AS a security engineer I WANT automated CI verification that the lockfile resolves only to `@whiskeysockets/baileys` at a pinned integrity hash SO THAT no Baileys-impersonating package can enter the build undetected.
- AS an ops engineer I WANT a documented, step-by-step revocation runbook SO THAT if a compromise is detected I can revoke all linked WhatsApp devices and re-establish clean sessions without relying on institutional memory.
- AS a platform engineer I WANT dependency pinning enforced for Baileys SO THAT an accidental range upgrade cannot silently pull in an untrusted version.

## Acceptance criteria (EARS)

- WHEN a pull request is opened or a CI pipeline runs, THE SYSTEM SHALL scan the lockfile (`package-lock.json` or `yarn.lock`) and fail the build if any package named `lotusbail` or matching the pattern `*bail*` (excluding `@whiskeysockets/baileys`) is present.
- WHEN a pull request is opened or a CI pipeline runs, THE SYSTEM SHALL fail the build if `@whiskeysockets/baileys` is not pinned to an exact version and integrity hash in the lockfile.
- WHILE the service is running in any tenant, THE SYSTEM SHALL not load any npm package that resolves the Baileys module identifier to a package other than `@whiskeysockets/baileys`.
- IF a Baileys-adjacent package name is detected in the lockfile or `node_modules` tree at runtime audit, THEN THE SYSTEM SHALL emit an alert to the on-call channel and block further deployments to that tenant until the alert is acknowledged and the lockfile is remediated.
- WHEN a compromise of WhatsApp auth tokens is confirmed or suspected, THE SYSTEM SHALL provide a documented revocation runbook that an operator can execute to revoke all linked WhatsApp devices and force QR re-pairing within one business hour.
- WHEN a Baileys version update is proposed, THE SYSTEM SHALL require that the updated integrity hash is explicitly committed to the lockfile and that the change follows the `labs` → `admins` → `ovk` rollout order defined in ADR-0001.
- IF the `@whiskeysockets/baileys` package in the lockfile does not match the expected integrity hash, THEN THE SYSTEM SHALL fail the CI build with a human-readable error message identifying the mismatched field.

## Out of scope

- Replacing `@whiskeysockets/baileys` with an alternative WhatsApp Web library (evaluated and deferred; migration risk exceeds current threat).
- A full audit of every npm package in the workspace (addressed by a separate, broader supply-chain initiative).
- Changes to the S3 session-storage design described in ADR-0002.
- Automated device revocation via API (the WhatsApp Web protocol does not provide a reliable server-side revocation endpoint; manual QR re-pairing is the only safe path).
