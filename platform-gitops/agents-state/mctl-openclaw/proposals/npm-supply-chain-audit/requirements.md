# Audit and pinning of official npm packages (Baileys, discord.js)

## Context
Active distribution of poisoned npm forks of two key openclaw dependencies has been recorded (inbox/2026-04-27.md). The fake Baileys fork intercepts WhatsApp auth tokens, messages, contacts, and media files via a WebSocket wrapper. The `discord.js-user` package (CVSS 9.8, GHSA-69r6-7h4f-9p7q) leaks Discord tokens to a remote server. The official packages — `@whiskeysockets/baileys` and `discordjs/discord.js` — are not directly affected.

The threat materialises as accidental substitution: if `package.json` or `package-lock.json` pins the wrong package (for example `baileys` instead of `@whiskeysockets/baileys`, or `discord.js-user` instead of `discord.js`), openclaw will send auth tokens of every WhatsApp/Discord account to attacker servers. Even if the dependencies are correct now, without an explicit CI check the risk of accidental substitution on future updates remains open. Effort is minimal: a one-off audit plus a permanent CI step.

## User stories
- AS a security engineer I WANT a one-off audit of `package-lock.json` to confirm only official packages are in use SO THAT the current state is verified and documented
- AS a platform operator I WANT a CI check of resolved URLs in `package-lock.json` against an allowlist of official packages SO THAT accidental substitution with a poisoned fork is caught in the PR before deploy
- AS a developer I WANT a clear list of forbidden package names (e.g. `baileys`, `discord.js-user`) SO THAT I do not add them by accident when updating dependencies

## Acceptance criteria (EARS)
- WHEN the CI pipeline runs for a PR that touches `package.json` or `package-lock.json` THEN THE SYSTEM SHALL check the resolved URLs of all Baileys- and discord.js-related packages against the allowlist of official registries
- IF `package-lock.json` contains a resolved URL that does not match the official registry (`registry.npmjs.org`) for monitored packages THEN THE SYSTEM SHALL fail the CI step indicating the specific package and offending URL
- IF `package.json` or `package-lock.json` contains a name from the forbidden list (`baileys`, `discord.js-user` and equivalents) THEN THE SYSTEM SHALL fail the CI step explaining the correct package
- WHEN `npm audit` runs in CI THEN THE SYSTEM SHALL exit with a non-zero code on advisories with severity >= high for monitored packages
- WHILE the CI check is active THE SYSTEM SHALL run it on every PR that touches dependencies, with no opt-out without an explicit, justified override

## Out of scope
- Audit of every npm dependency in the project (scope limited to Baileys, discord.js, and explicitly known poisoned packages)
- Updates to Baileys or discord.js versions (separate decision; Baileys 7.0.0 is still rc)
- Scanning package contents for malicious code (SAST/SCA is outside the scope of this proposal)
- Changes in the openclaw runtime
- Audit of other channels (Slack, Telegram, Signal etc.) — no recorded poisoned forks
