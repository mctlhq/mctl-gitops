# Audit and pin Axios transitive dependencies against WAVESHAPER.V2 backdoor

## Context

In April 2026, threat actor UNC1069 (North Korea-linked) compromised an Axios maintainer account and published backdoored npm packages `axios@1.14.1` and `axios@0.30.4`. These versions contain the **WAVESHAPER.V2** remote access trojan, which silently exfiltrates credentials from browsers, npm token stores, and GitHub tokens from the host environment. Axios has approximately 100 million weekly downloads, making this one of the highest-reach supply-chain attacks of 2026.

The `node-slack-sdk` package already pins `axios` to `>=1.15.0`, which is safe. However, the full transitive dependency graph across the mctl-openclaw workspace packages (TypeScript extensions, plugin-sdk consumers, and CI tooling) has not been audited. Any workspace package that resolves `axios@1.14.1` or `axios@0.30.4` — even transitively — would expose S3 credentials, channel OAuth refresh tokens, GitHub deploy keys, and npm publish tokens to the attacker's exfiltration endpoint.

## User stories

- AS a security engineer I WANT a complete audit of every direct and transitive `axios` dependency across all workspace packages SO THAT I can confirm no installation of WAVESHAPER.V2 is present in any tenant's runtime.
- AS a platform engineer I WANT the lockfile and `package.json` overrides to pin `axios` to `>=1.15.0` workspace-wide SO THAT future `npm install` runs cannot resolve the backdoored versions.
- AS an on-call engineer I WANT automated dependency scanning on every CI run SO THAT newly introduced backdoored transitive deps are caught before they reach any tenant.

## Acceptance criteria (EARS)

- WHEN the audit is run THE SYSTEM SHALL produce a full list of every installed version of `axios` across all workspace packages, including transitive dependencies, for each of the three tenants' deployed images.
- IF any installed version of `axios` is `1.14.1` or `0.30.4` THE SYSTEM SHALL immediately flag it as a critical incident and block the affected tenant's deployment pipeline.
- WHEN the remediation is applied THE SYSTEM SHALL pin `axios` to `>=1.15.0` in the root `package.json` via an `overrides` (npm) or `resolutions` (yarn) field so that no descendant package can resolve the backdoored versions.
- WHEN the lock file is regenerated after pinning THE SYSTEM SHALL contain no entry for `axios@1.14.1` or `axios@0.30.4`.
- WHILE the audit reveals the backdoored version was present in any deployed image THE SYSTEM SHALL initiate credential rotation for all secrets potentially accessible from that environment: S3 bucket credentials, channel OAuth refresh tokens, GitHub deploy keys, and npm publish tokens for that tenant.
- WHEN a pull request is opened against the repository THE SYSTEM SHALL run `npm audit` (or equivalent) in CI and fail the build if any dependency scanning check fails for a known malicious package.
- IF new high-severity npm advisories are published THE SYSTEM SHALL surface them within 24 hours via the existing daily researcher cycle.

## Out of scope

- Replacing Axios as an HTTP client across all packages (disproportionate effort for a pinning fix).
- Auditing non-npm build dependencies (Docker base images, shell scripts) — separate security review.
- Credential rotation for tenants confirmed clean after audit (rotation only triggered if backdoored version was found).
