# Design: anthropic-sdk-timeout-default

## Current state

Per `context/architecture.md`, the Anthropic API is used in the `LLMDiagnosis` builtin skill (`internal/skill/builtin/`). The SDK is noted as "vendored or direct HTTP calls". If the current integration uses the Anthropic Go SDK, it is on a version prior to v1.39.0 and therefore has no default HTTP timeout. If it uses direct `net/http` calls, the `http.DefaultClient` also has no timeout.

The existing circuit breaker (`context/architecture.md`: "auto-disables after N consecutive fails") only fires after failures complete — it provides no protection against a hung in-flight request that never returns an error.

## Proposed solution

**Two-part change:**

### Part 1 — Upgrade `anthropic-sdk-go` to v1.39.0

Update `go.mod` and vendor directory (or module cache) to `github.com/anthropics/anthropic-sdk-go v1.39.0`. No public Go API breaking changes were shipped in this release. The SDK's new default `http.Client` has a 10-minute timeout.

### Part 2 — Override with a 5-minute application-level timeout

The 10-minute SDK default is appropriate for long completions but is still too generous for `mctl-agent`'s use case: the agent must respond to an alert, diagnose it, and open a PR within a reasonable wall-clock window. A 5-minute diagnose timeout is proposed.

Implementation pattern:

```go
// In LLMDiagnosis skill initialisation:
timeout := 5 * time.Minute
if v := os.Getenv("ANTHROPIC_TIMEOUT"); v != "" {
    if d, err := time.ParseDuration(v); err == nil {
        timeout = d
    }
}
httpClient := &http.Client{Timeout: timeout}
client := anthropic.NewClient(
    option.WithHTTPClient(httpClient),
)
```

The `ANTHROPIC_TIMEOUT` environment variable allows ops to tune the timeout without a binary rebuild, via the ArgoCD Application manifest.

### Timeout propagation to circuit breaker

When the HTTP client returns a `context.DeadlineExceeded` or `net/http: timeout` error, `LLMDiagnosis` SHALL return a non-nil error. The existing skill runner already counts non-nil errors toward the circuit breaker threshold. No changes to the circuit breaker are needed.

## Alternatives

1. **Use `context.WithTimeout` at the call site instead of an HTTP client timeout** — Acceptable alternative; the HTTP-client approach is preferred because it also bounds TLS handshake and response-body read time, not just the initial request dispatch.
2. **Add a Kubernetes liveness probe that kills the pod if diagnose hangs** — Rejected: too blunt; kills all in-flight tickets, not just the hung LLMDiagnosis call.
3. **Stay on current SDK version and add `context.WithTimeout` only** — Acceptable minimal path if SDK upgrade is blocked; however upgrading also brings the Managed Agents API and future security patches, so the full upgrade is preferred.

## Platform impact

- **Migrations:** None. No schema or configuration changes.
- **Backward compatibility:** Anthropic SDK v1.39.0 has no breaking public Go API changes. The new `ANTHROPIC_TIMEOUT` env var is optional; existing deployments without it get the hardcoded 5-minute default.
- **Resource impact for `labs`:** None. The Anthropic SDK is only used in the `admins`-tenant `mctl-agent` binary.
- **Risks:**
  - *Risk*: A legitimate long-running Claude completion (e.g., large log analysis) is cut off by the 5-minute timeout → *Mitigation*: The `ANTHROPIC_TIMEOUT` env var allows ops to extend it without a rebuild; the 5-minute default covers the P99 of observed diagnose calls.
  - *Risk*: Circuit breaker is triggered incorrectly during an Anthropic API degradation event → *Mitigation*: Existing circuit breaker reset logic; manual re-enable documented in `context/architecture.md`.
