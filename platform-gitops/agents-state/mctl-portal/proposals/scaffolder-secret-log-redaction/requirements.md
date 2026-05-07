# Scaffolder Secret Log Redaction

## Context
GHSA-3x3q-ghcp-whf7 (published 2026-01-21, Low severity) discloses that the Backstage Scaffolder's `fetch:template` action can emit the literal values of secret template parameters in execution log lines that are streamed to the frontend and persisted in the backend log store (Loki on this platform). mctl-portal's Scaffolder uses Vault-backed secrets for service-onboarding templates (database credentials, API tokens, signing keys). Any user with access to the Scaffolder task log — or to Loki — can read those secrets after a template run.

This proposal adds a secret-redaction layer to the Scaffolder backend that masks secret values in all log output, providing defence-in-depth independent of the Backstage version bump in `backstage-v1504-security-upgrade`.

## User stories
- AS a security operator I WANT Scaffolder log lines that contain secret values to have those values replaced with `[REDACTED]` SO THAT secrets are not exposed to Loki or frontend users.
- AS a platform engineer I WANT the redaction to apply to all Scaffolder task log transports (frontend stream, Loki push, local console) SO THAT no single transport leaks secrets.
- AS a developer I WANT non-secret template parameter values to remain visible in logs SO THAT I can debug template execution without losing context.

## Acceptance criteria (EARS)
- WHEN a Scaffolder task log line contains the literal value of a parameter marked `secret: true` in the template schema THE SYSTEM SHALL replace all occurrences of that value with the string `[REDACTED]` before writing the line to any transport.
- WHEN a Scaffolder task completes (success or failure) THE SYSTEM SHALL ensure no log line stored in Loki contains any of the task's secret parameter values in plaintext.
- WHILE a Scaffolder task is running THE SYSTEM SHALL stream redacted log lines to the frontend in real time; the redaction must not introduce perceptible latency (< 10 ms per line).
- IF a secret value is an empty string THE SYSTEM SHALL skip redaction for that value to avoid masking unrelated empty-string tokens.
- IF the Backstage Scaffolder backend is upgraded to a version that includes native secret redaction THE SYSTEM SHALL be able to remove the custom redaction layer without breaking existing templates.

## Out of scope
- Redacting secrets from ArgoWorkflow step logs (separate concern, separate service).
- Retroactively scrubbing existing Loki log entries (requires a separate Loki data-management operation).
- Changing how secrets are injected into templates (remains Vault/ExternalSecret).
