# Pin and Verify Prometheus v3.11.3 to Remediate Credential Exposure and XSS

## Context

Prometheus v3.11.3 was released as a security patch addressing three distinct vulnerabilities:

1. **AzureAD OAuth credential exposure** — earlier versions could log AzureAD OAuth client
   secrets to stdout in debug mode, exposing credentials in log aggregators.
2. **Snappy decompression Denial-of-Service** — malformed snappy-compressed payloads sent
   to the remote-write endpoint could cause Prometheus to crash, interrupting metrics
   collection across all tenants.
3. **Stored XSS in the heatmap UI** — injected data could be rendered unescaped in the
   Prometheus heatmap chart, allowing a user with write access to metrics labels to execute
   JavaScript in another user's browser session.

Prometheus is templated through this GitOps repository. No existing proposal covers these
Prometheus CVEs, and the pinned version in values files may not yet reflect v3.11.3.
A version audit and pin update is required to confirm the platform is running the patched
version.

## User stories

- AS a platform security engineer I WANT Prometheus to run v3.11.3 or later SO THAT the
  platform is not exposed to credential leakage, DoS, or XSS vulnerabilities documented
  in the v3.11.3 release.
- AS a platform operations engineer I WANT the Prometheus version pin in all values files
  to be set to v3.11.3 SO THAT ArgoCD reconciliation always deploys the patched image.
- AS a platform security engineer I WANT to confirm that AzureAD OAuth credentials are not
  logged to stdout SO THAT secrets are not accidentally captured by the log aggregation
  pipeline.

## Acceptance criteria (EARS)

- WHEN Prometheus is deployed by ArgoCD THE SYSTEM SHALL run image version v3.11.3 or later.
- WHEN AzureAD OAuth is configured for Prometheus THE SYSTEM SHALL NOT write OAuth client
  credentials to stdout or any log output, regardless of log level.
- WHILE Prometheus is scraping targets and receiving remote-write data THE SYSTEM SHALL handle
  malformed snappy-compressed payloads gracefully without crashing or restarting the Prometheus
  process.
- IF a user navigates to the Prometheus heatmap chart UI THE SYSTEM SHALL sanitize all
  metric label data before rendering it as HTML, preventing stored XSS execution.
- WHEN any values file under `platform-gitops/services/` or `platform-gitops/helm-charts/`
  references a Prometheus image or chart version THE SYSTEM SHALL reference v3.11.3 or later.

## Out of scope

- Upgrading Prometheus beyond v3.11.3 (this is a patch-level pin, not a feature upgrade).
- Replacing Prometheus with an alternative metrics backend.
- Changes to Grafana dashboards or alerting rules unrelated to the patch.
- Full Prometheus Operator upgrade (separate concern, out of scope for this patch).
- Changes that would increase memory consumption in tenant `labs`.
