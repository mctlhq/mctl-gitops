# Glovo M1c: deployable OAuth MCP facade for the team-scoped fake Glovo pilot

## Context

The merged M0 contract (PR #1233, issue #1227) defines the Glovo protected resource
`https://glovo.mctl.ai/mcp`, two scopes (`glovo:read`, `glovo:basket:prepare`) and a
closed set of seven tools in `docs/contracts/glovo-mcp-tools.json`, together with ADR
`docs/adr/0010-glovo-multitenant-connections.md`, the threat model
`docs/agent-runtime/glovo-threat-model.md` and the handoff contract
`docs/contracts/glovo-checkout-handoff.md`. No server implements any of it yet. The
owner decision (mctlhq/.github#324) is `REUSE_EXISTING`: the source lives in
`mctl-telegram`, but the facade is a separately built and deployed binary and image,
and mctl-api stays the only authority for identity, tenant, connection (`gcn_`), order
and `aar_` approval.

This proposal adds that facade: a Go executable `cmd/glovo-mcp` with its own
Dockerfile and GHCR image. It serves Streamable HTTP MCP at `/mcp` and RFC 9728
protected-resource metadata. It validates mctl-api-issued bearer tokens, resolves an
explicitly selected team tenant through mctl-api on every call, and hands every tool
to mctl-api over a frozen wire protocol. It holds no secrets, no Temporal client, no
Glovo access and no Kubernetes or Vault privileges. All code is built and tested
against an in-repo fake mctl-api harness, so it can proceed while mctl-api M1a/M1b
(mctl-api#953, #954) are still in progress. Activation, image publication, DNS/TLS and
deployment are out of scope and stay off.

## User stories

- AS an MCTL team member in the pilot allowlist I WANT to connect Claude (or another
  MCP client) to `https://glovo.mctl.ai/mcp` through standard OAuth discovery SO THAT I
  can use the fake Glovo tools inside my selected team tenant.
- AS a pilot user I WANT `glovo_prepare_order` to return a pending approval that only
  a human can grant through mctl-api SO THAT no model or tool can approve or place an
  order on my behalf.
- AS a member of a team with other members I WANT my connections and orders to be
  invisible and unusable to colleagues and to other tenants SO THAT tenant and owner
  isolation hold.
- AS a platform operator I WANT the facade as an independent binary and image, with
  health probes, metrics, traces, limits and a kill switch SO THAT I can review,
  release and roll it back without touching `tg.mctl.ai`.
- AS a facade developer I WANT a fake mctl-api harness with the frozen wire protocol
  SO THAT I can build and test the facade before mctl-api M1a/M1b merge.

## Acceptance criteria (EARS)

Discovery and transport
- WHEN a client sends `GET /.well-known/oauth-protected-resource/mcp` (or the root
  alias) THE SYSTEM SHALL return RFC 9728 metadata with `resource` exactly
  `https://glovo.mctl.ai/mcp` (the configured `GLOVO_MCP_RESOURCE`), the configured
  mctl-api `authorization_servers` entry, `scopes_supported` exactly
  `["glovo:read","glovo:basket:prepare"]` and `bearer_methods_supported` `["header"]`.
- WHEN a request reaches `/mcp` without a valid bearer token THE SYSTEM SHALL answer
  HTTP 401 with `WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource/mcp"`
  and SHALL NOT call mctl-api.
- WHEN an authorized client performs the MCP `initialize` handshake over Streamable
  HTTP THE SYSTEM SHALL answer with a pinned server name `mctl-glovo-mcp`, the build
  version and a protocol version from a pinned supported list, and `tools/list` SHALL
  return exactly the seven tools of `docs/contracts/glovo-mcp-tools.json`, with input
  and output schemas byte-equivalent (after canonical JSON) to the contract.
- THE SYSTEM SHALL expose no MCP resources, prompts, sampling or any tool not in the
  contract, and SHALL NOT serve any `tg.mctl.ai` route, tool or descriptor.

Token validation (checkpoint 1, ADR 0010)
- IF the bearer is not a JWS signed by a key in the configured mctl-api JWKS, or its
  `alg` is not in the allowed asymmetric list (RS256, ES256), THEN THE SYSTEM SHALL
  refuse with 401 `invalid_token`.
- IF `iss` does not equal `GLOVO_MCP_ISSUER` exactly, or `aud` does not contain
  exactly the string `GLOVO_MCP_RESOURCE` (no prefix, suffix, origin-only or trailing
  slash variant), or `exp` is past, or `nbf`/`iat` is in the future beyond 60 s skew,
  or `sub` is empty, THEN THE SYSTEM SHALL refuse with 401 `invalid_token` and SHALL
  NOT call mctl-api.
- IF the token lacks the tool's `required_scope` THEN THE SYSTEM SHALL return an MCP
  tool error `not_authorized` (HTTP 403 `insufficient_scope` at transport level when
  no scope from `scopes_supported` is present at all) and SHALL NOT call mctl-api.

Tenant and pilot resolution (per call)
- WHEN a tool is called THE SYSTEM SHALL derive the tenant only from the token's
  selected-tenant claim (`mctl_tenant`), and SHALL re-check the principal, membership,
  pilot allowlist and install through the mctl-api `resolve` endpoint before every
  effectful or read call to mctl-api.
- IF the token carries no selected tenant THEN THE SYSTEM SHALL return `no_tenant`;
  IF mctl-api reports more than one candidate THEN `ambiguous_tenant`; IF the
  selection is a personal scope THEN `scope_unsupported`; IF the principal is not in
  the pilot allowlist THEN `not_in_pilot`; IF the membership is expired or revoked
  THEN `not_authorized`. In every such case THE SYSTEM SHALL invoke no mctl-api effect
  endpoint.
- THE SYSTEM SHALL NOT fall back to a default tenant, `labs`, `mctl`, a hosting
  namespace, a Telegram OAuth principal or any value supplied in tool arguments.

Tool behaviour
- WHEN tool arguments contain an undeclared property, a wrong type, an over-length
  string or a value outside the schema THE SYSTEM SHALL reject the call with
  `invalid_arguments` before any mctl-api call.
- WHEN `glovo_connect_account` is called THE SYSTEM SHALL ask mctl-api to create a
  fake-provider `pending_handoff` connection bound to the resolved tenant and
  principal and return only `connection_id`, `state`, `handoff_url` and `expires_at`.
- WHEN `glovo_prepare_order` is called THE SYSTEM SHALL ask mctl-api to start or
  query the `aar_` approval flow for the preview, perform no basket write, and return
  `order_id`, `fingerprint`, `consent_request_id` (an `aar_` id) and `expires_at`.
- WHILE an order is awaiting approval THE SYSTEM SHALL offer no tool that approves,
  consumes a receipt, places, pays or checks out, and SHALL treat a `hir_` reference
  as never authorizing anything.
- IF an `order_ref`, `preview_id`, `order_id` or connection belongs to another
  principal or tenant, or does not exist, THEN THE SYSTEM SHALL return the same
  `not_found` result in both cases.
- WHEN a read-only tool (`glovo_auth_status`, `glovo_get_order_history`,
  `glovo_preview_reorder`, `glovo_get_basket`, `glovo_order_status`) is called THE
  SYSTEM SHALL call only mctl-api read endpoints.
- WHEN mctl-api returns a response THE SYSTEM SHALL validate it against the tool's
  output schema and SHALL return `upstream_invalid` rather than any non-conforming
  field.

Limits, observability, lifecycle
- THE SYSTEM SHALL cap request bodies at 64 KiB, mctl-api response bodies at 256 KiB,
  and apply a per-principal token-bucket rate limit and a global concurrency cap,
  returning HTTP 429 or tool error `rate_limited` when exceeded.
- WHEN a tool call finishes THE SYSTEM SHALL emit one audit log record and one span
  with tool name, outcome code, latency, hashed principal and tenant, and request id,
  and SHALL NOT include tokens, handoff URLs, tool arguments or results.
- THE SYSTEM SHALL never place a token in a URL query parameter, log line, metric
  label, span attribute, tool result or error message.
- WHEN `/healthz` is requested THE SYSTEM SHALL answer 200 while the process runs;
  WHEN `/readyz` is requested THE SYSTEM SHALL answer 200 only when `GLOVO_MCP_ENABLED`
  is true, the JWKS has been fetched and the mctl-api `/healthz` answered within 2 s.
- WHILE `GLOVO_MCP_ENABLED` is false (the default) THE SYSTEM SHALL answer `/mcp` with
  HTTP 503 and SHALL NOT contact mctl-api.
- WHEN the process receives SIGTERM THE SYSTEM SHALL fail readiness, stop accepting
  connections, and drain in-flight requests for up to 20 s before exiting.

Non-regression
- THE SYSTEM SHALL leave `cmd/server`, `Dockerfile`, `docs/tool-descriptors*.json`
  and `docs/portal-allowlist.json` byte-unchanged, with their existing tests green.

## Out of scope

- Real Glovo provider access, the provider worker, adapters, sessions or any Glovo
  egress (gate G3; separate slice).
- mctl-api implementation (M1a mctl-api#953, M1b mctl-api#954), the authorization
  server, consent UI, `aar_` approval UI and the handoff page.
- Temporal access of any kind from the facade (mctl-gitops#2456).
- Publishing the image to GHCR from a release, gitops `values.yaml`, ArgoCD apps,
  DNS, TLS or production/preview deployment (mctl-gitops#2457, gate G6).
- Personal scope (until mctlhq/.github#309), scheduled orders, `glovo_confirm_basket`.
- Any change to `tg.mctl.ai` behaviour.

## Open questions

- Authorization server support (mctl-api#953): this proposal assumes mctl-api issues
  asymmetric-signed JWTs with a public JWKS, accepts RFC 8707 `resource`
  `https://glovo.mctl.ai/mcp`, and places the user's explicitly selected tenant in a
  `mctl_tenant` claim. If mctl-api selects tenant differently, only
  `internal/glovo/authn` changes; the wire protocol header carrying the tenant stays.
- Facade-to-mctl-api authentication: the proposal forwards the user's access token
  for re-verification by mctl-api (`X-Mctl-Subject-Token`) plus a facade workload
  credential. mctl-api owners may prefer RFC 8693 token exchange; that is a client
  swap in `internal/glovo/mctlapi` behind the same interface.
- The wire protocol (`docs/contracts/glovo-facade-mctl-api.md`, v1alpha1) is frozen
  on the facade side by this proposal; mctl-api M1a/M1b must adopt it or a version
  bump is required before activation.
- Exact rate-limit numbers (default proposed: 30 calls/min per principal, burst 10,
  64 concurrent requests) need operator review before any deployment.
- Hostname reservation: `glovo.mctl.ai` is named by the contract, but no DNS or
  gitops entry exists and none is created here.
