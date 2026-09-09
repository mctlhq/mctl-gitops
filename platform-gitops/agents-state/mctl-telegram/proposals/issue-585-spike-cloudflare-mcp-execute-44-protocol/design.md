# Design: issue-585-spike-cloudflare-mcp-execute-44-protocol

## Current state

`mctl-telegram` exposes `/mcp` through `mcpserver.NewStreamableHTTPServer(...)` and is pinned to `github.com/mark3labs/mcp-go v1.0.0`.

The existing repository clients (`cmd/canary`, load test, Local Bridge E2E) are legacy-style clients: they call `initialize`, capture `Mcp-Session-Id`, then send subsequent requests with that session id. That proves only the legacy path currently exercised by mctl's own clients.

The original proposal incorrectly inferred that because `WithStateLess(true)` is not passed, all protocol versions are necessarily sessionful. The pinned SDK's own `v1.0.0` modern tests show otherwise:

- modern `2026-07-28` requests carry protocol/client metadata on every request;
- `server/discover` is the modern discovery entry point;
- `initialize` is rejected as removed for modern clients;
- modern requests do not mint `Mcp-Session-Id`;
- `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` are validated against the request body;
- `WithStateLess(true)` is still relevant to legacy/session behavior, but its absence does not prove the modern path is stateful.

This means #585 should first **measure whether current `mctl-telegram` already exposes the SDK's modern path correctly**, while #568 remains responsible for the broader direct-upstream rollout/state inventory.

### OAuth current state

The authorization server already provides protected-resource metadata, authorization-server metadata, authorization-code flow, PKCE-S256, refresh tokens and exact redirect matching for registered clients.

Important current contract: authorization metadata advertises:

```json
"token_endpoint_auth_methods_supported": ["none"]
```

So mctl currently supports public OAuth clients with PKCE; there is no confidential-client/client-secret authentication path.

The existing `mctl_self_connect` client proves an in-memory pre-registered client can use the strict exact-redirect branch without RFC 7591 DCR.

### Identity / routing constraint

Telegram execution remains application-stateful. The hosted MTProto pool and Local Bridge connection ownership are not made horizontally safe merely because the MCP protocol becomes stateless. Cloudflare must also preserve per-user upstream identity; a shared upstream principal would break authorization and collapse any identity-based routing strategy.

## Proposed solution

### 1. Add an isolated `mcpprobe`; do not refactor the production canary

Create `internal/mcpprobe` plus a thin `cmd/mcpprobe` executable. The compatibility spike must not modify the paging canary or load generator merely to deduplicate code. Once the probe is proven, shared-client cleanup can be a separate follow-up.

The probe has two explicit protocol modes.

#### Modern mode (`2026-07-28`)

A modern request:

1. sends `server/discover` directly — no `initialize` bootstrap;
2. includes per-request `_meta` carrying protocol version, client info and client capabilities;
3. sends `MCP-Protocol-Version` and `Mcp-Method` headers;
4. sends `Mcp-Name` when the method names a capability, e.g. `tools/call`;
5. follows with `tools/list` and one read-only `tools/call`, still without a session id;
6. separately sends `initialize` as a negative compatibility test and records the expected removed-method rejection;
7. tests method/name header consistency by intentionally omitting/mismatching them in bounded negative cases.

The probe records what the deployed endpoint does; it does not assume current production already behaves like the SDK test fixture.

#### Legacy mode

For a configured legacy protocol version, the probe performs the existing initialize/session lifecycle and records whether a session id is minted and required.

Modern and legacy results are separate rows/results. There is no implicit fallback from a failed modern request into legacy while still calling the result "modern".

### 2. Report shape and safety

The report contains only:

- path label and evidence source;
- protocol mode/version;
- HTTP status / JSON-RPC error code;
- supported protocol versions;
- method/tool names and read-only annotations;
- session-id presence/length, never the value;
- boolean observations;
- timestamp and build/ref metadata where available.

It contains no bearer/refresh token, authorization code, Telegram message body, title, peer id, phone number or arbitrary tool result value.

The only real `tools/call` is guarded structurally by `readOnlyHint=true`; default to `get_my_send_status` or another non-content read-only status capability. If the configured target is not read-only, the probe refuses to call it.

### 3. Evidence provenance: three rows, not two

Use distinct evidence rows:

| row | source | purpose |
|---|---|---|
| `in-process-current-main` | `httptest` around the real handler wiring | what current code supports |
| `direct-deployed` | operator run against preview or `tg.mctl.ai` | what the deployed build actually does |
| `cloudflare-portal` | operator run through the configured Portal | what survives the enterprise edge |

CI may generate the first row only. It must never label an in-process result as live `tg.mctl.ai` evidence.

For each row record modern and legacy observations separately.

### 4. Pre-register Cloudflare as an exact-redirect public client

Add optional structured configuration for one or more pre-registered OAuth clients, e.g. `OAUTH_PREREGISTERED_CLIENTS` containing JSON records:

```json
[
  {
    "client_id": "portal-client-id",
    "redirect_uris": ["https://portal.example.test/servers-callback"]
  }
]
```

No secret field is added in this spike.

Implementation boundary:

- `internal/config` parses and validates the structured configuration;
- `cmd/server` passes the parsed records into `oauth.Config` (or an equivalent explicit constructor option);
- `internal/oauth.New` seeds them into its private `s.clients` registry with `CreatedAt` zero/static semantics, exactly where the built-in `mctl_self_connect` client is already seeded;
- `cmd/server` must not reach into `oauth.Server` internals directly.

This path uses exact redirect URI comparison. It does **not** use the implicit redirect-host allow-list and does not call `/oauth/register`.

Do not add `OAUTH_EXTRA_IMPLICIT_HOSTS`. That would broaden an older implicit/DCR compatibility surface for a Portal path that can and should use exact pre-registration. Existing `OAUTH_ALLOWED_IMPLICIT_HOSTS` semantics remain unchanged for existing clients.

### 5. Explicit Cloudflare OAuth compatibility gate

Before declaring Phase B green, test whether Cloudflare can operate as a public upstream OAuth client using:

```text
token_endpoint_auth_method = none
PKCE = S256
redirect_uri = exact pre-registered value
Require user auth = ON
```

If Cloudflare requires `client_secret_basic`, `client_secret_post`, or another confidential-client mechanism, record Phase B as BLOCKED and open a separate child issue. Do not add client-secret handling opportunistically inside this spike; that changes the authorization-server threat model and metadata contract.

DCR remains a compatibility-only test. CIMD remains the target registration direction when supported end-to-end.

### 6. Header compatibility semantics

Do not test whether `Mcp-Method` / `Mcp-Name` are "echoed"; echo is not the contract.

Test instead:

- correct headers + matching body succeed;
- missing/mismatched headers fail according to the modern binding;
- through Cloudflare, an upstream observation/log/trace confirms the headers survive the Portal path where that can be observed.

If preservation cannot be observed from the client side, mark it `PENDING-OPERATOR`; do not infer it from a 200 response alone.

### 7. Operator document

Add `docs/cloudflare-portal-compat.md` with:

- exact current mctl OAuth contract (`token_endpoint_auth_methods_supported=[none]`, PKCE-S256);
- instructions to paste the callback URI Cloudflare actually displays;
- `Require user auth=ON` as mandatory;
- explicit instruction **not** to add the Portal callback to implicit-host allow-lists for the preferred path;
- the three-row evidence matrix;
- bounded operator steps for deployed direct and Portal rows;
- two-user identity verification;
- the MTProto/Local Bridge ownership caveat;
- DCR labeled compatibility-only and CIMD labeled target when available.

## Tests

- modern direct request fixture based on the pinned SDK's `2026-07-28` request shape;
- modern `initialize` removed-method negative test;
- method/name header mismatch tests;
- legacy stateful fixture with minted/required session id;
- 401 challenge parsing without secret/token output;
- read-only guard test;
- report redaction test;
- in-process integration test around the real handler wiring;
- pre-registered public-client exact redirect positive and negative tests;
- unchanged PKCE/resource/audience/scope regression suite;
- no new HTTP+SSE / DCR dependency / deprecated primitive guard.

## Alternatives rejected

### Refactor `cmd/canary` in this spike

Rejected. The canary is paging/SLO infrastructure. A compatibility spike should not change its internals unless necessary for the compatibility result. Shared plumbing can be extracted later.

### Add an additive implicit-host variable for Cloudflare

Rejected. The preferred Cloudflare path is a registered client with exact redirect URI matching. Broadening the implicit-host compatibility surface is unnecessary and weaker.

### Add confidential-client support now

Rejected until Cloudflare proves it is required. The current server explicitly advertises public-client token endpoint auth (`none`). Adding secrets changes OAuth semantics and deserves a separate security-reviewed issue.

### Treat CI `httptest` as live evidence

Rejected. CI proves current code behavior only. Deployed direct and Portal behavior require bounded operator runs.

## Platform impact

- no database migration;
- no replica-count/HPA change;
- no MTProto or Local Bridge ownership change;
- no canary behavior change;
- one optional pre-registered-client configuration surface;
- one standalone probe binary/library;
- one compatibility/operator document;
- DCR, legacy SSE, Roots, Sampling and MCP Logging are not extended.

## Rollback

Unset the pre-registered-client configuration and stop running `cmd/mcpprobe`; no persisted state or schema migration requires cleanup. The existing OAuth/DCR compatibility behavior and production canary remain untouched.
