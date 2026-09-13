# Tasks: issue-605-mcpprobe-four-p3s-left-open-when-604-mer

- [ ] 1. Re-verify finding 1 at HEAD: read `splitChallengeParts` /
      `unquoteChallengeValue` in `internal/mcpprobe/oauthprobe.go` and run
      `go test ./internal/mcpprobe/ -run TestParseChallengeParams -count=1`.
      — DoD: the escape-aware behaviour is confirmed present and green; the PR
      body states that finding 1 needed no production change and links the
      commit that introduced the escape handling.
- [ ] 2. Add the missing grammar case to
      `TestParseChallengeParams_HonoursQuotedStringEscapes`
      (`internal/mcpprobe/oauthprobe_test.go`): an escaped quote inside the
      `resource_metadata` value, i.e. the escape in the parameter *after* the
      first quoted value (depends on 1). — DoD: the case asserts both `realm`
      and `resource_metadata` come back with escapes resolved and boundaries
      intact; the table still asserts exact map length; suite green.
- [ ] 3. Extend `fakeServer` in `internal/mcpprobe/fake_test.go` with a
      `mintSessionOn map[string]bool` knob keyed by JSON-RPC method, setting
      `mcp.HeaderSessionID` to `fakeSessionID` on that method's response.
      Leave the existing `mintSession` boolean (legacy `initialize`) untouched.
      — DoD: no existing test changes behaviour; the knob is documented as
      modelling a non-conforming server and defaults off.
- [ ] 4. Add modern-path session tests to `internal/mcpprobe/modern_test.go`,
      one minting on `tools/list` and one on `tools/call` (depends on 3).
      — DoD: each asserts `Session.HeaderPresent == true` and
      `Session.IDLength == len(fakeSessionID)`; each fails when the matching
      `noteSession` call in `internal/mcpprobe/modern.go` is deleted (verify by
      temporarily removing the call, then restoring it).
- [ ] 5. Assert the value is still withheld in the new modern cases: marshal
      the report and check it does not contain `fakeSessionID` (depends on 4).
      — DoD: mirrors `TestReport_RecordsSessionShapeWithoutTheValue`; a report
      that observed a session on a later modern response leaks nothing.
- [ ] 6. Complete the enumeration in the `Report` doc comment in
      `internal/mcpprobe/report.go`: name `Server.Name`, `Server.Version`,
      `Server.SupportedVersions`, `Tools[].Name`,
      `OAuth.AuthorizationServer.Issuer`,
      `OAuth.AuthorizationServer.TokenEndpointAuthMethods`,
      `OAuth.Unauthenticated.Realm`, `OAuth.Unauthenticated.ErrorCode`.
      — DoD: the comment's "only strings that did not originate in this
      package" claim is true by inspection of the current type; no code change.
- [ ] 7. Add `TestReportStringFieldsHaveADeclaredOrigin` to
      `internal/mcpprobe/report_test.go`: reflect-walk `Report{}`, collect every
      `string` / `[]string` / named-string field path, and compare against an
      explicit origin table (`package`, `caller`, `server`) (depends on 6).
      — DoD: an unclassified field fails with a message naming the field and
      instructing the author to classify it and, if server-origin, extend the
      `Report` comment; the table's server-origin set matches task 6's list
      exactly.
- [ ] 8. Add `clientDisplayName(ctx, clientID) string` to
      `internal/oauth/server.go` beside `validateClient`: store
      (`s.store.GetClientReg`) first, then the in-memory `s.clients` map under
      `s.mu`, "" on miss, errors swallowed. — DoD: helper compiles, is
      documented with why a miss must not fail a token exchange, and mirrors
      `validateClient`'s lookup order.
- [ ] 9. Replace the inline `GetClientReg` block in the authorization_code
      branch of the token handler (`internal/oauth/server.go`, around line
      2023) with a call to `clientDisplayName` (depends on 8). — DoD: the
      `db.RefreshToken` passed to `issueRefreshToken` carries the resolved name;
      nothing else in the token or refresh path changes.
- [ ] 10. Parameterize the `internal/oauth` test helpers by client:
      `stateFromAuthorize` / `obtainAuthorizationCode`
      (`internal/oauth/server_test.go`) and `authCodeTokens`
      (`internal/oauth/refresh_test.go`) gain `clientID` / `redirectURI`
      arguments or `…For(...)` variants. — DoD: existing call sites keep their
      current behaviour via one-line wrappers passing `claude.ai` /
      `https://claude.ai/cb`; `go test ./internal/oauth/` green.
- [ ] 11. Run `go fmt ./...`, `go vet ./...` and `golangci-lint run` over the
      touched packages (depends on 2, 5, 7, 9, 10). — DoD: clean; commits follow
      conventional-commit prefixes and the merge-commit policy in
      `.claude/CLAUDE.md`.

## Tests

- [ ] T1. `TestParseChallengeParams_HonoursQuotedStringEscapes` gains the
      escape-in-`resource_metadata` case and stays green (task 2).
- [ ] T2. `TestModernRun_ObservesASessionMintedOnToolsList` — the modern run
      against a fixture minting only on `tools/list` records
      `HeaderPresent == true` and `IDLength == len(fakeSessionID)` (task 4).
- [ ] T3. `TestModernRun_ObservesASessionMintedOnToolsCall` — same for the
      `tools/call` response (task 4).
- [ ] T4. Mutation check: deleting `noteSession` from `probeToolsList` fails
      T2 and deleting it from `probeReadOnlyCall` fails T3; restore both
      afterwards (task 4).
- [ ] T5. The new modern cases assert the serialized report never contains
      `fakeSessionID` (task 5).
- [ ] T6. `TestReportStringFieldsHaveADeclaredOrigin` fails when a new string
      field is added to any struct in the `Report` tree and passes on the
      current type (task 7).
- [ ] T7. `TestPreregisteredClient_RefreshTokenCarriesClientName` in
      `internal/oauth/preregistered_test.go`: with `withPortalClient`, complete
      an authorization_code exchange as `portal-client`, `LookupRefreshToken`
      the returned refresh token, assert `ClientName == "Example Portal"`
      (tasks 9, 10).
- [ ] T8. Regression: an implicit client (`claude.ai`, no registration in
      store or map) still records an empty `ClientName` and the exchange
      succeeds — the miss path must stay non-fatal (task 9).
- [ ] T9. Full suite: `go test ./internal/mcpprobe/ ./internal/oauth/
      ./internal/db/ -count=1` green.

## Rollback

Each finding is an independent commit, so rollback is per-finding.

- Findings 1–3 (`internal/mcpprobe`) are comment- and test-only plus a
  test-fixture knob; `git revert` of those commits restores the previous state
  with zero runtime effect — no deployed binary behaviour changes, and
  `ReportSchema` is untouched, so previously written reports stay comparable.
- Finding 4 (`internal/oauth`) is one helper plus one call-site substitution.
  Reverting restores the store-only lookup; refresh-token rows written while the
  change was live keep their populated `client_name`, which is a superset of the
  old blank value and is read only for display, so no reader breaks either way.
  There is no migration to undo.
- If the display-name change were ever suspected in a token-exchange failure,
  the fastest mitigation is reverting commit 9 alone (leaving the helper
  unused), since the helper never returns an error and cannot deny a token.
