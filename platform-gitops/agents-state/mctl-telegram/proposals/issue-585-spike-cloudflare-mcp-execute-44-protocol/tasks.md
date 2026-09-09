# Tasks: issue-585-spike-cloudflare-mcp-execute-44-protocol

- [ ] 1. Add `internal/mcpprobe` and `cmd/mcpprobe` without touching `cmd/canary` or the load generator — DoD: standalone probe builds with `go build ./...`; no production credential, token, callback URI or Cloudflare hostname is hard-coded.

- [ ] 2. Implement explicit protocol modes — DoD: `modern` and `legacy` are separate code paths/results. `modern` defaults to `2026-07-28`; legacy version is operator-configurable. A failed modern run never silently falls back and reports itself as modern.

- [ ] 3. Implement modern `2026-07-28` request construction — DoD: modern requests begin with `server/discover`, carry per-request `_meta` (`protocolVersion`, `clientInfo`, `clientCapabilities`), `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` when applicable. No `initialize` bootstrap and no `Mcp-Session-Id` is sent.

- [ ] 4. Add modern removed-method/header negative probes — DoD: calling `initialize` in modern mode is recorded as a removed-method rejection; missing/mismatched `Mcp-Method` / `Mcp-Name` cases are exercised and recorded as protocol errors. Do not use header echoing as the success criterion.

- [ ] 5. Implement modern discovery/read-only call path — DoD: record `server/discover`, `tools/list`, supported protocol versions/server metadata where returned, then exactly one `tools/call` guarded by `readOnlyHint=true`. Default target is `get_my_send_status` when available. Any `Mcp-Session-Id` returned/required in modern mode is recorded as an observation and never logged by value.

- [ ] 6. Implement legacy initialize/session compatibility path — DoD: selected legacy version performs `initialize`, records server protocol version, session-id presence/length, and whether subsequent `tools/list` / read-only `tools/call` require that session id. Legacy results are labeled separately.

- [ ] 7. Add OAuth metadata/401 challenge probe — DoD: protected-resource and authorization-server metadata are collected; `WWW-Authenticate` / `resource_metadata` is classified on 401; reports contain no bearer/refresh token or authorization code. Record `token_endpoint_auth_methods_supported` so Cloudflare public-client compatibility can be assessed explicitly.

- [ ] 8. Define a structurally redacted `Report` — DoD: fields are limited to labels/provenance, protocol versions/modes, status/error codes, tool/method names, annotations, booleans, counts, timestamp/build/ref, and session-id presence/length. No arbitrary tool result body is serializable into the report.

- [ ] 9. Add three-row evidence model — DoD: output supports `in-process-current-main`, `direct-deployed`, and `cloudflare-portal`. CI produces only the in-process row; deployed/Portal rows are operator evidence and can be `PENDING-OPERATOR`. Each row records protocol mode/version and evidence timestamp/ref where known.

- [ ] 10. Add structured `OAUTH_PREREGISTERED_CLIENTS` configuration — DoD: `internal/config` parses JSON records containing `client_id` and exact `redirect_uris`; `cmd/server` passes those records through `oauth.Config` (or an explicit constructor option); `internal/oauth.New` seeds its private `s.clients` map with zero-`CreatedAt` static registrations alongside the built-in self-connect client. No client-secret field is added and `cmd/server` does not reach into OAuth internals. Unset means no behavior change.

- [ ] 11. Prove exact redirect matching — DoD: a configured public client using a synthetic callback such as `https://portal.example.test/servers-callback` is accepted with exact URI and rejected for path/query/port variants. The flow does not call `/oauth/register` and works with `AllowImplicitClient=false`.

- [ ] 12. Preserve the old implicit/DCR surface unchanged — DoD: do **not** add `OAUTH_EXTRA_IMPLICIT_HOSTS`; do not add the Portal callback to `OAUTH_ALLOWED_IMPLICIT_HOSTS`; existing replace semantics and DCR/implicit tests remain unchanged. Preferred Portal docs use pre-registration only.

- [ ] 13. Add Cloudflare public-client compatibility gate to docs/report — DoD: operator procedure verifies Cloudflare can use `token_endpoint_auth_method=none` + PKCE-S256. If Cloudflare requires a client secret/confidential auth method, report `BLOCKED` and open a separate security-reviewed child issue; do not implement confidential-client auth in this spike.

- [ ] 14. Write `docs/cloudflare-portal-compat.md` — DoD: document the actual callback shown by Cloudflare (never guess/bake it), `Require user auth=ON`, exact pre-registration, current public-client OAuth contract, DCR compatibility-only, CIMD target, three-row matrix, direct/Portal bounded operator commands, two-user identity check, and MTProto/Local Bridge ownership caveat.

- [ ] 15. Link measured evidence back to `mctlhq/.github#44` — DoD: issue comment includes the generated matrix/report and distinguishes CI/in-process evidence from deployed direct and Portal evidence.

## Tests

- [ ] T1. Modern request fixture follows the pinned `mcp-go v1.0.0` `2026-07-28` request shape and succeeds against a modern fake/server.
- [ ] T2. Modern `initialize` is exercised only as a negative removed-method test.
- [ ] T3. Missing/mismatched modern method/name headers are rejected and recorded correctly.
- [ ] T4. Legacy stateful fake mints `Mcp-Session-Id`; probe records and uses it only in legacy mode.
- [ ] T5. Read-only guard refuses `send_message` or any tool without `readOnlyHint=true` before issuing `tools/call`.
- [ ] T6. Redaction test proves serialized/logged output omits fixture bearer tokens, message bodies, chat titles, peer ids and full session ids.
- [ ] T7. In-process integration test mounts the real MCP handler/middleware wiring and produces an `in-process-current-main` result; it does not claim to be live `tg.mctl.ai` evidence.
- [ ] T8. Pre-registered public-client exact redirect positive/negative tests pass with `AllowImplicitClient=false` and without `/oauth/register`.
- [ ] T9. Existing PKCE, issuer/resource/audience, scope, protected-resource metadata and DCR/implicit-host regression tests pass unchanged.
- [ ] T10. Guard confirms no new HTTP+SSE endpoint, Roots, Sampling, MCP Logging, DCR dependency, confidential-client secret handling or Cloudflare production hostname is introduced.

## Rollback

The probe is standalone and the OAuth registration config is optional/in-memory. Stop running the probe and unset `OAUTH_PREREGISTERED_CLIENTS`; there is no schema or persisted state to unwind. Production canary/load behavior remains untouched.
