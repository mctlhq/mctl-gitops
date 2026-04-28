# Close CVE-2026-32237: server env-variable leak via the dry-run endpoint

## Context
CVE-2026-32237 affects `plugin-scaffolder-backend` versions 3.1.0–3.1.4 (excluding 3.1.1+).
An authenticated user with template dry-run permission receives the full values of
server-side environment variables in the endpoint response (Vault token, Postgres DSN,
GitHub App credentials) due to incomplete redaction of nested JSON objects. In mctl-portal
those secrets are mounted via ExternalSecret and are critical for platform security.

Notably, the patch for CVE-2026-32237 is in the same `plugin-scaffolder-backend` 3.1.1+
release that closes CVE-2026-24046 (scaffolder-path-traversal). Both CVEs can and should
be closed by a single PR, reducing operational load and minimising the number of
production deploys.

## User stories
- AS a platform engineer I WANT the scaffolder dry-run endpoint to redact all server-side
  environment variables from its response SO THAT authenticated users cannot extract Vault
  tokens, Postgres DSN, or GitHub App credentials via template preview.
- AS a security officer I WANT both CVE-2026-24046 and CVE-2026-32237 to be closed in a
  single deployment SO THAT the attack surface for scaffolder is eliminated atomically.
- AS a developer I WANT the dry-run functionality to remain available for template
  debugging SO THAT template authors can still preview scaffolder output without
  triggering secrets exposure.

## Acceptance criteria (EARS)
- WHEN a user calls the scaffolder dry-run endpoint THE SYSTEM SHALL return template
  output with all server-side environment variable values replaced by redaction markers.
- WHEN the dry-run response contains nested JSON objects THE SYSTEM SHALL recursively
  redact any field whose key or value matches known secret patterns (tokens, DSNs,
  credentials).
- WHILE `plugin-scaffolder-backend` >= 3.1.1 is running THE SYSTEM SHALL not expose any
  `process.env` values in dry-run API responses.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-32237 or CVE-2026-24046.
- WHEN a dry-run is executed with a valid template and no path-traversal payloads THE
  SYSTEM SHALL return a successful preview response with correctly rendered template
  variables (non-secret).

## Out of scope
- Restricting permissions to call the dry-run endpoint (RBAC) — separate topic.
- Rotation of already-compromised secrets (if the leak occurred before the patch) — out
  of scope for this proposal; requires a separate incident response.
- Changes in the `labs` tenant.
- Audit of custom plugins for similar redaction vulnerabilities.
