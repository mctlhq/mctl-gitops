# Tasks: anthropic-sdk-v143-upgrade

- [ ] 1. Bump SDK version in `go.mod` — change the anthropic-sdk-go dependency to
  `v1.43.0`; run `go mod tidy`. — DoD: `go.mod` and `go.sum` updated; `go build ./...`
  succeeds with no compile errors.

- [ ] 2. Inspect v1.43.0 `Usage` type for cache fields (depends on 1) — locate
  `CacheCreationInputTokens` and `CacheReadInputTokens` in the SDK's type definitions
  and confirm field names and zero-value behaviour. — DoD: field names confirmed and
  documented in the PR description.

- [ ] 3. Add SQLite migration for cache columns (depends on 2) — add a startup migration
  that runs `ALTER TABLE skill_metrics ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER`
  and `ALTER TABLE skill_metrics ADD COLUMN IF NOT EXISTS cache_creation_tokens INTEGER`.
  — DoD: migration runs idempotently on a fresh DB and on an existing DB with old rows.

- [ ] 4. Wire cache fields in LLMDiagnosis (depends on 2, 3) — after each Messages API
  call, read the two cache token counts from the response `Usage` struct (guard for nil /
  zero) and write them to the new columns in the skill_metrics row. — DoD: a unit test
  with a mocked API response that includes cache tokens confirms the values are stored.

- [ ] 5. Expose cache_hit_rate on `GET /api/v1/skills` (depends on 4) — compute
  `cache_read_tokens / (cache_read_tokens + cache_creation_tokens)` as a float when the
  denominator is non-zero; add as an optional `cache_hit_rate` field on the LLMDiagnosis
  skill entry in the API response. — DoD: endpoint returns the field when data exists;
  omits it when all rows have zero cache counts.

- [ ] 6. Add structured-output regression test (depends on 1) — write a table-driven test
  that constructs tool schemas with nested `$defs`, `anyOf`, and `array` types, serialises
  them via the SDK, and asserts byte-for-byte equality with the input schema JSON.
  — DoD: test fails on v1.41.x (demonstrating the bug) and passes on v1.43.0.

## Tests

- [ ] T1. `go build ./...` compiles cleanly against v1.43.0.
- [ ] T2. `go test ./...` — all existing LLMDiagnosis tests pass without modification.
- [ ] T3. Cache-token unit test: mock a Messages response with non-zero cache fields;
  assert SQLite row contains correct `cache_read_tokens` and `cache_creation_tokens`.
- [ ] T4. Nil-safety test: mock a response with zero / missing cache fields; assert no
  panic and that the SQLite row stores 0 gracefully.
- [ ] T5. SQLite migration idempotency test: run migration twice on the same DB; assert
  no error and no duplicate columns.
- [ ] T6. Structured-output regression test (see task 6).

## Rollback

Revert `go.mod`, `go.sum`, and the LLMDiagnosis source changes. The two new SQLite
columns (`cache_read_tokens`, `cache_creation_tokens`) are nullable and backward-
compatible — they can remain in the schema after rollback without affecting the previous
binary. No data is lost. Re-deploy via ArgoCD sync to the previous commit.
