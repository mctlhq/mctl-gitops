# Glovo M1a slice 1: feature-off OAuth resource audience and fail-closed auth gates

## Context
Parent mctlhq/mctl-api#953 (Glovo M1a, tenant-bound synthetic Glovo
connections) was approved, but its one-shot implementation failed as too broad
(`mctl-agents-implement-dc72d343`, no commits, `needs-triage`). Issue #958 is
slice 1 of 4. It covers only the authentication plumbing the later slices
depend on: a separate OAuth protected resource for the Glovo MCP facade
(`https://glovo.mctl.ai/mcp`), exact-audience verification for that resource,
a deny-by-default feature gate with typed `not_ready` / `not_authorized`
errors, and a reserved (not yet issued) Glovo worker identity. Everything ships
feature-off.

This matters because later slices add tenant resolution, a connection store
and a worker. Each of those relies on two guarantees. First, a token minted for
the Glovo resource can never be used against the main API, `/mcp`, the support
routes or Telegram surface routes. Second, a token for any other audience can
never reach Glovo. Setting up these guarantees first, with nothing reachable,
keeps later slices small and makes them safe to review. This slice is not an
implementation approval in its own right: the #953 grant must not be reused,
and this proposal needs its own content digest and explicit human approval.

## User stories
- AS a platform operator I WANT the Glovo resource to be configurable but inert SO THAT deploying this slice changes no behaviour of the running API.
- AS a security reviewer I WANT a Glovo-audience token to be refused on every existing route SO THAT the new audience cannot widen access to the API, `/mcp`, support or Telegram routes.
- AS a security reviewer I WANT existing API, support, DevLoop agent and surface tokens to be refused by any Glovo gate SO THAT Glovo access can never be inferred from another credential.
- AS a later-slice implementer I WANT typed `not_ready` / `not_authorized` errors and a single gate function SO THAT facade and worker routes added later fail closed by construction.
- AS a security reviewer I WANT the future Glovo worker identity reserved but unissued SO THAT no caller can become a provider worker by setting env vars, crafting headers or choosing a token subject.

## Acceptance criteria (EARS)
- WHILE `GLOVO_MCP_RESOURCE` is unset or empty THE SYSTEM SHALL behave exactly as before this change for `/oauth/authorize`, `/oauth/token`, `/.well-known/oauth-protected-resource`, `/.well-known/oauth-protected-resource/mcp`, token verification and every authenticated route. Existing tests must pass unmodified.
- WHILE `GLOVO_MCP_RESOURCE` is unset or empty THE SYSTEM SHALL answer `invalid_target` to an authorize or token request whose `resource` is `https://glovo.mctl.ai/mcp`, as it does today.
- WHEN the process starts with `GLOVO_MCP_RESOURCE` set THE SYSTEM SHALL refuse to boot unless the value is an absolute https URL without a fragment that names neither this API (audience, base URL, `/mcp`) nor `OAUTH_SUPPORT_RESOURCE`.
- WHILE the Glovo feature gate is closed (always, in this slice) THE SYSTEM SHALL refuse to mint any access or refresh token whose audience is the Glovo resource. A request naming the configured Glovo resource at `/oauth/authorize` or `/oauth/token` gets the RFC 8707 `invalid_target` error, and nothing is stored or signed.
- WHEN an access token is verified and its `aud` contains the configured Glovo resource THE SYSTEM SHALL accept it as Glovo-audience only if `aud` is exactly that one value and `iss` equals the server's `BaseURL`. Any other `aud` containing the Glovo resource (multi-valued, or mixed with the API or support audience) SHALL be refused as `aud_mismatch`.
- IF a token is malformed, has a bad signature, is expired, has the wrong issuer, has a wrong audience, or has no audience where one is required THEN THE SYSTEM SHALL refuse it on every route, Glovo resource configured or not, with the same 401 and metric result as today.
- IF a Glovo-audience token is presented on any route of the authenticated group (including `/mcp`, `/api/v1/whoami` and the support relay routes) THEN THE SYSTEM SHALL answer 401 `invalid_token` before any other gate runs.
- IF a Glovo-audience caller asks to mint a support token THEN THE SYSTEM SHALL refuse it with `ErrSupportTokenRefused`.
- WHEN the Glovo gate (`glovo.Gate.Authorize`) is evaluated THE SYSTEM SHALL return `not_ready` while the feature is closed, whatever the caller. Once later slices open it, the gate SHALL return `not_authorized` for any caller that is not Glovo-audience with a resolved principal. API, support, agent-run, surface, relayed, service, CI and admin callers SHALL all get `not_authorized`.
- WHERE a Glovo error is written to HTTP THE SYSTEM SHALL map `not_ready` to 503 and `not_authorized` to 403, using a stable JSON envelope `{"error": "<code>", "error_description": "..."}`.
- WHILE this slice is deployed THE SYSTEM SHALL register no new HTTP route and no new MCP tool, and SHALL NOT change the protected-resource metadata documents.
- THE SYSTEM SHALL reserve the identifier `service:mctl-glovo-worker` and refuse to authenticate any caller as it. No env var (including `MCTL_GLOVO_WORKER_TOKEN`), request header, OAuth subject or static token may produce a user that `IsGlovoWorker()` reports true for.
- THE SYSTEM SHALL NOT infer, select or record a tenant for any Glovo-related request in this slice.

## Out of scope
- OAuth team selection, consent changes, `selected_team_tenant` grants, minting enabled Glovo tokens.
- Postgres migrations, connection store, install/order/`aar_` records.
- Glovo facade or worker routes, MCP tools, provider calls, real Glovo, payments.
- Issuing a worker token, Temporal roles or configuration, GitOps values, DNS for `glovo.mctl.ai`, deployment changes.
- Any change to mctl-telegram, mctl-support or mctl-agents.

## Open questions
- Exact-audience versus precedence. Parent #953 design said "a Glovo entry wins over support and API entries" (a precedence switch, as for support). This issue asks for "exact `aud`" and lists "multi-aud tokens" as a negative test. This proposal follows the issue: a Glovo token must carry exactly one `aud`, and a multi-valued `aud` naming Glovo is refused. This is stricter and still fail-closed. Reviewers should confirm it.
- Default value. #953 proposed `GLOVO_MCP_RESOURCE` defaulting to empty (disabled), unlike `OAUTH_SUPPORT_RESOURCE`, which has a non-empty default. This proposal keeps the empty default, so absence is the feature-off state. `https://glovo.mctl.ai/mcp` is exposed only as the documented constant `auth.GlovoResourceIntended`.
- The feature gate in this slice is a compile-time closed gate (`glovo.Gate{Open: false}`), not an env switch, so no configuration can open it before the later slices exist. Whether slice 2+ opens it through an env var (for example `GLOVO_ENABLED`) or through the presence of the store is left to those slices.
- "Glovo endpoints (if routed) return fail-closed 503": this slice routes none. The 503 mapping exists in `glovo.WriteError` and is unit tested, but no route uses it yet.
- The deployed mctl-api config could not be observed directly; see design.md "Deployed state checked".
