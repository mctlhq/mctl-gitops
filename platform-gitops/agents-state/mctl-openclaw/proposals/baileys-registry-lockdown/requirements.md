# Pin Baileys to official package and enforce registry allowlist

## Context
In December 2025 the `lotusbail` npm package was disclosed as an active typosquatting attack against `@whiskeysockets/baileys`. The malicious package has accumulated over 56,000 downloads. Its payload steals WhatsApp auth tokens and session keys. On the mctl-openclaw platform, WhatsApp sessions are handled by the Baileys channel and their credentials are stored in S3 per ADR-0002. A successful substitution attack would expose those credentials, allowing an attacker to take over WhatsApp sessions for all three tenants.

The current dependency on `@whiskeysockets/baileys` (v7.0.0-rc.9) is a release candidate and is pinned by version string, but no mechanism prevents a compromised or spoofed package from being resolved at install time. This proposal introduces exact-version pinning in `package-lock.json` and a `.npmrc` registry allowlist (or equivalent scope enforcement) to ensure that only the genuine `@whiskeysockets/baileys` package from the official npm registry can be installed. This is a narrower hardening measure than the broader `npm-supply-chain-audit` proposal and can be delivered independently.

## User stories
- AS a platform operator I WANT `@whiskeysockets/baileys` pinned to an exact version with a verified integrity hash SO THAT no typosquatted or substituted package can be silently installed.
- AS a security reviewer I WANT an npm registry allowlist (or scope restriction) enforced in CI and local development SO THAT only approved package sources are used for the Baileys dependency.
- AS the `ovk` customer I WANT WhatsApp session credentials protected against supply-chain substitution attacks SO THAT my auth tokens stored in S3 cannot be exfiltrated by a malicious npm package.

## Acceptance criteria (EARS)
- WHEN `npm install` is run in the mctl-openclaw workspace THE SYSTEM SHALL resolve `@whiskeysockets/baileys` only from the official npm registry scope (`registry.npmjs.org`) and reject any package resolved from an unlisted registry.
- WHEN `package-lock.json` is committed THE SYSTEM SHALL contain an exact version pin and a `resolved` URL pointing to `registry.npmjs.org` for `@whiskeysockets/baileys`.
- WHEN `package-lock.json` is committed THE SYSTEM SHALL contain the `integrity` (sha512) hash for the `@whiskeysockets/baileys` package, and `npm ci` SHALL fail if the hash does not match.
- WHILE CI runs `npm ci` THE SYSTEM SHALL fail the build if any package in the `@whiskeysockets` scope is resolved from a registry other than `registry.npmjs.org`.
- IF a developer attempts to `npm install` a package whose name matches the known typosquats list (e.g., `lotusbail`) THE SYSTEM SHALL fail with an error via registry allowlist or `.npmrc` deny pattern.
- WHEN the lockfile changes in a pull request THE SYSTEM SHALL require a reviewer to verify that the `resolved` URL and `integrity` hash for `@whiskeysockets/baileys` remain unchanged or are intentionally updated.

## Out of scope
- Upgrading `@whiskeysockets/baileys` beyond v7.0.0-rc.9 (version change is a separate decision).
- Auditing or pinning all npm dependencies across the workspace (covered by the separate `npm-supply-chain-audit` proposal).
- Replacing the Baileys WhatsApp channel with an alternative library.
- Changes to S3 bucket layout or session storage format (ADR-0002 unchanged).
- Any memory footprint change (this proposal adds no runtime dependencies).
