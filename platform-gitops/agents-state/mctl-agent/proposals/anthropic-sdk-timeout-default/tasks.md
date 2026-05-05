# Tasks: anthropic-sdk-timeout-default

- [ ] 1. Audit current Anthropic integration — locate the `LLMDiagnosis` skill source file(s) and confirm whether the SDK or raw `net/http` calls are used; check if any `http.Client` timeout is already configured — DoD: a written note in the PR description stating the current integration pattern and current timeout (or lack thereof).

- [ ] 2. Update `go.mod` and `go.sum` to `anthropic-sdk-go` v1.39.0 (depends on 1) — run `go mod tidy` — DoD: `go.mod` references v1.39.0, `go mod verify` passes.

- [ ] 3. Implement configurable HTTP client timeout in `LLMDiagnosis` (depends on 2) — add the `ANTHROPIC_TIMEOUT` env var parsing and construct the `http.Client{Timeout: timeout}` passed to the Anthropic SDK via `option.WithHTTPClient` — DoD: code compiles; default is 5 minutes when `ANTHROPIC_TIMEOUT` is unset; any valid Go duration string in `ANTHROPIC_TIMEOUT` is accepted.

- [ ] 4. Add structured log line on timeout (depends on 3) — when the diagnose call returns a timeout error, log at `WARN` level: `{"msg":"llm_diagnose_timeout","ticket_id":"…","elapsed_ms":…}` — DoD: log line appears in unit test output when a mock timeout is injected.

- [ ] 5. Update ArgoCD Application manifest to document the `ANTHROPIC_TIMEOUT` env var (depends on 3) — add it as a commented-out example in the Application spec YAML — DoD: the env var is visible to ops without reading source code.

- [ ] 6. Run full unit and integration test suite (depends on 4) — DoD: `go test ./...` passes; LLMDiagnosis skill test exercises both the success path and the timeout path.

- [ ] 7. Update vendor directory if vendoring is used (depends on 6) — DoD: `vendor/` reflects v1.39.0; CI builds without network download.

## Tests

- [ ] T1. Unit test: mock Anthropic HTTP server that sleeps 6 minutes; assert `LLMDiagnosis` returns an error after 5 minutes (default timeout) and logs the structured `WARN` line.
- [ ] T2. Unit test: set `ANTHROPIC_TIMEOUT=30s`; mock server sleeps 31 seconds; assert timeout fires at ~30 s.
- [ ] T3. Unit test: set `ANTHROPIC_TIMEOUT=invalid`; assert the skill falls back to the 5-minute default and logs a warning about the bad value.
- [ ] T4. Integration test: end-to-end alert with no matching builtin skill routes to `LLMDiagnosis`; mock returns a valid diagnosis within 10 s; ticket transitions to `diagnosed` state.
- [ ] T5. Circuit-breaker test: inject N consecutive LLMDiagnosis timeouts; assert skill is auto-disabled after the threshold is reached.

## Rollback

1. Revert `go.mod`/`go.sum` to the previous SDK version.
2. Remove the `http.Client` timeout block from `LLMDiagnosis`.
3. Remove the `ANTHROPIC_TIMEOUT` env var from the Application manifest.
4. Run `go build ./...` and `go test ./...`.
5. Re-deploy via ArgoCD sync to the previous image tag.
6. Note: a rollback re-introduces the indefinite-hang risk; monitor for stuck tickets after rollback.
