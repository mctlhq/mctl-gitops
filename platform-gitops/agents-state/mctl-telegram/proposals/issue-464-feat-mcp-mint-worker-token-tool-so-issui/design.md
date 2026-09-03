# Design: issue-464-feat-mcp-mint-worker-token-tool-so-issui

## Current state

**HTTP mint path.** `internal/workertoken/tokenhandler.go` owns
`NewHandler(secret []byte, issuer, mcpAudience string) http.HandlerFunc`,
mounted at `POST /api/mcp/worker-token` in `cmd/server/main.go:470-473`,
gated on `id.HasScope("admin:users")` and only mounted when
`cfg.OAUTHJWTSecret != ""`. The handler owns, as unexported package state:

- `allowedReadOnlyScopes` / `allowedLocalBridgeScopes` (`tokenhandler.go:58-73`)
  — the fixed per-purpose scope allowlists.
- `defaultWorkerTokenTTL` (30d) / `maxWorkerTokenTTL` (90d)
  (`tokenhandler.go:43-46`).
- `workerAudience` ("mcp-worker-ro") / `workerBridgeAudience`
  ("mcp-worker-bridge") (`renewhandler.go:33-47`) — the per-purpose
  audience markers, also consumed by the renew path to recognize a token
  as renewable.
- Purpose dispatch (`tokenhandler.go:159-173`): `""` selects the read-only
  allowlist/default/audience; `"local-bridge"` selects the send+pin
  allowlist/default/audience; anything else is a 400.
- Scope validation against the selected allowlist
  (`tokenhandler.go:175-184`, `isAllowedScope`).
- TTL resolution and clamp to the ceiling (`tokenhandler.go:186-192`).
- `orig_iat` anchoring via `localjwt.Claims.OriginalIssuedAt` set to
  `time.Now().Unix()` at mint time (`tokenhandler.go:198-208`) — this is
  what lets `NewRenewHandler` (`renewhandler.go`) bound the total renewal
  chain to `maxRenewalChain` (365d) from the original human-approved mint.
- Structured logging of `admin_user_id`, `target_tg_id`, `scopes`, `ttl`,
  `expires_at`, `purpose`, `audience_marker` (`tokenhandler.go:219-220`) —
  never the raw token.
- Response shape `workerTokenResponse{WorkerToken, ExpiresAt}`
  (`tokenhandler.go:97-100`).

This is genuinely security policy, not incidental request-handling: the
issue's own framing (`internal/workertoken/tokenhandler.go`'s package doc,
lines 1-23) says the package exists specifically to replace hand-signing
with `OAUTH_JWT_SIGNING_KEY`, and every constant above is what makes that
replacement safe.

**MCP admin-tool path.** `internal/mcp/tools.go` has an established shape
for admin-only mutating tools — `toolSetAccountMode`
(`tools.go:1011-1086`) and `toolProvisionLocalAccount`
(`tools.go:1093-...`):

1. `id := auth.From(ctx)`; `requireScope(id, "admin:users")`
   (`tools.go:1347-1354`) gates entry, returning a tool error with no
   audit write (matches the HTTP handler's pre-auth 401/403, which also
   isn't audited — there is no user identity yet to audit against).
2. Past the gate, a local `refuse(format, args...)` closure wraps every
   remaining early return: it builds the error, calls `s.audit(ctx, id,
   "<tool_name>", "", err, startedAt)`, and returns the tool error. This is
   the #462 fix `toolSetAccountMode`'s comment describes
   (`tools.go:1042-1052`): every exit past the scope gate is audited,
   including refusals, not only the write that reaches the database.
3. Args are pulled with `intArg`/`stringArg`/`boolArg` helpers.
4. Success returns `jsonResult(someResult{...})` (`tools.go:1495`) after a
   final `s.audit(ctx, id, "<tool_name>", "", nil, startedAt)`.
5. Tools are registered unconditionally in
   `internal/mcp/server.go:HTTPHandler` via
   `{t, h := s.toolXxx(); s.addTool(srv, t, h)}` (`server.go:168-169` for
   the two mode/provision tools); `s.addTool` only filters on
   `ToolFilter` (read-only vs all), not on server configuration.

`mcp.Server` (`internal/mcp/server.go:18-57`) currently holds no reference
to the JWT signing secret, issuer, or `mcpAudience` — those live only in
`cmd/server/main.go`'s `cfg` and are passed directly into
`workertoken.NewHandler`/`NewRenewHandler` at the HTTP mount sites
(`cmd/server/main.go:470-480`). `mcpapp.New(...)` is constructed at
`cmd/server/main.go:436` and chained with `WithVersion`/`WithLimiter`/
`WithMetrics`/`WithPeerCache`/`WithToolFilter`, later `WithHub`
(`main.go:520`) — the same `With*` builder pattern this proposal extends.

## Proposed solution

**1. Factor the mint policy out of `workertoken.NewHandler` into a shared,
exported function**, so the HTTP handler and the new MCP tool are two thin
callers of one implementation rather than two copies of the same
constants — this is the issue's explicit, non-negotiable requirement.

Add `internal/workertoken/mint.go`:

```go
// Purpose selects which allowlist/default/audience-marker this mint uses.
type Purpose string

const (
    PurposeReadOnly    Purpose = ""
    PurposeLocalBridge Purpose = "local-bridge"
)

// MintParams is the already-validated, transport-agnostic input to Mint.
type MintParams struct {
    TelegramID int64
    Purpose    Purpose // "" (unrecognized falls through to ErrUnknownPurpose)
    Scopes     []string // nil/empty => this purpose's default scopes
    TTLHours   int      // 0 => defaultWorkerTokenTTL
}

// MintResult is the transport-agnostic output of Mint.
type MintResult struct {
    Token          string
    ExpiresAt      time.Time
    Scopes         []string
    Purpose        Purpose
    AllowlistName  string // "read-only" | "local-bridge", for logging
    AudienceMarker string
}

// Sentinel errors so each caller maps to its own transport (HTTP status
// code vs MCP tool error string) without Mint knowing about either.
var (
    ErrUnknownPurpose    = errors.New("unknown purpose")
    ErrInvalidTelegramID = errors.New("telegram_id required")
    ErrScopeNotAllowed   = errors.New("scope not in allowlist")
)

// Mint applies the worker-token policy (allowlist selection, default
// scopes, TTL ceiling, audience marker, orig_iat anchoring) and signs the
// resulting token. This is the ONLY place that policy is expressed;
// NewHandler and the mint_worker_token MCP tool both call it.
func Mint(signer *localjwt.Issuer, mcpAudience string, p MintParams) (*MintResult, error) {
    ...
}
```

`Mint` contains exactly the logic currently inlined in
`tokenhandler.go:153-220` (purpose dispatch, scope validation, TTL clamp,
audience assembly, `orig_iat` anchoring, `signer.Mint` call) minus the
HTTP-specific parts (JSON decode, `writeJSON`/`writeJSONError`, the
`admin_user_id` log field, which the caller still owns because only the
caller knows its own identity source).

`NewHandler` becomes a thin wrapper: construct the signer once (unchanged),
decode+validate the HTTP body, translate to `MintParams`, call `Mint`, map
`Mint`'s sentinel errors to HTTP status codes, log
`"worker token minted"` with the fields `Mint` returned plus
`admin_user_id` from `auth.From(ctx)`, and write
`workerTokenResponse{WorkerToken: result.Token, ExpiresAt: ...}`.
`NewRenewHandler` is unaffected in this proposal (renewal has different
inputs — a presented token's claims, not admin-supplied `telegram_id`+
`scopes` — so it is out of scope per the issue's "Not in scope" section);
it keeps reading `allowedReadOnlyScopes`/`allowedLocalBridgeScopes`/
`workerAudience`/`workerBridgeAudience`, which stay as package-level vars
(now referenced from `mint.go` too, not duplicated).

**2. Give `mcp.Server` a way to call `Mint`.** Add to `mcp.Server`
(`internal/mcp/server.go`):

```go
// WorkerTokenSigner mints worker tokens for mint_worker_token. Nil when
// OAUTH_JWT_SIGNING_KEY is unset, matching the same gate that keeps
// POST /api/mcp/worker-token unmounted (cmd/server/main.go:470).
WorkerTokenSigner *localjwt.Issuer
// WorkerTokenAudience is the mcpAudience passed to workertoken.Mint,
// mirroring cfg.OAUTHJWTAudience at the HTTP mount site.
WorkerTokenAudience string
```

with a builder:

```go
func (s *Server) WithWorkerTokenSigner(signer *localjwt.Issuer, mcpAudience string) *Server {
    s.WorkerTokenSigner = signer
    s.WorkerTokenAudience = mcpAudience
    return s
}
```

`cmd/server/main.go` constructs the signer once, next to the existing
`if secret := cfg.OAUTHJWTSecret; secret != "" { ... }` block that mounts
`POST /api/mcp/worker-token`, and chains it onto `mcpSrv`:

```go
if secret := cfg.OAUTHJWTSecret; secret != "" {
    mux.With(...).Post("/api/mcp/worker-token", workertoken.NewHandler(...))
    mux.With(...).Post("/api/mcp/worker-token/renew", workertoken.NewRenewHandler(...))
    if signer, err := localjwt.NewIssuer([]byte(secret), selectAgentIssuer(cfg)); err == nil {
        mcpSrv = mcpSrv.WithWorkerTokenSigner(signer, cfg.OAUTHJWTAudience)
    } else {
        slog.Error("worker token signer init failed; mint_worker_token tool will refuse", "err", err)
    }
}
```

Passing a constructed `*localjwt.Issuer` (rather than the raw secret+issuer
strings) keeps `mcp.Server` from re-deriving anything the signer needs;
`workertoken.Mint`'s signature takes the signer directly for the same
reason — one fewer place that could construct it differently.

**3. Add `toolMintWorkerToken` in `internal/mcp/tools.go`**, following
`toolSetAccountMode`'s exact shape:

```go
func (s *Server) toolMintWorkerToken() (mcplib.Tool, mcpserver.ToolHandlerFunc) {
    tool := mcplib.NewTool("mint_worker_token",
        mcplib.WithTitleAnnotation("Mint a headless MCP worker token"),
        mcplib.WithReadOnlyHintAnnotation(false),
        mcplib.WithDestructiveHintAnnotation(true),
        mcplib.WithOpenWorldHintAnnotation(false),
        mcplib.WithOutputSchema[mintWorkerTokenResult](),
        mcplib.WithDescription(`Admin only (requires the admin:users scope). Mint a bounded,
scoped bearer token for a headless MCP worker (e.g. a Local Bridge daemon), identical in policy to
POST /api/mcp/worker-token.

Inputs:
  telegram_id — int, required. The TARGET account the token authenticates as.
  purpose     — string, optional. "" (default) mints a read-only token. "local-bridge" mints a
                send-and-pin-capable token for a Local Bridge daemon — request it explicitly, it is
                never the default for an unqualified mint.
  scopes      — array of strings, optional. Must be a subset of the allowlist selected by purpose;
                omit for that purpose's default scopes.
  ttl_hours   — int, optional. Clamped to the TTL ceiling if it exceeds it.

Returns the minted token, its scopes, purpose, and expires_at. The token is not renewable by this
tool call again — the worker renews itself via POST /api/mcp/worker-token/renew.`),
        mcplib.WithNumber("telegram_id", mcplib.Required(), ...),
        mcplib.WithString("purpose", ...),
        mcplib.WithArray("scopes", ...),
        mcplib.WithNumber("ttl_hours", ...),
    )
    handler := func(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
        startedAt := time.Now()
        id := auth.From(ctx)
        if err := requireScope(id, "admin:users"); err != nil {
            return mcplib.NewToolResultError(err.Error()), nil
        }
        refuse := func(format string, a ...any) *mcplib.CallToolResult {
            err := errors.New(formatErr(format, a...))
            s.audit(ctx, id, "mint_worker_token", "", err, startedAt)
            return mcplib.NewToolResultError(err.Error())
        }
        if s.WorkerTokenSigner == nil {
            return refuse("worker token minting is not configured on this deployment"), nil
        }
        args := req.GetArguments()
        tgID := int64(intArg(args, "telegram_id", 0))
        if tgID <= 0 {
            return refuse("telegram_id is required and must be a positive integer"), nil
        }
        purpose := workertoken.Purpose(stringArg(args, "purpose", ""))
        scopes := stringSliceArg(args, "scopes")
        ttlHours := intArg(args, "ttl_hours", 0)

        result, err := workertoken.Mint(s.WorkerTokenSigner, s.WorkerTokenAudience, workertoken.MintParams{
            TelegramID: tgID, Purpose: purpose, Scopes: scopes, TTLHours: ttlHours,
        })
        if err != nil {
            return refuse("mint_worker_token: %v", err), nil
        }
        slog.Info("worker token minted", "admin_user_id", id.UserID, "target_tg_id", tgID,
            "scopes", result.Scopes, "expires_at", result.ExpiresAt.UTC().Format(time.RFC3339),
            "purpose", result.AllowlistName, "audience_marker", result.AudienceMarker,
            "via", "mcp_tool")
        s.audit(ctx, id, "mint_worker_token", "", nil, startedAt)
        return jsonResult(mintWorkerTokenResult{
            TelegramID: tgID,
            Purpose:    string(result.Purpose),
            Scopes:     result.Scopes,
            ExpiresAt:  result.ExpiresAt.UTC().Format(time.RFC3339),
            Token:      result.Token,
            OK:         true,
        })
    }
    return tool, handler
}
```

`stringSliceArg` is a new small helper alongside the existing
`intArg`/`stringArg`/`boolArg` in `tools.go`, following the same signature
convention (`args map[string]any, key string, ... ) []string`).

Register it in `internal/mcp/server.go:HTTPHandler`, next to the other
admin-mutating tools:
`{t, h := s.toolMintWorkerToken(); s.addTool(srv, t, h)}`.

**4. Prove the two paths cannot drift**, per the issue's "asserted by a
test that would fail if either side's policy changed alone." Add
`internal/workertoken/mint_test.go` (or extend `tokenhandler_test.go`)
with a table test that drives `NewHandler`'s HTTP path and
`workertoken.Mint` directly with identical `MintParams`-equivalent inputs
for both `purpose=""` and `purpose="local-bridge"`, and asserts the
resulting `Scopes`, clamped TTL/`expires_at` (within a tolerance), and
`AudienceMarker` are identical. Because both `NewHandler` and
`toolMintWorkerToken` call the same `Mint`, this test — run once, against
`Mint` directly plus once through the HTTP wrapper — is sufficient: there
is structurally only one policy implementation left to test, and a
regression in `Mint` fails both callers' tests simultaneously; a
hypothetical future re-duplication (someone inlining logic back into
`toolMintWorkerToken`) would fail the parity assertion because its output
would stop being sourced from `Mint`.

## Alternatives

1. **Have the MCP tool call `NewHandler`'s `http.HandlerFunc` in-process**
   by constructing a fake `http.Request`/`httptest.ResponseRecorder` and
   parsing the JSON response. Rejected: it technically reuses the exact
   code path, but it is a worse "thin wrapper" than factoring out `Mint`
   — the tool would depend on HTTP status codes and JSON error shapes
   never designed to be introspected programmatically, and every future
   HTTP-specific change to `NewHandler` (headers, content-type, error
   body shape) would risk breaking the tool for reasons that have nothing
   to do with mint policy. Factoring out `Mint` keeps the shared surface
   to exactly the policy, which is what the issue asks to converge.

2. **Leave the allowlists/TTL/audience constants where they are in
   `tokenhandler.go`/`renewhandler.go` and have the MCP tool import and
   reference those same package-level vars directly**, duplicating only
   the purpose-dispatch/validation/clamp control flow in
   `toolMintWorkerToken`. Rejected: this still leaves two copies of the
   *logic* (dispatch, validation order, TTL clamp, `orig_iat` anchoring)
   even if the *constants* are shared, which is exactly the drift the
   issue warns about — "if this tool re-derives any of them, the two
   paths will drift." The issue's wording ("Factor the policy out of
   `workertoken.NewHandler`") points at extracting the logic, not just
   the constants.

3. **Pass the raw JWT secret + issuer strings into `mcp.Server` instead of
   a constructed `*localjwt.Issuer`**, and have `toolMintWorkerToken`
   construct its own `localjwt.NewIssuer` per call (mirroring how
   `NewHandler` constructs its own signer once at handler-construction
   time). Rejected: constructing the signer inside the MCP package would
   duplicate `NewHandler`'s `signerErr` handling a third time and gives
   `mcp.Server` a second thing to get wrong (issuer string) beyond what it
   needs. Constructing the signer once in `cmd/server/main.go` and handing
   `mcp.Server` the already-built `*localjwt.Issuer` keeps `mcp.Server`
   from knowing about raw key material at all, matching how it already
   receives `*db.Store`/`*telegram.ClientPool` as constructed
   dependencies rather than connection strings.

## Platform impact

- **Migrations**: none. No schema change; `audit_logs` already records
  `mint_worker_token` the same way it records every other tool call via
  `s.audit`.
- **Backward compatibility**: `POST /api/mcp/worker-token` and
  `/renew` keep their exact request/response shape and route — `NewHandler`
  is refactored internally but not resized externally. Existing callers of
  the HTTP endpoint (the canary, any hand-run curl) are unaffected.
- **Resource impact**: negligible — one more MCP tool registration, one
  more `*localjwt.Issuer` construction at server startup (already done
  once for the HTTP handler; this proposal reuses that construction rather
  than doubling it, per Alternative 3's rejection reasoning if implemented
  as designed).
- **Risks**:
  - *A months-long credential becomes easier to mint, which could
    increase how often one is minted carelessly.* Mitigated by keeping
    every guard from the HTTP path unchanged (`admin:users` gate, fixed
    allowlists, TTL ceiling, explicit `purpose` requirement for send/pin)
    and by the tool description text explicitly stating the token is
    long-lived and that `purpose: "local-bridge"` must be named
    deliberately, echoing the issue's "Do not make a send-capable token
    the default for an unqualified mint" acceptance criterion.
  - *The minted token appears in the MCP tool result, which some MCP
    clients may log or surface in chat transcripts more readily than a
    curl response.* This mirrors the existing risk of the HTTP endpoint
    (its JSON body carries the same raw token) and is inherent to the
    tool's purpose; no new redaction gap is introduced since
    `internal/audit/redact.go` already governs what `slog` lines may
    carry, and this proposal's log line follows `NewHandler`'s existing
    practice of never including the raw token.
  - *Drift between `Mint` and any future direct edit to `NewHandler`.*
    Mitigated structurally (there is only one implementation left to
    edit) and by the parity test in tasks.md.
