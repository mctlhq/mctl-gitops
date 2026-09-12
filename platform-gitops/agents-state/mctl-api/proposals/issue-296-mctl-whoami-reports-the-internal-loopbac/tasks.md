# Tasks: issue-296-mctl-whoami-reports-the-internal-loopbac

- [ ] 1. Add a `publicURL` field to `Server` in `internal/mcp/server.go` and set
      it in `NewServer` to the trimmed `apiURL` — DoD: field documented with a
      comment distinguishing "upstream base (loopback by design)" from
      "caller-facing base URL"; `go build ./...` passes; existing
      `TestNewServer` / `TestNewServer_TrimsTrailingSlash`
      (`internal/mcp/server_test.go:125-143`) still pass unchanged.
- [ ] 2. Add `isLoopbackURL(raw string) bool` to `internal/mcp/server.go`
      (depends on 1) — DoD: parses with `net/url`, returns true for host
      `localhost` (any case) and for any `net.ParseIP(host).IsLoopback()`
      (`127.0.0.1`, `127.0.0.53`, `::1`), false for `https://api.mctl.ai` and
      for unparseable input; covered by T3.
- [ ] 3. Add `NewInProcessServer(port, publicURL string) *Server` to
      `internal/mcp/server.go` (depends on 1) — DoD: delegates to
      `NewServer("http://localhost:"+port, "")`, sets `publicURL` trimmed of a
      trailing slash, and carries the comment explaining why the upstream stays
      loopback (mirrors the note at `cmd/api/main.go:304-306`).
- [ ] 4. Rewire `cmd/api/main.go:307` to
      `mcpSrv := mctlmcp.NewInProcessServer(cfg.Port, cfg.SelfURL)` (depends on
      3) — DoD: no other change in `main.go`; `cfg.SelfURL` is the same value
      already passed to `auth.NewOAuthServer` at `:117`; `go build ./...` and
      `go vet ./...` clean.
- [ ] 5. Rewrite the `toolWhoami` message in `internal/mcp/server.go:212-213`
      (depends on 2, 3) — DoD: builds the identity block byte-identically to
      today (`User:`/`Admin:`/`Teams:`/`Accessible namespaces:`, same order and
      spacing) and prefixes `Authenticated to <displayURL()>\n\n` only when
      `displayURL()` is non-empty; `s.apiURL` no longer appears anywhere in the
      handler's success path.
- [ ] 6. Add `redactUpstream(err error) string` and use it in `toolWhoami`'s
      failure branch (depends on 5) — DoD: returns `err.Error()` unchanged when
      `s.apiURL == ""`, otherwise replaces every occurrence of `s.apiURL` with
      `the mctl API`; the branch also emits `slog.Error("whoami upstream call
      failed", "error", err)` so operators keep the full detail; covered by T2
      and T4.
- [ ] 7. Review the `mctl_whoami` tool description
      (`internal/mcp/server.go:191-195`) for wording that promises a URL
      (depends on 5) — DoD: description matches the new behaviour or is left
      unchanged with a note in the PR why; no other tool description touched.
- [ ] 8. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, `go test ./...`
      (depends on 1-7) — DoD: all clean; tool count assertions
      (`TestNewMCPServer_ToolCount`, the 74-tool check at
      `internal/mcp/server_test.go:174`) and
      `internal/mcp/stateless_test.go` unaffected.

## Tests

New file `internal/mcp/whoami_test.go` (package `mcp`):

- [ ] T1. **No loopback through the production construction path, any port.**
      Start an `httptest.NewServer` that answers `GET /api/v1/whoami` with
      `{"id":"mashkovd","groups":["admins","ovk"],"isAdmin":true,"namespaces":["admins","ovk"]}`,
      take its listener port, build the server with
      `NewInProcessServer(port, "https://api.mctl.ai")` — the same constructor
      `cmd/api/main.go` uses — and drive `tools/call` for `mctl_whoami` through
      `srv.NewMCPServer().HandleMessage(...)`, i.e. the real MCP layer, not the
      handler closure. Assert the rendered text contains none of `localhost`,
      `127.0.0.1`, `::1`, contains `Authenticated to https://api.mctl.ai`, and
      contains `User: mashkovd`, `Admin: true`, `Teams: [admins ovk]`,
      `Accessible namespaces: [admins ovk]`. Table-drive the port (the ephemeral
      httptest port plus an explicitly constructed second instance) so the
      assertion holds "under any port configuration".
      **Mutation check (record in the test's doc comment and verify by hand
      before merge):** putting `s.apiURL` back into the message must make T1
      fail on the `localhost` assertion.
- [ ] T2. **Error path leaks nothing.** Build `NewInProcessServer` against a port
      with no listener (start an httptest server, close it, reuse its port) and
      assert the `tools/call` result is an error result whose text contains no
      `localhost`, no `127.0.0.1`, no `::1`, and no `http://` upstream URL, while
      still saying it failed to get the identity.
- [ ] T3. **`isLoopbackURL` unit table.** `http://localhost:8080`,
      `http://LOCALHOST:9999`, `http://127.0.0.1:8080`, `http://127.0.0.53`,
      `http://[::1]:8080` → true; `https://api.mctl.ai`, `https://mcp.mctl.ai/mcp`,
      `""`, `":://bad"` → false.
- [ ] T4. **Fallback rendering.** With `NewInProcessServer(port, "")` and with
      `NewInProcessServer(port, "http://localhost:8080")`, the response omits the
      `Authenticated to` line entirely (no leading blank line) and still carries
      the four identity fields verbatim.
- [ ] T5. **Stdio path unchanged.** `NewServer("https://api.mctl.ai/", "tok")`
      renders `Authenticated to https://api.mctl.ai` (trailing slash trimmed),
      pinning that `cmd/mcp/main.go`'s only correct configuration does not
      regress.
- [ ] T6. **Suite regression sweep.** `go test ./...` — in particular
      `internal/mcp/server_test.go` and `internal/mcp/stateless_test.go` pass
      untouched, confirming no tool-count or transport change.

## Rollback

Single-service, code-only change with no migration and no gitops/values
dependency, so rollback is a normal image revert:

1. `mctl_get_service_config` for the `mctl-api` service to read the current
   image tag, then `mctl_rollback_service` to the previous tag (or revert the
   PR on `main` and let the release pipeline ship the next tag).
2. Nothing else to undo: no schema, no secrets, no Helm values, no ArgoCD
   application change. `SELF_URL` handling is untouched — the OAuth issuer keeps
   using `cfg.SelfURL` exactly as before, so a rollback cannot strand tokens.
3. Blast radius if the change is wrong: the first line of the `mctl_whoami`
   response only. Every other tool, the REST API, and the MCP transport are
   untouched, so a bad render is cosmetic and can wait for the next deploy
   rather than forcing an emergency rollback.
