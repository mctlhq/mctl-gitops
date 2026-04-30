# Tasks: mcp-command-injection-hardening

- [ ] 1. Define `mcpEnvelope` struct and compile-time tool-name allowlist in
  `internal/mcp/validate.go` — DoD: file compiles; allowlist contains exactly the 6
  registered tool names as string constants; a `len(allowlist) == 0` guard calls
  `log.Fatal` with a descriptive message.

- [ ] 2. Implement body-size cap and JSON parse step in `NewMCPValidationMiddleware`
  (depends on 1) — DoD: middleware wraps body with `http.MaxBytesReader(64 KB)`;
  malformed JSON returns HTTP 400 + JSON-RPC `-32700`; oversized body returns HTTP 413;
  all validated by unit tests.

- [ ] 3. Implement tool-name allowlist check in middleware (depends on 2) — DoD:
  any `method` not in the allowlist returns HTTP 400 + JSON-RPC `-32601`; a `slog.Warn`
  entry is emitted with `request_id`, `remote_addr`, `rejected_field="method"`,
  `reason="method not allowed"`; covered by table-driven unit tests.

- [ ] 4. Implement param field length check (shallow, 3-level depth cap) in middleware
  (depends on 3) — DoD: any top-level string param exceeding 8 KB returns HTTP 400 +
  JSON-RPC `-32602` with the offending field name logged; depth cap prevents unbounded
  recursion; covered by unit tests including a deeply nested object fixture.

- [ ] 5. Re-serialise sanitised envelope and replace `r.Body` (depends on 4) — DoD:
  downstream handler receives a readable `io.NopCloser` body with the validated envelope;
  end-to-end test confirms a compliant request is processed correctly by the real MCP
  handler.

- [ ] 6. Register `http.TimeoutHandler(30s)` around the `POST /mcp` route in `main.go` or
  the router setup (depends on 5) — DoD: a request that stalls returns HTTP 408 within
  31 s in an integration test using a slow-handler stub.

- [ ] 7. Add startup guard in `main.go` to call `NewMCPValidationMiddleware` and assert
  the returned error is nil, or `log.Fatal` on empty allowlist (depends on 1) — DoD:
  running the binary with a modified empty allowlist exits non-zero at startup with a
  `FATAL` log line referencing the missing configuration.

- [ ] 8. Update `POST /mcp` section in service API documentation / inline godoc (depends
  on 6) — DoD: godoc comment on `NewMCPValidationMiddleware` lists the 64 KB body cap,
  8 KB param-string cap, allowlisted method names, and all rejection HTTP status codes.

## Tests

- [ ] T1. Unit: `TestMCPValidation_BodyTooLarge` — POST body > 64 KB returns 413.
- [ ] T2. Unit: `TestMCPValidation_MalformedJSON` — non-JSON body returns 400 +
  JSON-RPC `-32700`.
- [ ] T3. Unit: `TestMCPValidation_UnknownMethod` — table-driven test over 10 crafted
  method names not in allowlist; each returns 400 + `-32601`.
- [ ] T4. Unit: `TestMCPValidation_KnownMethods` — each of the 6 registered tool names
  passes allowlist check and reaches the next handler.
- [ ] T5. Unit: `TestMCPValidation_OversizedParam` — param string of 8 KB + 1 byte
  returns 400 + `-32602`; param string of exactly 8 KB passes.
- [ ] T6. Unit: `TestMCPValidation_DeeplyNestedParams` — object nested 4 levels deep does
  not cause a stack overflow; validation terminates at depth 3.
- [ ] T7. Unit: `TestMCPValidation_WarnLog` — rejected request emits a `slog.Warn` record
  containing all required fields (`request_id`, `remote_addr`, `rejected_field`, `reason`).
- [ ] T8. Integration: `TestMCPTimeout` — handler stub that sleeps 35 s; middleware +
  `TimeoutHandler` returns HTTP 408 within 31 s.
- [ ] T9. Integration: `TestMCPValidation_CompliantEndToEnd` — compliant tool call with
  all valid fields passes through to MCP handler and returns a successful JSON-RPC response.

## Rollback
1. The validation middleware is a chi middleware in the handler chain. To roll back, remove
   the `Use(NewMCPValidationMiddleware(...))` call in the router setup and redeploy via
   ArgoCD. No database migration is involved.
2. If the `http.TimeoutHandler` causes issues independently, it can be removed from the
   `POST /mcp` route in the same change without affecting the validation logic.
3. Both changes are in a single commit tagged `mcp-injection-hardening`; reverting that
   commit and triggering an ArgoCD sync is sufficient for a full rollback.
