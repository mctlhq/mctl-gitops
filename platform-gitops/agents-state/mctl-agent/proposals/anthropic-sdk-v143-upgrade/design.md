# Design: anthropic-sdk-v143-upgrade

## Current state

The Anthropic SDK is used in `internal/skill/builtin/` (the `LLMDiagnosis` skill). The
service calls the Messages API with a system prompt containing alert evidence and receives
a structured diagnose response. Skill-level metrics (success/failure counts, latency) are
stored in the SQLite `skill_metrics` table. There is currently no visibility into
prompt-cache hit rates or per-call token costs.

The existing `anthropic-sdk-v141-upgrade` proposal addresses v1.41.0 features
(managed-agents, webhook handling) and has not yet landed. This proposal is additive and
can be implemented independently — or, if v141 lands first, this proposal extends it.

See `context/architecture.md` for the three-tier skill system and LLMDiagnosis fallback
position.

## Proposed solution

### 1. Bump the SDK version

Update `go.mod` to reference the v1.43.0 tag. Run `go mod tidy`. No API surface changes
are expected between v1.41.0 and v1.43.0 that would break existing call sites.

### 2. Wire cache diagnostics into skill metrics

v1.43.0 exposes `Usage.CacheCreationInputTokens` and `Usage.CacheReadInputTokens` in the
Messages API response (beta field, may be zero when cache is cold or not enabled). After
each LLMDiagnosis call, read these fields and append them to the existing metrics record:

```go
// pseudo-code — actual field names subject to SDK type inspection
type diagnoseMetric struct {
    // existing fields ...
    CacheReadTokens     int64
    CacheCreationTokens int64
}
```

Store in the `skill_metrics` table as two new nullable INTEGER columns so that rows
from before the upgrade remain valid. Expose the aggregate via the existing
`GET /api/v1/skills` endpoint (add cache_hit_rate derived field if non-zero data exists).

### 3. Structured-output regression test

Add a table-driven test that constructs a tool schema with nested `$defs` / `anyOf` /
`array` types and asserts that the JSON serialized by the SDK exactly matches the
input schema. This pins the fix and prevents silent regressions on future SDK bumps.

## Alternatives

| Option | Reason rejected |
|---|---|
| Stay on v1.41.0 | Leaves structured-output bug open; no cache visibility |
| Wait for v1.44.0 | No known blocker; v1.43.0 fixes are available now |
| Build cache metrics out-of-band (log parsing) | Fragile; SDK-native fields are reliable and structured |

## Platform impact

### Migrations
Two new nullable INTEGER columns in the `skill_metrics` SQLite table:
`cache_read_tokens` and `cache_creation_tokens`. Both are `NULL` for existing rows —
backward-compatible with zero-downtime deployment.

### Backward compatibility
No changes to external API contracts. `GET /api/v1/skills` response gains optional
`cache_hit_rate` field; clients that ignore unknown fields are unaffected.

### Resource impact
- Negligible: two int64 fields per LLMDiagnosis row in SQLite.
- JSON encoder optimization reduces CPU time per request — small positive effect.
- **`labs` tenant**: no impact — LLMDiagnosis runs only in `admins`; no memory increase.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Cache diagnostics beta fields not present on all accounts | Guard with nil/zero check; gracefully store 0 rather than crash |
| SDK v1.43.0 introduces unexpected compile error | `go build ./...` in CI catches it before merge |
| SQLite migration fails on startup | Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`; test migration in CI |
