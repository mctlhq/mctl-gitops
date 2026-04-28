# Audit and pin Axios against UNC1069/WAVESHAPER.V2 backdoor

## Context

North Korea-linked threat actor UNC1069 compromised an Axios npm maintainer account
and published two backdoored versions: `axios@1.14.1` and `axios@0.30.4`. Both
contain the WAVESHAPER.V2 remote-access trojan, which exfiltrates npm tokens, GitHub
tokens, browser credentials, and environment variables from any Node.js process that
loads the package.

The mctl-openclaw service stores particularly sensitive credentials: WhatsApp/Telegram
auth tokens and channel OAuth tokens persisted to per-tenant S3 buckets, plus API
keys present in environment variables at runtime. Exfiltration of any of these would
represent a full credential compromise across all three tenants. A partial audit has
confirmed that `node-slack-sdk` resolves `axios@1.15.0` (safe), but the complete
transitive dependency graph across all workspace packages has not been systematically
checked. Any path that resolves to `axios@1.14.1` or `axios@0.30.4` — even as a
deep transitive dependency — is an active supply-chain backdoor. This proposal is
distinct from the existing `npm-supply-chain-audit` proposal, which targets the
`lotusbail` and `discord.js-user` packages and does not cover the Axios vector.

## User stories

- AS a security engineer I WANT every workspace package's full transitive dependency
  graph audited for the two backdoored Axios versions SO THAT I know whether
  WAVESHAPER.V2 is present in any deployed build.
- AS a platform operator I WANT any path that resolves to `axios@1.14.1` or
  `axios@0.30.4` pinned away to a safe version SO THAT the service cannot load the
  backdoored code at runtime.
- AS a `labs` operator I WANT this change to carry zero additional memory overhead
  SO THAT the `labs` tenant stays within its memory limit.

## Acceptance criteria (EARS)

- WHEN `npm ls axios` is run across all workspace packages THE SYSTEM SHALL produce
  a full dependency tree that is inspected for the strings `axios@1.14.1` and
  `axios@0.30.4`.
- IF any workspace package resolves `axios@1.14.1` or `axios@0.30.4` at any depth
  in its dependency tree THEN THE SYSTEM SHALL add an `overrides` or `resolutions`
  entry in the relevant `package.json` that forces resolution to a safe version.
- WHEN the pinning change is applied THE SYSTEM SHALL produce a lockfile in which
  neither `axios@1.14.1` nor `axios@0.30.4` appears anywhere.
- WHILE the pinned lockfile is in use THE SYSTEM SHALL NOT introduce any new
  packages beyond what is required to satisfy the safe Axios version.
- WHEN CI builds the project after the pinning change THE SYSTEM SHALL pass all
  existing tests without modification.
- IF no workspace package resolves either backdoored version THEN THE SYSTEM SHALL
  record the audit result as a dated entry confirming clean status, with no code
  changes required.

## Out of scope

- Auditing or remediating packages other than Axios (the `lotusbail` and
  `discord.js-user` vectors are handled in the existing `npm-supply-chain-audit`
  proposal).
- Upgrading openclaw core (covered by `upgrade-to-2026-4-26`).
- Rotating credentials that may already have been exfiltrated (that is an incident
  response action outside this proposal's scope; if backdoored versions are found,
  an incident must be opened separately).
- Changes to S3 bucket policies or the canary/probe setup.
- Memory or CPU tuning.
