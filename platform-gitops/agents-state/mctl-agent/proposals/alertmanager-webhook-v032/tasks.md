# Tasks: alertmanager-webhook-v032

- [ ] 1. **Audit the current webhook handler and struct** — Locate the `POST /api/v1/alerts` handler and the AlertManager payload struct. Document every field currently parsed and compare against the v0.32.x schema. DoD: A comment in the PR listing the delta (fields added, fields changed, fields removed) between the current struct and v0.32.x.

- [ ] 2. **Add version annotation to the webhook struct** (depends on 1) — Insert a comment on the struct type citing `AlertManager v0.32.x` and the date validated. DoD: The struct declaration includes the version comment; it appears in `go doc`.

- [ ] 3. **Implement unknown-field warning logger** (depends on 1) — Add the two-pass JSON deserialisation approach described in `design.md`. DoD: A test with an unknown field in the payload produces a `slog` WARNING entry with the unknown key name and returns HTTP 200.

- [ ] 4. **Fix silence matcher struct for v0.32.x** (depends on 1) — If the silence `matchers` field is used, update from `[]Matcher` to `[][]Matcher` and add the flattening shim. DoD: Compiles cleanly; existing silence-related tests pass; new test with a multiple-matcher-set silence passes.

- [ ] 5. **Add startup schema-version log** (depends on 2) — Emit `slog.Info("alertmanager webhook handler ready", "alertmanager_schema_version", "v0.32")` in the handler initialisation. DoD: The log line appears in the service startup output in tests.

- [ ] 6. **Write table-driven integration test fixtures** (depends on 3, 4) — Add four fixtures as described in `design.md` (v0.31.x baseline, v0.32.x template annotation, v0.32.x multiple-matcher silence, unknown top-level field). DoD: All four test cases pass; test coverage of the webhook handler increases.

- [ ] 7. **Run full test suite** (depends on 6) — `go test ./...` with `-race`. DoD: All tests pass; no races detected; test coverage of `POST /api/v1/alerts` handler ≥ 80%.

- [ ] 8. **Deploy to staging and run end-to-end smoke test** (depends on 7) — Deploy the updated handler; send each of the four fixture payloads to the staging endpoint. DoD: All four payloads are accepted (HTTP 200); tickets are created for firing alerts; no ERROR or PANIC entries in logs.

- [ ] 9. **Deploy to production** (depends on 8) — Update the ArgoCD `Application` image tag. DoD: ArgoCD reports `Synced` and `Healthy`; the startup log includes `alertmanager_schema_version=v0.32`; no increase in 4xx or 5xx rates on `/api/v1/alerts` for 30 minutes post-deploy.

## Tests

- [ ] T1. **v0.31.x regression**: a canonical pre-v0.32 payload is parsed correctly and produces the correct internal ticket fields.
- [ ] T2. **v0.32.x template annotation**: a payload where `alerts[0].annotations.description` contains a template-expanded string (e.g. `"Pod {{ $labels.pod }} is crashing"`) is parsed without error.
- [ ] T3. **v0.32.x multiple-matcher silence**: a payload where the silence `matchers` field is `[[{name:"alertname", value:"PodCrashLooping"}]]` is parsed and the silence is applied correctly.
- [ ] T4. **Unknown field warning**: a payload with an extra top-level key `"futureField": "x"` returns HTTP 200 and a `slog` WARNING is emitted (not a 400).
- [ ] T5. **Invalid JSON**: a non-JSON body returns HTTP 400 with a structured error response (regression test for existing behaviour).

## Rollback
1. Revert the ArgoCD `Application` image tag to the prior version.
2. If the platform has already upgraded to AlertManager v0.32.x, the rolled-back handler may misparse payloads — monitor error rates on `/api/v1/alerts` and escalate to the on-call engineer.
3. The safest rollback path is a fast-forward fix, not a revert; keep the prior image available for at most 1 hour.
