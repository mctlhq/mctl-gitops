# Upgrade openclaw to 2026.4.25 (close 5 unpatched CVEs)

## Context
The current openclaw version 2026.3.14 carries 5 unpatched vulnerabilities recorded in inbox/2026-04-27.md. The most critical is CVE-2026-41349 (CVSS 8.8): an LLM agent can silently disable execution approval via `config.patch`, which in the openclaw agentic environment means uncontrolled action execution without user consent. Alongside it are open CVE-2026-41361 (SSRF via IPv6 special-use ranges), CVE-2026-41359 (privilege escalation through the Telegram send endpoint), CVE-2026-41353 (allowProfiles bypass via persistent profile mutation) and CVE-2026-41348 (Discord slash command / autocomplete auth bypass, CVSS 5.4).

The upstream 2026.4.25 release closes all five and contains 200+ changes, including a TTS upgrade, a plugin registry on cold-persisted storage, OpenTelemetry expansion, and browser automation hardening. The upgrade follows the established route labs → admins → ovk per ADR 0001; before the labs rollout we must measure the RAM delta because the labs tenant is close to the memory limit.

## User stories
- AS a platform operator I WANT openclaw upgraded to 2026.4.25 SO THAT the five open CVEs are closed before potential exploitation
- AS a security engineer I WANT confirmation that all three tenants run on the patched version SO THAT I can close the security findings in the tracker
- AS a labs tenant operator I WANT a pre-flight check of the new release's RAM footprint SO THAT the upgrade does not lead to OOM in labs
- AS an ovk production operator I WANT a rollout that exercises the restore-state probe and the s3-sync canary SO THAT WhatsApp/Telegram sessions are not lost during the upgrade

## Acceptance criteria (EARS)
- WHEN the openclaw 2026.4.25 Docker image is deployed to the labs tenant THEN THE SYSTEM SHALL pass the restore-state readiness probe before ArgoCD transitions to Healthy
- WHEN the labs rollout finishes THE SYSTEM SHALL record the actual pod RAM consumption and compare it to the current labs limit; if the delta exceeds 50MB — block the admins rollout pending a decision
- WHILE rollout is in progress in any tenant THE SYSTEM SHALL keep the s3-sync canary suspended and resume it with a delay after a successful rollout
- WHEN the labs and admins rollouts have completed without regressions THE SYSTEM SHALL allow promotion to ovk per the rollout route labs → admins → ovk
- IF the restore-state probe fails to pass within the allotted timeout in any tenant THEN THE SYSTEM SHALL automatically roll back the deploy to the previous version (2026.3.14)
- IF the actual RAM consumption in labs after the upgrade exceeds the current limit THEN THE SYSTEM SHALL not promote the image to admins and ovk without an explicit decision to raise the limit
- WHEN openclaw 2026.4.25 is running in all three tenants THE SYSTEM SHALL no longer have active CVE-2026-41349, CVE-2026-41361, CVE-2026-41359, CVE-2026-41353, CVE-2026-41348

## Out of scope
- Node.js runtime upgrade (no urgent security trigger)
- TypeScript upgrade to 6.x (no security CVE)
- Migration of the plugin registry to cold-persisted storage (a feature of the new release; separate proposal if needed)
- Updates to Baileys, discord.js, node-slack-sdk dependencies (covered by separate proposals)
- Changes to channel or skill configuration
