# Design: issue-605-mcpprobe-four-p3s-left-open-when-604-mer

## Current state

All paths below were read in the read-only clone at HEAD `29470b0`.

### 1. Challenge parsing — `internal/mcpprobe/oauthprobe.go`

`probeChallenge` (line 148) sends a deliberately unauthenticated
`tools/list`, requires a 401, and reads `WWW-Authenticate`. It then calls
`parseChallengeParams` (line 199), which splits the auth-param list with
`splitChallengeParts` (line 250) and unquotes each value with
`unquoteChallengeValue` (line 222). Two values reach the report:
`ChallengeProbe.Realm` and the `resource_metadata` pointer, the latter only as
the booleans `ResourceMetadataPresent` / `ResourceMetadataMatches`.

Contrary to the issue text, the splitter **already** honours escapes:

```go
case escaped:            current.WriteRune(r); escaped = false
case inQuotes && r == '\\': current.WriteRune(r); escaped = true
case r == '"':           inQuotes = !inQuotes; current.WriteRune(r)
case r == ',' && !inQuotes: parts = append(parts, current.String()); current.Reset()
```

and `unquoteChallengeValue` resolves `\"` and `\\`, returns bare tokens
untouched, and terminates at the closing delimiter. The behaviour is pinned by
`TestParseChallengeParams_HonoursQuotedStringEscapes`
(`internal/mcpprobe/oauthprobe_test.go`, line 205) with eight cases, including
the odd-number-of-escapes case that an escape-blind splitter actually breaks
on. `go test ./internal/mcpprobe/ -run TestParseChallengeParams` passes in the
clone. The one grammar shape the table does not carry is an escape appearing in
a parameter *after* the first quoted value — e.g. inside `resource_metadata` —
where a mis-split would corrupt the pointer rather than the realm.

### 2. Modern-path session observation — `internal/mcpprobe/modern.go`

`runModern` (line 23) calls `noteSession(r, discover)` after discovery
(line 42); `probeToolsList` (line 111) and `probeReadOnlyCall` (line 154) each
call it too, which is what widens "the modern path mints no session" from the
first response to the whole path. `noteSession` (line 186) records only
`Session.HeaderPresent` and `Session.IDLength`, never the value.

The fixture cannot currently exercise the widened observation. In
`internal/mcpprobe/fake_test.go`, `fakeServer.mintSession` (line 26) sets
`mcp.HeaderSessionID` **only** on the `mcp.MethodInitialize` branch (line 153),
i.e. the legacy lifecycle. `TestModernRun_UsesDiscoverAndNeverInitializes`
asserts `!report.Session.HeaderPresent` (modern_test.go line 44), but against a
fixture that never mints one anywhere on the modern path — so deleting the
`noteSession` calls in `probeToolsList` and `probeReadOnlyCall` leaves the
suite green. `TestReport_RecordsSessionShapeWithoutTheValue`
(report_test.go line 121) covers only the legacy run.

### 3. Report redaction comment — `internal/mcpprobe/report.go`

The doc comment on `Report` (lines 59–71) states the shape guarantee (no
`json.RawMessage`, `map[string]any`, `any` or `[]byte` anywhere in the tree),
then adds: "a handful of fields do carry server-chosen text — the server name
and version from discovery, tool names, the advertised token endpoint auth
methods … they are the only strings here that did not originate in this
package."

Walking the tree, the server-origin string fields are:

| Field | Named in comment |
| --- | --- |
| `ServerInfo.Name`, `ServerInfo.Version` | yes |
| `ServerInfo.SupportedVersions` | no |
| `ToolInfo.Name` | yes |
| `AuthServerProbe.TokenEndpointAuthMethods` | yes |
| `AuthServerProbe.Issuer` | no |
| `ChallengeProbe.Realm` | no |
| `ChallengeProbe.ErrorCode` | no |

The remaining strings are package constants or caller input: `Schema`,
`Source`, `Mode`, `ProtocolVersion`, `Summary`, `Reason`, `Step.Label`,
`Step.Method`, `Step.Tool` (from `Options.Tool`), `TargetHost` (from
`Options.URL`), `GitRef`. The structural half of the guarantee is enforced by
`TestReportCarriesNoOpenEndedFields` (report_test.go line 21), which walks the
tree by reflection and rejects open-ended types — but nothing enforces the
*enumeration* of server-origin strings, so the comment's "only" drifted.

### 4. Pre-registered client display name — `internal/oauth/server.go`

`New` seeds the in-memory `s.clients` map with the built-in connect client
(line 684) and every `cfg.PreregisteredClients` entry (line 701), each carrying
the operator's `ClientName` and a zero `CreatedAt` so the sweeper never evicts
them. These records are never written to the store.

In the authorization_code branch of the token handler (lines 2023–2035):

```go
var clientName string
if reg, regErr := s.store.GetClientReg(r.Context(), clientID); regErr == nil {
    clientName = reg.ClientName
}
refreshTok, err := s.issueRefreshToken(r.Context(), db.RefreshToken{ ... ClientName: clientName, ... })
```

A static client has no store row, so `GetClientReg` returns
`db.ErrOAuthNotFound` and the refresh-token record
(`db.RefreshToken.ClientName`, `internal/db/refresh_tokens.go` line 27, a
denormalized column) is written blank. Rotation carries the blank forward
verbatim (`rt.ClientName` at line 2245), so the value never recovers for the
life of the family. The precedent for the correct lookup order already exists
next door: `validateClient` (line 2803) tries the store first and falls back to
`s.clients` under `s.mu`, precisely so pre-registered clients are recognised
when `useDB` is true. `docs/cloudflare-portal-compat.md` line 104 documents
`OAUTH_PREREGISTERED_CLIENTS` carrying `client_name`, and
`internal/oauth/preregistered_test.go` already seeds a synthetic
`portal-client` / "Example Portal" record.

## Proposed solution

Four small, independent changes; none alters an on-the-wire contract.

**1. Record finding 1 as already fixed, and add the one missing case.**
No production code changes in `oauthprobe.go`. Add a case to
`TestParseChallengeParams_HonoursQuotedStringEscapes` in which the escape lives
in the *second* parameter, e.g.

```text
Bearer realm="mctl-telegram", resource_metadata="https://host/a\"b"
```

asserting that `resource_metadata` comes back with the escape resolved and that
`realm` is untouched. This closes the finding by pinning the half of the
grammar the current table does not reach, rather than by re-fixing solved code.
The implementer records in the PR body that the splitter was already
escape-aware at HEAD.

**2. Give the widened session observation a fixture that would mint.**
Extend `fakeServer` in `internal/mcpprobe/fake_test.go` with a knob that mints
`Mcp-Session-Id` on a *named* method's response, e.g.
`mintSessionOn map[string]bool` (keyed by the JSON-RPC method string), leaving
the existing `mintSession` boolean for the legacy `initialize` path so no
current test changes. Set the header in `ServeHTTP` just before
`writeRPCResult` for the matching method.

Then add two table-driven cases to `internal/mcpprobe/modern_test.go` — one
minting on `tools/list`, one on `tools/call` — each asserting
`report.Session.HeaderPresent` is true, `IDLength == len(fakeSessionID)`, and
that the serialized report does not contain `fakeSessionID` (reusing the
assertion style of `TestReport_RecordsSessionShapeWithoutTheValue`). Each case
fails if the corresponding `noteSession` call site in `modern.go` is removed,
which is exactly the property the issue says is missing. The existing
"modern mints no session" assertion stays as the negative half.

**3. Complete the enumeration and make it machine-checked.**
Rewrite the last paragraph of the `Report` doc comment to name all eight
server-origin fields (grouped: discovery identity and supported versions; tool
names; the authorization-server issuer and advertised token endpoint auth
methods; the challenge realm and error code). Then add
`TestReportStringFieldsHaveADeclaredOrigin` to
`internal/mcpprobe/report_test.go`: walk `reflect.TypeOf(Report{})` the same
way `TestReportCarriesNoOpenEndedFields` does, collect every field path whose
type is `string`, `[]string` or a named string type, and compare the set
against an explicit table in the test mapping each path to one of
`originPackage`, `originCaller`, `originServer`. An unknown path fails with a
message telling the author to classify the field and, if it is server-origin,
to add it to the comment. This converts the comment's exhaustiveness claim from
prose into something a compiler-visible change breaks — the same philosophy the
existing guard tests state.

**4. Resolve the display name through both client sources.**
Add a helper next to `validateClient` in `internal/oauth/server.go`:

```go
// clientDisplayName resolves the operator- or client-supplied display name for
// client_id, preferring a persisted registration and falling back to the
// in-memory map that holds the built-in connect client and every
// cfg.PreregisteredClients entry. A miss yields "": the name is cosmetic and
// must never fail a token exchange.
func (s *Server) clientDisplayName(ctx context.Context, clientID string) string
```

Order mirrors `validateClient`: store first (`s.store.GetClientReg`), then
`s.clients` under `s.mu`. Errors are swallowed, as today. Replace the inline
`GetClientReg` block at line 2023 with a call to it. Nothing else in the
refresh path changes; rotation keeps carrying `rt.ClientName` forward, which
now starts non-blank for static clients.

Test in `internal/oauth/preregistered_test.go`: drive an authorization_code
exchange as `portalClientID` (reusing `withPortalClient`), then
`store.LookupRefreshToken` the returned `refresh_token` and assert
`ClientName == "Example Portal"`. This needs a client-parameterized version of
`stateFromAuthorize` / `obtainAuthorizationCode` / `authCodeTokens`; the
preferred route is to add `client_id`/`redirect_uri` parameters to those
helpers (or thin `…For(clientID, redirectURI)` variants) so the existing
`claude.ai` callers stay one-line wrappers.

## Alternatives

- **Rewrite the challenge parser against a full RFC 7235 tokenizer.** Rejected:
  the current parser already satisfies the grammar for the shapes this probe
  reports, it is covered by an eight-case table, and a rewrite would risk a
  regression in a wrong-observation-sensitive path to fix a defect that no
  longer exists at HEAD.
- **Assert the widened session observation by inspecting call sites (e.g. an
  AST or source grep test).** Rejected: it pins the implementation rather than
  the behaviour, and this package has an explicit preference for structural,
  behaviour-level guards — `guard_test.go` says so where it replaces a source
  grep with a reflection walk over `Options`.
- **Drop the "they are the only strings here" sentence instead of completing
  the list.** This is the issue's own second option and is cheaper, but it
  trades an over-strong claim for a weaker guarantee at a point where the type
  is the whole redaction mechanism. Completing the list plus a guard keeps the
  strong claim and makes drift fail a test. Dropping the sentence remains the
  fallback if a reviewer rejects the guard's maintenance cost.
- **Persist pre-registered clients into the `oauth_client_registrations`
  table at boot** so `GetClientReg` finds them. Rejected: it would give static
  clients a `CreatedAt` and pull them into sweeper/cap accounting that `New`
  deliberately exempts (lines 690–707), and it turns a cosmetic fix into a
  storage-lifecycle change.
- **Fall back to `client_id` as the display name when no name is known.**
  Rejected: it would change the meaning of `ClientName` for implicit clients
  (`claude.ai` et al.) that currently record a blank, which is a visible
  behaviour change outside this issue's scope.

## Platform impact

- **Migrations:** none. No schema, no `ReportSchema` bump (`mctl-mcpprobe/1`
  stays), no new config keys.
- **Backward compatibility:** the `mcpprobe` changes are comment and test only,
  plus a test-fixture knob; the report JSON shape is unchanged. The `oauth`
  change alters one previously-blank string on newly issued refresh-token rows
  for static clients only. Existing rows keep their blank value; nothing reads
  `ClientName` for an authorization decision (`grep` finds it used only for
  storage and display), so no policy turns on it.
- **Resource impact:** one extra map lookup under an already-held mutex per
  authorization_code exchange, only when the store lookup misses. Negligible.
- **Risks + mitigations:**
  - *Risk:* the new origin-table guard test becomes a maintenance tax on every
    added string field. *Mitigation:* the failure message states exactly what to
    do (classify the field; if server-origin, extend the comment), and the tree
    is small and deliberately frozen.
  - *Risk:* generalizing the shared `internal/oauth` test helpers touches many
    existing tests. *Mitigation:* keep the current signatures as wrappers that
    pass `claude.ai`; no existing call site changes.
  - *Risk:* the new fixture knob makes `fakeServer` mint sessions in modern
    mode where a conforming server would not, confusing a later reader.
    *Mitigation:* document the knob as modelling a non-conforming server, which
    is precisely the case the observation exists to catch, and default it off.
  - *Risk:* touching the refresh-token path was deliberately out of scope for
    #604's review. *Mitigation:* the change is confined to resolving one string
    before `issueRefreshToken`; rotation, reuse detection, grace window and TTL
    are untouched, and the new test asserts only the display name.
- **Conventions:** `go fmt`, `go vet`, `golangci-lint`; conventional commits
  (`test:` for findings 1–2, `docs:` or `refactor:` for finding 3, `fix:` for
  finding 4 — or one `fix:` commit per finding); merge-commit strategy per
  `.claude/CLAUDE.md`; synthetic fixture identifiers only (the existing
  `portal-client` / `portal.example.test` and `fake-telegram` fixtures are
  reused, no new identifiers invented).
