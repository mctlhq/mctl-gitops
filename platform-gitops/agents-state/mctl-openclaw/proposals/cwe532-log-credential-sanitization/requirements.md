# CWE-532 Interim Mitigation: Log Credential Sanitization

## Context

openclaw 2026.3.14 (the version running on all three tenants — admins, labs, ovk) does not redact
sensitive values before writing HTTP request logs. The following categories of secrets appear in
plaintext in pod stdout/stderr: `?password=` query parameters, `?token=` query parameters, and
`Authorization:` HTTP headers. These values carry live OAuth access and refresh tokens, Slack
webhook tokens, webhook callback authentication parameters, plugin auth credentials, and
OpenAI/provider API keys. Any operator or pipeline that has log-read access — including Loki,
CloudWatch, Datadog, and Grafana Loki backends — can therefore retrieve production secrets without
authenticating to the application itself. This is a CWE-532 (Information Exposure Through Log
Files) finding.

The permanent application-level fix ships in openclaw 2026.5.2. That upgrade must soak through the
mandatory labs → admins → ovk promotion cycle, which may take several days. During that window the
credential exposure continues unmitigated. This proposal describes an interim mitigation implemented
entirely at the log-shipper (Fluentd/Vector DaemonSet) layer, deployable immediately and
independently of the upgrade timeline. The interim mitigation will be retired once 2026.5.2 is
confirmed healthy across all three tenants, though it may be retained as defense-in-depth.

## User stories

- AS a platform operator I WANT sensitive query parameters and Authorization headers to be redacted
  in forwarded logs SO THAT credentials are not exposed to anyone with log-read access.
- AS a security officer I WANT the redaction to apply to all three tenants (admins, labs, ovk)
  simultaneously SO THAT no tenant's logs remain a source of plaintext secrets while the upgrade
  soak cycle completes.
- AS a platform operator I WANT the scrubbing transform deployed without restarting application
  pods SO THAT the mitigation does not trigger the restore-state probe or disrupt the s3-sync
  canary.
- AS a platform operator I WANT the scrubbing transform to be removable cleanly after the 2026.5.2
  upgrade lands SO THAT we do not carry permanent operational debt.
- AS a security officer I WANT log-aggregation backend access restricted by NetworkPolicy SO THAT
  even logs that may already have been shipped to the backend are accessible only to authorised
  principals.

## Acceptance criteria (EARS)

- WHEN a log line emitted by any openclaw pod in the admins, labs, or ovk namespace contains the
  pattern `?password=<value>`, THE SYSTEM SHALL replace `<value>` with the literal string REDACTED
  before the line is forwarded to the log-aggregation backend.
- WHEN a log line emitted by any openclaw pod in the admins, labs, or ovk namespace contains the
  pattern `?token=<value>`, THE SYSTEM SHALL replace `<value>` with the literal string REDACTED
  before the line is forwarded to the log-aggregation backend.
- WHEN a log line emitted by any openclaw pod in the admins, labs, or ovk namespace contains an
  `Authorization:` header value (case-insensitive), THE SYSTEM SHALL replace the header value with
  the literal string REDACTED before the line is forwarded to the log-aggregation backend.
- WHILE the scrubbing transform is active, THE SYSTEM SHALL preserve the full structure and
  remaining content of each log line so that debugging information other than the redacted secrets
  remains intact.
- WHILE the scrubbing transform is active, THE SYSTEM SHALL apply the transform to all pod
  namespaces that host openclaw workloads (admins, labs, ovk) without exception.
- IF a log line contains more than one sensitive pattern, THEN THE SYSTEM SHALL redact all
  occurrences within that line, not only the first.
- IF the log-aggregation backend does not already have a Kubernetes NetworkPolicy restricting
  ingress, THEN THE SYSTEM SHALL apply a NetworkPolicy that limits which service accounts and
  namespaces may reach the backend.
- WHEN openclaw 2026.5.2 (or later) has been confirmed healthy across all three tenants, THE
  SYSTEM SHALL support clean removal of the log-shipper scrubbing transform without requiring a pod
  restart or application configuration change.
- WHEN the scrubbing transform configuration is changed or rolled back, THE SYSTEM SHALL apply the
  change without restarting openclaw application pods.

## Out of scope

- Purging or redacting credentials that have already been shipped to the log-aggregation backend
  before this mitigation is deployed (historical log remediation is a separate workstream).
- Application-level code changes to openclaw itself — the permanent fix belongs to the
  `upgrade-to-2026-5-2` proposal.
- Rotation of credentials that may have been exposed prior to the mitigation being in place —
  credential rotation is an incident-response action outside this proposal.
- Changes to the S3-state persistence layer, the s3-sync canary, or the restore-state probe.
- Modifying the three-layer skills architecture or any YAML/remote skills.
- Scrubbing secrets from log lines that are not HTTP request logs (e.g., skill execution traces).
- Enforcement of secret scanning in the Git repository — out of scope for an infra-layer mitigation.
