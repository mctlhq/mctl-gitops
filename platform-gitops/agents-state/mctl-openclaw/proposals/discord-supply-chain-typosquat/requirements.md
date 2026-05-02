# Discord Supply-Chain Typosquat Lockdown (GHSA-69r6-7h4f-9p7q)

## Context

GHSA-69r6-7h4f-9p7q identifies `discord.js-user` (npm) as a fully malicious package: all published versions contain code that silently uploads the process's Discord token to an attacker-controlled remote server. The package name is a deliberate typosquat targeting consumers of the legitimate `discord.js` library.

OpenClaw uses `discord.js` for its Discord channel integration across all three tenants (`labs`, `admins`, `ovk`). If any transitive dependency in the openclaw workspace accidentally resolves `discord.js-user` instead of `discord.js` — due to a typo in a `package.json`, a compromised lock-file entry, or a malicious PR — every Discord bot token in use by all three tenants would be silently exfiltrated.

The existing `baileys-registry-lockdown` proposal established the pattern for guarding against supply-chain attacks on channel libraries; this proposal applies the same pattern to Discord. CVSS is not assigned to advisory-only entries, but the impact of a token exfiltration is equivalent to a critical credential compromise.

## User stories

- AS a security engineer I WANT `discord.js-user` to be explicitly denied in the package registry configuration SO THAT it can never be accidentally installed in any openclaw workspace.
- AS an operator I WANT `discord.js` to be pinned to a verified exact version in every tenant's lock file SO THAT unintended upgrades or substitutions are blocked.
- AS an on-call engineer I WANT the CI pipeline to fail if `discord.js-user` appears in any dependency resolution SO THAT supply-chain substitution is caught before deployment.

## Acceptance criteria (EARS)

- WHEN `npm install` or `npm ci` is executed in any openclaw workspace THEN THE SYSTEM SHALL fail with a non-zero exit code if `discord.js-user` appears in the resolved dependency tree.
- WHEN a gitops PR changes any `package.json` or `package-lock.json` that references Discord-related packages THEN THE SYSTEM SHALL require a CI check that verifies the installed package is `discord.js` and not `discord.js-user`.
- WHILE the `.npmrc` deny-list is active THE SYSTEM SHALL prevent installation of `discord.js-user` even if a downstream transitive dependency declares it.
- IF the Discord bot token for any tenant is confirmed to have been exposed THEN THE SYSTEM SHALL trigger immediate token rotation for that tenant and SHALL NOT restart the Discord channel until a new token is provisioned.
- WHEN the lockdown configuration is applied THEN THE SYSTEM SHALL include `discord.js` integrity hashes (SRI / `npm pack` shasum) in the lock file for all three tenants.

## Out of scope

- Rotation of currently active Discord bot tokens (no evidence of compromise exists today; token rotation is a break-glass action contingent on evidence).
- Changes to the Discord channel's feature set or message routing.
- Applying the deny-list to other channel packages (each channel library is a separate proposal in the supply-chain hardening series).
