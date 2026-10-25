# MCP gateway G0 spike: identity, per-tool policy and tenant isolation before migration

## Context

mctlhq/.github#195 activates (2026-10-25, P1) the bounded G0 decision spike for
the accepted MCP gateway design in `docs/plans/mcp-gateway.md` (mctlhq/.github#194,
decisions D1-D5 accepted 2026-10-17). The spike must decide, with exactly one
verdict `GO | REVISE | NO-GO`, whether an mctl-owned gateway gives enough
authorization and operational value to replace the user-blind Cloudflare MCP
Portal at `mcp.mctl.ai`. It must prove the identity/delegation/authorization
boundary (resource-bound caller token, RFC 8693-shaped exchange, asymmetric
verification, principal x tenant x server x tool policy, failure semantics,
audit correlation, direct-path bypass model, SDK choice) in an isolated,
deterministic reference model, and map every production behaviour to pinned
`mctl-api` code, without changing any repository other than `mctlhq/.github`.

It matters because the current production token is not resource-bound: at
`mctlhq/mctl-api@98bbf8c61006f1d70762c1ae2a9d3747c67ef241`,
`internal/auth/oauth_server.go` signs access tokens with a shared HMAC secret
(`signJWT`, `{"alg":"HS256"}`), the `jwtPayload` has no `aud` claim, and
`verifyJWT` checks only signature, `iss` and `exp`. Any gateway-audience token
minted by the same issuer today would therefore be accepted at `api.mctl.ai`.
The spike must show the contract that closes this, and in which order it must
be shipped, before any G1-G5 work is authorized.

## User stories

- AS the platform owner I WANT one evidence-backed `GO | REVISE | NO-GO` verdict
  on the gateway boundary SO THAT I can authorize (or refuse) the G1-G5
  migration epic without guessing.
- AS an mctl-api maintainer I WANT the smallest signing/JWKS/audience change
  stated against pinned code SO THAT I can ship it as an independently useful
  slice even if the gateway epic is not yet authorized.
- AS a security reviewer I WANT gateway-audience and API-audience tokens to be
  provably non-substitutable and every failure mode to be fail-closed in the
  reference model SO THAT the design's security claims are testable, not
  asserted.
- AS a future gateway implementer I WANT reference fixtures for tokens, policy,
  cache and failure cases SO THAT production acceptance tests can be derived
  from them.
- AS a tenant member I WANT the gateway to only narrow my downstream authority
  SO THAT a gateway bug can never let me act in a tenant I do not belong to.

## Acceptance criteria (EARS)

Deliverables and boundaries

- WHEN the spike is delivered THE SYSTEM SHALL add `docs/spikes/mcp-gateway-g0.md`
  (the report) and `docs/spikes/mcp-gateway-g0/` (reference model, fixtures,
  executable tests) to `mctlhq/.github`, and change no other repository.
- WHEN the report cites cross-repository code THE SYSTEM SHALL pin each
  repository to a 40-hex commit with a read date, and every proposed production
  hook SHALL cite `path:symbol` at that pin.
- WHILE the report states any fact THE SYSTEM SHALL label it as one of
  `[REF]` (reference-model/fixture evidence), `[CODE]` (read-only pinned
  production code), `[DOC]` (issue/plan text) or `unknown (not observed)`, and
  SHALL never present `[REF]` evidence as production proof.
- WHEN the report is complete THE SYSTEM SHALL record exactly one verdict from
  `GO`, `REVISE`, `NO-GO`, derived from an explicit table evaluating each of the
  seven GO criteria from the issue as `met | not met | met-with-condition`.
- IF any GO criterion is `not met` THEN THE SYSTEM SHALL NOT record `GO`.
- WHILE the verdict is not `REVISE` THE SYSTEM SHALL preserve accepted D1
  (Go + `github.com/mark3labs/mcp-go`).
- WHEN the spike is delivered THE SYSTEM SHALL register it in
  `roadmap/spikes/mcp-gateway-g0.yaml` (`kind: SpikeDefinition`,
  `lifecycle: active`, outcomes `GO`, `REVISE`, `NO_GO`, issue
  `mctlhq/.github#195`, `execution.devloop: true`) without a `decision` block,
  and list it under `# Spikes` in `AGENTS.md`.
- WHEN commits or the pull request reference the issue THE SYSTEM SHALL use
  `Refs #195`, never `Closes #195`.

D1 current-state / duplicate map

- WHEN the report describes related work THE SYSTEM SHALL map `.github#194`,
  `.github#184`, `.github#35`, `mctl-agents#242`, `mctl-api#377`,
  `mctl-api#488` and `mctl-api#747` to what each owns and what this spike reuses,
  and SHALL treat `mctl-api#377` as completed baseline, not an open dependency.

E1 identity and audience (G0.1, G0.2, G0.3)

- WHEN the reference gateway receives a token with `aud=https://mcp.mctl.ai`,
  a valid signature from a published JWKS key, valid `iss` and unexpired `exp`
  THE SYSTEM SHALL accept it and resolve `pid` to a canonical principal.
- IF the reference API resource receives a token whose `aud` is not
  `https://api.mctl.ai` THEN THE SYSTEM SHALL refuse it, even when `iss` and the
  signature are valid.
- IF a token has a wrong audience, is expired, has a bad signature, an unknown
  `kid`, `alg` other than the one pinned for the key, or `sub`/`pid` disagreement
  THEN THE SYSTEM SHALL refuse it at both the gateway and the API resource.
- WHEN the reference gateway performs an RFC 8693-shaped exchange
  (`grant_type=urn:ietf:params:oauth:grant-type:token-exchange`,
  `subject_token` = caller gateway token, `actor_token` = gateway service
  credential, `resource`/`audience` = `https://api.mctl.ai`) THE SYSTEM SHALL
  issue a token whose `sub`/`pid` equal the caller's, whose `act.sub` names the
  gateway service principal, whose `aud` is the API resource, whose `exp` is no
  later than the subject token's `exp` and no later than the configured exchange
  ceiling, and whose scope/authority is not wider than the subject token's.
- IF an exchange request names an actor that is not the registered gateway
  service principal, a subject token not addressed to the gateway, a target
  audience not on the allowed downstream list, or requests wider authority THEN
  THE SYSTEM SHALL refuse the exchange.
- WHILE the reference gateway forwards a call downstream THE SYSTEM SHALL send
  only the exchanged downstream-audience token and never the caller's gateway
  bearer.
- WHEN keys rotate in the reference JWKS THE SYSTEM SHALL accept tokens signed
  by any key still published and refuse tokens whose `kid` has been removed.
- WHEN the report maps E1 to production THE SYSTEM SHALL name, at the pinned
  `mctl-api` SHA, the hooks to change: `signJWT`/`verifyJWT`/`jwtPayload`/
  `IssueJWT`/`ValidateJWT` in `internal/auth/oauth_server.go`,
  `localOAuthProvider.Claims`/`Verify` in `internal/auth/provider_localoauth.go`,
  `handleOAuthToken` grant dispatch and `handleOAuthMeta` in
  `internal/api/oauth_handlers.go`, `handleProtectedResourceMeta` and the
  `.well-known` routes in `internal/api/router.go`, and the JWKS publication
  point.
- WHEN the report states the signing/audience slice THE SYSTEM SHALL say
  whether it is independently useful and SHALL record the ordering constraint
  that `aud` validation at `api.mctl.ai` must be deployed before any
  gateway-audience token is minted.

E2 tenant/tool isolation (G0.4)

- WHEN principal A (owner tenant-red, viewer tenant-blue) and principal B
  (developer tenant-blue) call reference `tools/list` THE SYSTEM SHALL return
  different effective catalogues computed as
  `ceiling(S) intersect union(grants matching P, tenant, S)`.
- IF a principal calls `tools/call` for a tool hidden from its catalogue by
  naming it directly THEN THE SYSTEM SHALL refuse it with the same error as an
  unknown tool.
- WHEN any `tools/call` is received THE SYSTEM SHALL re-evaluate effective
  policy and SHALL NOT use a prior `tools/list` result as permission.
- IF a grant names a tool not in the ceiling or not published by the downstream
  THEN THE SYSTEM SHALL treat it as inert (not grantable).
- IF a call targets tenant-blue using authority derived only from a tenant-red
  role THEN THE SYSTEM SHALL refuse it at the gateway and the reference
  downstream SHALL independently refuse it.
- WHEN the report describes cross-tenant refusal THE SYSTEM SHALL identify the
  authoritative production downstream check (`PrincipalAuthz.Apply` in
  `internal/auth/principal_authz.go`, `authorizeSubject` in
  `internal/api/tenant_authz_principal.go`, and the REST re-check that each MCP
  tool handler reaches with the caller's bearer).

E3 bypass model (G0.5)

- WHEN the report describes the migration state THE SYSTEM SHALL state that
  direct upstreams remain reachable and gateway policy is not a security
  perimeter in that state.
- WHEN the reference enforced-state fixture presents a gateway-audience token
  directly to the reference downstream THE SYSTEM SHALL refuse it, and WHEN it
  presents a correctly exchanged downstream-audience token THE SYSTEM SHALL
  accept it.
- WHILE describing E3 results THE SYSTEM SHALL state explicitly that fixture
  success is architecture evidence and that production refusal at
  `api.mctl.ai` is a post-G0 implementation acceptance criterion.

E4 revocation/cache bound

- WHEN the report states the revocation bound THE SYSTEM SHALL derive it from
  the policy cache hard TTL, the policy-version invalidation rule, call-time
  re-check and refresh-failure behaviour, as a formula
  (`R_max = hard_ttl + refresh_timeout`, unless the derivation in the report
  proves a tighter bound), not from a timing measurement.
- WHEN the reference model is driven by a fake clock across a grant removal THE
  SYSTEM SHALL refuse the removed tool no later than `R_max` after the removal
  becomes visible at the policy source, and SHALL refuse immediately when a newer
  policy version is observed.
- IF a token's remaining lifetime exceeds `R_max` THEN THE SYSTEM SHALL still
  enforce policy at `R_max`, because policy is re-checked on every call and is
  independent of token lifetime.

E5/G0.6 failure matrix

- IF the policy source is unavailable and no cached policy is within its hard
  TTL THEN THE SYSTEM SHALL fail `tools/list` and `tools/call` with a retriable
  error, never an empty list and never allow-all.
- IF the cached policy is past its hard TTL THEN THE SYSTEM SHALL behave as if
  the policy source were unavailable.
- IF token exchange is unavailable or returns an invalid token THEN THE SYSTEM
  SHALL fail that call with no fallback credential.
- IF a downstream is unavailable during `tools/call` THEN THE SYSTEM SHALL
  return an explicit unavailable error, never success.
- IF a downstream fails or returns a malformed catalogue during `tools/list`
  THEN THE SYSTEM SHALL omit it and list its server id in `_meta` as failed, and
  SHALL NOT present the aggregate as a complete catalogue.
- WHEN the failure matrix is recorded THE SYSTEM SHALL state, per fixture
  (policy unavailable, exchange unavailable, JWKS/key rotation, downstream
  unavailable, stale cache, malformed catalogue), the exact fail-open or
  fail-closed outcome, and every row where authorization is unknown SHALL be
  fail-closed.

G0.7 audit/correlation

- WHEN the reference gateway completes or refuses a `tools/call` THE SYSTEM
  SHALL emit one audit record carrying caller principal, tenant, gateway actor,
  server, tool, policy version, gateway request id, downstream request/audit id,
  decision and result status.
- WHILE emitting audit or log output THE SYSTEM SHALL NOT include any token,
  key, signature or request/result body; a test SHALL scan all captured output
  for every fixture credential and fail on any match.

G0.8 / E6 SDK comparison

- WHEN the report compares `github.com/mark3labs/mcp-go` with
  `modelcontextprotocol/go-sdk` THE SYSTEM SHALL cover stateless Streamable HTTP,
  proxy/aggregation ergonomics, tool filtering/interception, protocol-version
  support, auth middleware integration and maintenance risk, each with a cited
  source (pinned module version or upstream commit), and SHALL default to
  keeping `mcp-go`.
- WHEN the report states gateway overhead THE SYSTEM SHALL label it as a
  reference estimate/bound (component count, local benchmark of token verify,
  exchange and policy lookup on the reference model), never as a production
  measurement.

D6/D7 ownership and roadmap

- WHEN the report lists production gaps THE SYSTEM SHALL use the table
  `gap | repository | extend existing issue / create issue | dependency | priority`
  and SHALL list the `mctl-api` signing/JWKS/audience slice separately from the
  gateway epic.
- IF the verdict is `GO` THEN THE SYSTEM SHALL draft (text only) the epic and
  repository-owned children in the accepted G1 policy -> G2 Tier A -> G3
  downstream migration -> G4 cut-over -> G5 non-admin order, and SHALL NOT
  create issues, repositories or roadmap epics.
- IF the verdict is `REVISE` THEN THE SYSTEM SHALL propose only the design
  revision and independently useful focused follow-ups, and SHALL NOT draft the
  full epic.

## Out of scope

- Any change in `mctl-api`, `mctl-gitops`, `mctl-agents`, downstream MCP
  services, or creation of `mctlhq/mctl-mcp-gateway`.
- Production JWKS, token exchange, audience validation, endpoint cut-over,
  Portal removal, direct-endpoint removal, tenant-authorization changes.
- Editing the accepted design `docs/plans/mcp-gateway.md` (revisions, if any,
  are proposed in the report for owner approval).
- Creating follow-up issues, roadmap epics or work items; recording the
  verdict in the `SpikeDefinition` `decision` block (the owner does that).
- Reimplementing `CapabilityGateway`, completing `mctl-api#488` or `#747`,
  context-efficiency benchmarking (`mctl-agents#597`).
- A full alternate implementation on `modelcontextprotocol/go-sdk`, or any
  TypeScript/Bun/Python gateway.
- Claims of Tasks/Apps/elicitation compatibility.
- Production revocation SLAs or production latency figures.

## Open questions

- The accepted plan's G0 row (`docs/plans/mcp-gateway.md`, Migration table)
  says G0 delivers "mctl-api JWKS signing and per-resource audience behind a
  flag; gateway prototype in front of `api` only" and is done when "a token for
  `aud=mcp.mctl.ai` reaches mctl-api tools through the gateway". The issue
  narrows G0 to a `.github`-only reference proof. This proposal follows the
  issue; the report will flag the plan-row mismatch as a documentation
  revision for the owner, not silently edit the plan.
- Reference-model language: this proposal uses Go standard library only
  (crypto/ed25519, net/http/httptest) in its own module to stay aligned with D1
  and get real asymmetric signatures without third-party dependencies. If the
  owner prefers the Python stdlib convention of
  `docs/spikes/security-finding-lifecycle/`, the model can be ported, but
  asymmetric signing would then have to be hand-rolled.
- The signing algorithm for the production slice (EdDSA vs ES256 vs RS256) is
  left for the report to recommend; MCP client and downstream library support
  (for example coolify's verifier) is `unknown (not observed)` until checked.
- Whether `mctl-api` should accept RFC 8707 `resource` on the existing
  authorization-code/refresh grants (today `handleOAuthToken` ignores it) or
  infer audience from the client registration is a contract choice the report
  must recommend; both are modelled.
- `mctl_get_service_config` for `mctl-api` itself was not observed: `mctl-api`
  is not a catalogue service in the `admins` tenant listing, so its deployed
  `TENANT_AUTHZ_MODE` and access-token TTL are taken from issue text
  (`mctl-api#377` completed) and code defaults (`AccessTokenTTL` default 1h),
  not from deployed config.
