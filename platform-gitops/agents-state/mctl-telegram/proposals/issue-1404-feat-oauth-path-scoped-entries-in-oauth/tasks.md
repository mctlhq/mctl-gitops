# Tasks: issue-1404-feat-oauth-path-scoped-entries-in-oauth

- [ ] 1. Add `allowEntry` and `parseAllowEntry` to `internal/oauth/cimd/cimd.go`, and route `ParseAllowedHosts` through it. Keep the signature and the `[]string` return. — DoD: host-only and `.suffix` behaviour is unchanged (the existing `TestParseAllowedHosts` cases still pass, except that `a.com/x` now fails because it lacks a trailing `/`). `host/a/b/` is accepted. The new refusals (no trailing `/`, `//`, `.`/`..`, `%`, `?`, `#`, `@`, `\`, port, suffix with path, prefix `/`) return errors prefixed `OAUTH_CIMD_ALLOWED_HOSTS:` that name the entry.
- [ ] 2. Change `Resolver.allowed` to `[]allowEntry`, and make `NewResolver` parse `Options.AllowedHosts` with `parseAllowEntry`, skipping invalid entries (depends on 1). — DoD: builds; existing resolver tests pass.
- [ ] 3. Replace `hostAllowed` with `match(u *url.URL) (string, bool)`. Host-level entries are checked first. Path entries need an equal host, an escaped path free of `%2f`/`%5c`/`%25`, and a `HasPrefix` on `u.EscapedPath()` (depends on 2). — DoD: `Resolve` and `fetchKeys` (`assertion.go`) both use `match`, the allowlist check still runs before cache and network, and a miss returns an error wrapping `ErrNotAllowed` with the path-only detail when it applies.
- [ ] 4. Add `AllowEntry string` to `cimd.Document`, set it in `Resolve` on fresh and cached results, and log `"oauth: cimd client admitted"` with `client_id` and `allow_entry` at INFO on the authorize path in `internal/oauth/cimd_client.go` (depends on 3). — DoD: no document body, redirect URI or client name appears in the log, and the refusal log via `cimdFailure` carries the wrapped detail.
- [ ] 5. Update the `OAUTHCIMDAllowedHosts` comment in `internal/config/config.go`. — DoD: the comment mentions the `host/path-prefix/` form.
- [ ] 6. Update the docs in the same PR: `SECURITY.md`, `.env.example`, `README.md`, `docs/runbooks/admitting-an-agent-platform.md` (step 2 multi-tenant variant, section 5 rollback), and `docs/platforms/compatibility.md` (Hermes row note) (depends on 3). — DoD: `go test ./docs/...` passes, and the docs state that an admitted pod without an `MCP_CLIENT_PROFILES` record still gets the default scope surface.
- [ ] 7. Run `go fmt`, `go vet`, `golangci-lint run` and `go test ./...` (depends on 1-6). — DoD: all clean.

## Tests

Use synthetic hosts only, such as `pods.example.test` with pods `pod-a` and `pod-b`, and no real tenant names.

- [ ] T1. `TestParseAllowedHosts`, extended. Accepted: `pods.example.test/oauth/mcp/clients/pod-a/` and `Pods.Example.Test/x/`, where the host is lowercased and the path is preserved. Refused: `pods.example.test/x`, `pods.example.test/`, `pods.example.test//x/`, `pods.example.test/a/../b/`, `pods.example.test/./a/`, `pods.example.test/a%2fb/`, `pods.example.test/%2e%2e/`, `pods.example.test:443/a/`, `user@pods.example.test/a/`, `pods.example.test/a/?q/`, `pods.example.test/a/#f/`, `.example.test/a/`, `1.2.3.4/a/`.
- [ ] T2. `TestPathScopedMatch` (table test on `Resolve` with the fixture transport, or on `match` directly). Allowed entry `pods.example.test/oauth/mcp/clients/pod-a/`:
  - hit on `https://pods.example.test/oauth/mcp/clients/pod-a/server.json`
  - hit with an upper-case host and with `:443`
  - refused for sibling `/pod-b/server.json`
  - refused for `/pod-ab/server.json` (segment boundary)
  - refused for `/oauth/mcp/clients/pod-a` (no trailing segment, path shorter than the prefix)
  - refused for `/oauth/mcp/clients/pod-a%2fserver.json`, `/oauth/mcp/clients/pod-a/%252e%252e/pod-b/x.json` and `/oauth/mcp/clients/pod-a/..%2fpod-b/x.json`
  - refused for `/OAUTH/mcp/clients/pod-a/x.json` (the path is case-sensitive)
  - refused for userinfo, query and fragment, through `parseCIMDURL`
  - refused for `https://pods.example.test/other.json`, because the host is not admitted at host level
  - every refusal satisfies `errors.Is(err, ErrNotAllowed)` (or the `parseCIMDURL` invalid error for malformed URLs) with zero fixture hits.
- [ ] T3. `TestHostEntryAndPathEntryCoexist`: with `pods.example.test` and a path entry both listed, every path is admitted, and `AllowEntry` reports the host entry.
- [ ] T4. `TestJWKSURIUnderPathScope`: a `private_key_jwt` document for pod-a whose `jwks_uri` is under `/pod-b/` is refused with `ErrNotAllowed`, and one under `/pod-a/` succeeds.
- [ ] T5. Server-level test in `internal/oauth/cimd_client_test.go`, using a real `cimd.NewResolver` with a `roundTripFunc` transport that serves pod-a's document. `/oauth/authorize` accepts pod-a. Pod-b on the same host is refused with `errCIMDRefused`, the WARN log contains `cimd: host is not allowed`, and the transport sees no request for pod-b.
- [ ] T6. Server-level token test: complete an authorization_code grant for pod-a, then swap the server's resolver for one built without the pod-a entry (a test-only wrapper that delegates to a swappable `*cimd.Resolver`). The refresh_token grant is refused before the token lookup. The authorization_code grant is also refused after removal.
- [ ] T7. `internal/config/config_cimd_test.go`: `OAUTH_CIMD_ALLOWED_HOSTS=platform.example.test,pods.example.test/oauth/mcp/clients/pod-a/` loads, and `pods.example.test/oauth/mcp/clients/pod-a` (no trailing `/`) is a startup error naming the variable.
- [ ] T8. Mutation check, recorded in the PR description: temporarily make `match` compare the host only for path entries, and confirm T2's sibling-pod case and T5 fail. Then restore the matcher.
- [ ] T9. Assert the log output with an `slog` handler capturing records: the admitted record has `allow_entry` and has no `redirect_uris` or `client_name`.

## Rollback

- Code: revert the PR and release the previous tag. Host-only lists keep working on both versions. A deployment that already uses a path entry fails to start on the old version (`"... is not a host name or .suffix"`), so revert the gitops entry first or together with the image rollback.
- Configuration: removing the path entry from `OAUTH_CIMD_ALLOWED_HOSTS` in `platform-gitops/services/labs/mctl-telegram/values.yaml` refuses that tenant's new authorizations and cuts off its refresh families at the next grant, because CIMD clients are re-resolved at both token grants. Turning `OAUTH_CIMD_ACCEPT` off is not the lever for this, as `SECURITY.md` already states.
