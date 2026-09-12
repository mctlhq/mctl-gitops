# Confirm and Remediate Argo Workflows Artifact-Credential Plaintext Logging (CVE-2026-42295)

## Context
Argo Workflows' workflow executor logs S3/GCS/Azure/Git artifact-repository credentials in
plaintext during artifact input/output operations, in versions 4.0.0 through <4.0.5. This
platform's Argo Workflows controller/executor fleet is currently pinned at 4.1.2/4.1.3 (per
`platform-gitops/argo-workflows/`), which postdates the fix version, but this has not been
explicitly confirmed against this CVE, and no audit has been done to check whether any
historical executor logs — collected before the version was last bumped — contain plaintext
credentials that are still readable by anyone with log access.

Argo Workflows in this platform runs all cron and on-demand pipelines (see
`context/architecture.md`), including builds and deploys that are centralized here, and its
executor pulls artifact-repository credentials from Vault via ExternalSecrets
(`platform-gitops/argo-workflows/secrets/`). If credentials were ever logged in plaintext
during a window when the fleet ran an affected version, and log retention/access is broader
than the credential's own access scope, this constitutes a real secret-exposure risk even
after the version fix — the historical log entries remain a live leak until rotated.

## User stories
- AS a platform security engineer I WANT to confirm the Argo Workflows executor version was
  never in the vulnerable range without the fix, or if it was, that historical logs are
  audited and any exposed credentials rotated SO THAT no artifact-repository credential
  remains exposed in plaintext logs accessible to a broader audience than intended.
- AS a platform operator I WANT this confirmed as a low-effort audit rather than a full
  patch cycle when the fleet already postdates the fix SO THAT the team's effort is
  proportionate to the actual residual risk.

## Acceptance criteria (EARS)
- WHEN the currently-pinned Argo Workflows version is inspected THE SYSTEM SHALL confirm it
  is at or above 4.0.5, or document the exact version history (including any period spent
  in the 4.0.0-<4.0.5 range) if it was ever lower.
- IF the fleet was ever pinned to a version in the 4.0.0-<4.0.5 range THEN THE SYSTEM SHALL
  audit historical executor logs from that period for plaintext artifact-repository
  credentials.
- IF plaintext credentials are found in historical logs THEN THE SYSTEM SHALL rotate the
  affected credentials in Vault and confirm the corresponding ExternalSecret has propagated
  the new value before considering the exposure closed.
- WHEN the audit is complete and no evidence of exposure is found THE SYSTEM SHALL record
  the confirmation (version history, log-retention window checked, and outcome) in
  `platform-gitops/agents-state/argo-workflows-cred-log-leak/` as a durable audit trail.
- WHILE the fleet remains pinned at or above 4.0.5 THE SYSTEM SHALL treat no further
  version action as required for this specific CVE.

## Out of scope
- CVE-2026-42296 / CVE-2026-28229 (strict-mode bypass, unauthenticated template info
  disclosure) — already tracked in `argo-workflows-cve-bundle-upgrade` /
  `argo-workflows-cve-patch-v2`.
- Any Argo Workflows version bump beyond what is already pinned, since the fleet already
  postdates the fix for this specific CVE.
- A general redesign of executor logging (e.g. a structured log-redaction framework) beyond
  confirming this specific credential-logging class is closed.
- Any change to `labs` tenant workload memory allocation — this is a controller/executor-log
  audit, not a tenant workload change.
