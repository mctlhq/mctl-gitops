# Tasks: alertmanager-webhook-audit

- [ ] 1. Capture the AlertManager v0.32.0 webhook payload schema — DoD: a JSON sample file is
  committed at `testdata/alertmanager_v032_payload.json`; the sample is sourced from the
  AlertManager v0.32.0 source (`prometheus/alertmanager` tag `v0.32.0`) or official
  documentation and includes at least one alert with `silenceAnnotations` and `matcherSets`
  populated; a comment in the file records the source URL and tag.

- [ ] 2. Audit and update the webhook parse struct (depends on 1) — DoD: the Go struct(s) in
  `internal/webhook/` (or equivalent) declare all new optional v0.32.0 fields (`SilenceAnnotations`,
  `MatcherSets`) with `json:",omitempty"` tags; existing fields and their tags are unchanged;
  the package compiles without errors; `go vet ./...` is clean.

- [ ] 3. Implement two-pass unknown-field logging and silence-annotation persistence (depends on 2)
  — DoD: the handler uses a two-pass JSON decode in production (permissive) and
  `DisallowUnknownFields` in test mode; unknown top-level keys produce a `slog.Warn` log entry
  and do not cause a 4xx or 5xx response; when `SilenceAnnotations` is non-empty, it is stored
  under the key `silence_annotations` in the ticket's evidence JSON blob; unit tests covering all
  three behaviours are green.

- [ ] 4. Add the `alertmanager_payload_parse_errors_total` Prometheus counter (depends on 2) — DoD:
  the counter is registered during handler init with a `reason` label; it is incremented before
  every HTTP 400 response from the alerts handler; the metric is visible at `/metrics`; a unit
  test asserts the counter value increments on a deliberately malformed payload.

- [ ] 5. Run CI integration smoke test with a v0.32.0 sample payload (depends on 3, 4) — DoD: a
  CI job (or existing integration-test target) sends the content of
  `testdata/alertmanager_v032_payload.json` to the running service via `POST /api/v1/alerts` and
  asserts HTTP 200 is returned and a ticket record is created in SQLite; the job runs on every PR
  that touches `internal/webhook/`.

## Tests

- [ ] T1. Existing alert routing tests pass without modification — run
  `go test ./internal/webhook/... -v` and confirm all previously-passing cases still pass; no
  routed alert type (PodCrashLooping, KubePodCrashLooping, etc.) is broken.
- [ ] T2. v0.32.0 payload parses without error and routes correctly — table-driven test case using
  `testdata/alertmanager_v032_payload.json`; assert HTTP 200, correct skill selected, ticket
  created with `silence_annotations` evidence populated.
- [ ] T3. Unknown fields produce a WARN log entry, not a 5xx response — inject a payload with a
  synthetic unknown top-level field (e.g., `"futureField": "x"`); assert HTTP 200 is returned and
  the `slog.Warn` message is emitted; assert `alertmanager_payload_parse_errors_total` is NOT
  incremented (unknown fields are not parse errors).

## Rollback

1. Revert the struct additions in `internal/webhook/` and the two-pass decoder logic.
2. Remove or comment out the `alertmanager_payload_parse_errors_total` counter registration if
   it was newly added (to avoid a metric registration panic on restart with the old binary).
3. Open and merge the revert PR — CI must be green before merge.
4. AlertManager v0.31.x and v0.32.x are wire-compatible for all fields that predate v0.32.0;
   reverting the struct has no impact on parsing those shared fields.
5. If AlertManager has already been upgraded to v0.32.0 in the cluster at the time of rollback,
   unknown fields will again be silently dropped (the pre-patch behaviour) — this is acceptable
   as a temporary state while a corrected patch is prepared.
