# Design: scaffolder-secret-log-redaction

## Current state
The Scaffolder backend (`packages/backend`) uses the Backstage `createBuiltinActions` set plus custom actions in `plugins/scaffolder-backend-module-mctl/`. Log lines are emitted via the Scaffolder task logger, which forwards to:
1. The SSE stream consumed by the Scaffolder frontend UI.
2. The Winston root logger, which ships to Loki via a Loki transport.

Secret template parameters (`secret: true` in the JSON Schema) are available to actions at runtime. There is no current mechanism to strip those values from log output before they reach the transports.

## Proposed solution
Implement a **`SecretRedactingLogger`** wrapper around the Scaffolder task logger. The wrapper:
1. Receives the set of secret parameter values for the current task at task-start time.
2. Wraps every `log()` call to perform a string-replace of each secret value with `[REDACTED]` before delegating to the underlying logger.
3. Is injected into the Scaffolder task execution context via the existing `createTaskLogger` extension point in `@backstage/plugin-scaffolder-backend`.

Implementation location: `plugins/scaffolder-backend-module-mctl/src/lib/SecretRedactingLogger.ts`.

The redaction list is rebuilt per task (not shared across tasks) to avoid cross-contamination. String matching is case-sensitive and literal (no regex interpolation of secret values, which avoids ReDoS risk if a secret contains regex metacharacters).

## Alternatives

### A. Patch the upstream `fetch:template` action
Fork and patch the upstream action to suppress secret echoing. Dropped: upstream patches break on every Backstage version bump; the redacting logger approach is version-agnostic.

### B. Configure Loki pipeline stages to drop matching lines
Use Loki `pipeline_stages` with a `replace` stage to scrub secrets at ingest. Dropped: requires knowing secret values at Loki configuration time, which is impractical for per-task dynamic secrets; also only protects Loki, not the frontend stream.

### C. Wait for Backstage to fix upstream
Backstage acknowledged GHSA-3x3q-ghcp-whf7 but has not yet shipped a fix in stable. Dropped as sole mitigation: the fix timeline is unknown; defence-in-depth is warranted now.

## Platform impact
- **Migrations:** No changes to existing templates or catalog-info.yaml files. The `SecretRedactingLogger` is transparent to template authors.
- **Backward compatibility:** Fully backward-compatible. If upstream ships a fix, the custom wrapper can be removed without any template changes.
- **Resource impact:** Negligible CPU overhead (string search per log line). No memory footprint increase. Tenant `labs` is unaffected.
- **Risks and mitigations:**
  - *Secret value substring collision:* If a secret value is a common short string (e.g. `"true"`), redaction will mask unrelated log tokens. Mitigated by enforcing a minimum secret-value length of 8 characters before redacting; values shorter than 8 chars are logged with a warning instead.
  - *Performance regression in high-volume template runs:* Mitigated by benchmarking with a 10,000-line synthetic log run; target < 10 ms per line.
