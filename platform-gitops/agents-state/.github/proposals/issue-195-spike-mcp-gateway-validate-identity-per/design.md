# Design: issue-195-spike-mcp-gateway-validate-identity-per

## Current state

### In `mctlhq/.github` (clone at `51694fd`)

- `docs/plans/mcp-gateway.md` is the accepted design (D1-D5, 2026-10-17). It
  already fixes: caller token with `aud=https://mcp.mctl.ai` issued by mctl-api
  (D2); policy `effective(P, S) = ceiling(S) ∩ (⋃ grants matching P, S)` with no
  deny rules, grants in mctl-api Postgres and the ceiling in gitops (D3);
  `tools/call` re-checks policy and a denied call returns the unknown-tool
  error; failure table (unreachable policy, hard TTL, partial `tools/list` with
  `_meta`, ceiling missing, mint failure); Tier A/B/C downstream credentials
  with RFC 8693 exchange at the mctl-api token endpoint; audit into mctl-api
  `audit_events` with `via_principal_id`; Go + mcp-go (D1); migration G0-G5.
  Its G0 row includes production mctl-api JWKS work, which the issue now
  scopes out of this DevLoop.
- `docs/spikes/security-finding-lifecycle.md` + `docs/spikes/security-finding-lifecycle/`
  (`model.py`, `fixtures/*.json`, `tests/test_lifecycle.py`) is the house
  pattern for a spike: a report with evidence pins (40-hex SHAs, read date),
  `[I]`/`[P]` evidence tags, explicit "non-normative reference model" header,
  and stdlib unit tests over synthetic fixtures.
- `.github/workflows/workflow-tests.yml` runs that spike's tests on PRs/pushes
  touching `docs/spikes/security-finding-lifecycle/**`
  (`python3 -m unittest discover -s docs/spikes/security-finding-lifecycle/tests -v`).
- `roadmap/spikes/*.yaml` hold `kind: SpikeDefinition` manifests validated by
  `roadmap/schemas/spike-definition.schema.json` (outcome tokens must match
  `^[A-Z][A-Z0-9_]*$`, so `NO-GO` is encoded as `NO_GO`; `lifecycle: active`
  requires `timebox.decisionBy`; a `decision` block is allowed only when
  `decided`). `roadmap/README.md` validates them with
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`. No
  manifest exists for #195 yet.
- `AGENTS.md` indexes spikes under `# Spikes`.
- `roadmap/epics/enterprise-mcp.yaml` holds the paused gateway phase
  (`gateway`, `gateway-dlp-result`, `gateway-hardening`) that D4 supersedes.

### In `mctlhq/mctl-api` (read-only, pinned `98bbf8c61006f1d70762c1ae2a9d3747c67ef241`, read 2026-10-25)

- `go.mod`: `github.com/mark3labs/mcp-go v1.0.0` (D1 baseline version for E6).
- `internal/auth/oauth_server.go`:
  - `OAuthServer.JWTSecret` — "HMAC-SHA256 signing key for issued access tokens".
  - `jwtPayload{iss, sub, pid, groups, iat, exp}` — **no `aud`, no `kid`, no `act`**.
  - `signJWT` uses a constant header `{"alg":"HS256","typ":"JWT"}`.
  - `verifyJWT(token, secret, expectedIssuer)` checks HMAC, `iss`, `exp` only.
  - `IssueJWT(login, principalID, groups)` sets `sub` = login or principal id,
    `pid` = principal, TTL default 1h.
  - `ValidateJWT` in `PrincipalMode` requires a valid `pid` and `sub == pid` for
    principal-only subjects (mctl-api#377 baseline).
  - Conclusion `[CODE]`: a gateway-audience token from the same issuer would be
    accepted at `api.mctl.ai` today; audience validation must ship before any
    second audience is minted.
- `internal/auth/provider_localoauth.go`: `localOAuthProvider.Claims` routes a
  JWT by issuer only; `Verify` calls `ValidateJWT`. This is the per-provider
  verification hook where audience must be enforced.
- `internal/api/oauth_handlers.go`: `handleOAuthToken` supports only
  `authorization_code` and `refresh_token` (`unsupported_grant_type`
  otherwise); no RFC 8707 `resource` handling; `handleProtectedResourceMeta`
  publishes RFC 9728 metadata with `resource` = base or base+`/mcp`.
- `internal/api/router.go`: `.well-known/oauth-protected-resource[/mcp]`
  routes; `/mcp` served by `NewStreamableHTTPHandler`; no JWKS route.
- `internal/mcp/server.go`: `NewStreamableHTTPHandler` uses
  `server.WithStateLess(true)`; `NewMCPServer` uses
  `server.WithToolFilter(s.ownerOnlyToolFilter)` and
  `server.WithToolHandlerMiddleware(s.ownerOnlyCallMiddleware)` ("mcp-go applies
  the filter to tools/list and again to tools/call").
- `internal/mcp/owner_tools.go`: `ownerOnlyTools` map and
  `ownerOnlyCallMiddleware` distinguish "decided no" (unknown-tool error) from
  "could not verify" — the precedent for the gateway's deny/unavailable split.
- `internal/auth/principal_authz.go` `PrincipalAuthz.Apply` and
  `internal/api/tenant_authz_principal.go` `authorizeSubject` — the
  authoritative per-principal tenant decision (refuse with 503 when undecidable).
- `internal/auth/agent.go` — agent run tokens (`art_`) carry no subject;
  delegation is a separate `X-MCTL-On-Behalf-Of` mechanism (mctl-api#376/#747
  lineage). Related precedent for actor/subject separation, not the gateway
  exchange contract.

Deployed state checked:

- `mctl_list_services(team=admins)` — 7 catalogue services (mctl-agents-worker
  x3, mctl-design, mctl-docs, mctl-web, umami), all Synced. No gateway service
  and no `mctl-api` catalogue entry in that tenant, so mctl-api's deployed env
  (`TENANT_AUTHZ_MODE`, token TTL) was **not observed**; see Open questions.
- `$MCTL_GITOPS_ROOT` checkout at mctl-gitops `d1661f7100608af22c29dbda02a0a367c4d3218e`:
  `services/` has tenants `admins`, `karabu`, `labs`. `grep mcp.mctl.ai` hits
  `services/labs/mctl-telegram/values.yaml:151` (`OAUTH_DCR_REDIRECT_URIS`
  includes `https://mcp.mctl.ai/servers-callback` and the Cloudflare
  `ai-controls/mcp-server/oauth-callback/tg` URL), confirming tg is a direct
  OAuth upstream of the Portal today; `services/labs/coolify-mcp/values.yaml`
  and `services/labs/seerrsense/values.yaml` also exist as separately reachable
  hosts (`labs-coolify-mcp.mctl.ai`). No `mcp-gateway` service exists.
- Cloudflare Portal configuration (`infrastructure/cloudflare/portal/`) is not
  under `$MCTL_GITOPS_ROOT` (`platform-gitops/` only) and was not observed here.

## Proposed solution

A documentation-and-proof change confined to `mctlhq/.github`:

```
docs/spikes/mcp-gateway-g0.md                 report (D1-D8, verdict)
docs/spikes/mcp-gateway-g0/
  README.md                                   how to run; non-normative banner
  go.mod                                      module mctl.ai/spikes/mcpgatewayg0, go 1.22, NO requires
  model/
    token.go        JWS (EdDSA) sign/verify, JWKS, kid rotation, claim checks
    exchange.go     RFC 8693-shaped token-exchange endpoint model
    policy.go       ceiling ∩ grants, tenant roles, versioned cache, fake clock
    gateway.go      tools/list aggregation, tools/call re-check, forwarding
    downstream.go   reference "api" resource: aud check + independent tenant authz
    audit.go        correlation record + redacting sink
  fixtures/
    principals.json   prn_fixture_a (owner tenant-red, viewer tenant-blue),
                      prn_fixture_b (developer tenant-blue), gateway service principal
    ceiling.json      per-server publishable tool names (api, tg)
    grants.json       tenant-role and principal grants, policy version
    catalogues/*.json downstream tools/list fixtures incl. malformed one
    keys.json         deterministic ed25519 seeds (fixture-only, labelled)
  model_test.go     E1-E5 + G0.7 tests (table-driven)
  bench_test.go     E6 reference overhead benchmarks
roadmap/spikes/mcp-gateway-g0.yaml            SpikeDefinition, lifecycle: active
AGENTS.md                                     add spike index entry
.github/workflows/workflow-tests.yml          add path filter + `go test` step
```

### Why Go stdlib for the model

D1 is Go; Go's standard library provides real Ed25519 (`crypto/ed25519`),
JSON and `net/http/httptest`, so the model exercises genuine asymmetric
signatures, JWKS and HTTP round-trips with **zero third-party modules** (no
`go.sum`, nothing for Dependabot in a docs repo). The model does not import
mcp-go: the MCP framing (`tools/list`, `tools/call`, `_meta`) is modelled as
plain JSON-RPC structs because the spike proves the authorization boundary, not
the library. E6 evaluates mcp-go vs go-sdk by documented API inspection at
pinned versions, as the issue allows ("No full alternate implementation").

### D2 identity/token contract (modelled, proposed for production)

Caller token (issued by mctl-api AS, verified offline via JWKS):

```
header: {alg: EdDSA, kid: <key id>, typ: at+jwt}
claims: iss=https://api.mctl.ai, aud=https://mcp.mctl.ai, sub=<login|pid>,
        pid=prn_..., iat, exp, client_id, jti
```

Exchanged downstream token (RFC 8693 at the mctl-api token endpoint):

```
request: grant_type=urn:ietf:params:oauth:grant-type:token-exchange
         subject_token=<caller token>  subject_token_type=...:access_token
         actor_token=<gateway service credential>
         resource=https://api.mctl.ai  (RFC 8707)
issued:  aud=https://api.mctl.ai, sub/pid = caller's, act={sub: prn_gateway},
         exp = min(subject.exp, now + exchange_ttl_max), no groups/scope beyond subject's
```

Verification rules (both gateway and reference downstream): `alg` must equal
the key's published `alg`; `kid` must be in the current JWKS; `iss` exact;
`aud` must contain this resource's identifier exactly; `exp`/`iat` with bounded
skew; `sub`/`pid` consistency as in `ValidateJWT` principal mode. The exchange
endpoint refuses: actor not the registered gateway principal, subject token
`aud` not the gateway, target resource not in the allowed downstream list,
subject token invalid/expired, and any request for wider scope. The gateway
never forwards the caller bearer: the forwarder takes only an exchanged token
type, enforced by a distinct Go type and asserted by a test that inspects the
downstream's received `Authorization` header.

Production mapping (report section D2, `[CODE]` at `api@98bbf8c`): add `aud`/
`kid`/`act` to `jwtPayload`; replace `signJWT`/`verifyJWT` HS256 with
asymmetric signing behind a flag, keeping HS256 verification during a
dual-accept window; enforce audience in `verifyJWT` (or
`localOAuthProvider.Verify`) for the resource `https://api.mctl.ai` with a
compatibility rule for existing aud-less tokens until their 1h TTL drains;
publish `/.well-known/jwks.json` and `jwks_uri` in `handleOAuthMeta`; accept
`resource` in `handleOAuthToken` for audience selection; add the
token-exchange grant case restricted to the gateway service principal.
Ordering constraint: audience enforcement at `api.mctl.ai` must be live before
mctl-api mints any `aud=https://mcp.mctl.ai` token, otherwise the new token is
a valid API bearer (today's `verifyJWT` ignores `aud`). The signing/JWKS/audience
slice is evaluated as independently useful (offline verification by coolify
and other downstreams, removal of shared-secret risk) regardless of verdict.

### D3 policy model

Exactly the accepted D3 formula, keyed additionally by tenant:
`effective(P, T, S) = ceiling(S) ∩ ⋃ {grants g : g.subject matches P or P's role in T, g.server = S}`.
Tools absent from `ceiling(S)` or from the downstream's published catalogue
are inert. Tool names are namespaced `<server>_<tool>` as the Portal does
today, compatible with `mctl-agents#242` capability identity (server-qualified
names; discovery narrows, never grants). `tools/list` filters for exposure;
`tools/call` re-resolves the prefix and re-evaluates `effective` every time.

Cache/version contract: the policy snapshot carries `version` (monotonic) and
`digest`, `fetched_at`, `soft_ttl` (refresh in background) and `hard_ttl`
(refuse beyond). A response with a newer version replaces the snapshot
immediately; an older version is ignored. Refresh failure past `hard_ttl`
means fail-closed. Designed revocation bound:
`R_max = hard_ttl + refresh_timeout` from the moment the policy source
publishes the change (the report derives it and states assumptions: monotonic
clock, no version regression). Token lifetime does not extend revocation of a
tool grant because policy is checked per call; token revocation itself is
bounded by access-token TTL and is reported separately.

### D4 direct-path migration model

Three states, each with what is and is not enforced:

1. Today/migration `[CODE]`+`[DOC]`: downstreams reachable directly with
   their own OAuth; gateway policy is presentation + narrowing only, not a
   perimeter; `api.mctl.ai` accepts any same-issuer token (no `aud`).
2. Audience-enforced api `[REF]` modelled: `api.mctl.ai` accepts only
   `aud=https://api.mctl.ai`; the gateway token is refused directly; exchanged
   token accepted. Direct user tokens for `api` remain valid (the API is still
   a first-class resource), so the gateway narrows only gateway-routed traffic.
3. Enforced Tier A `[REF]`: per the plan, downstream accepts only mctl-issued
   tokens for its audience; weaker direct OAuth doors closed in G3.
Production proof of (2)/(3) is deferred to the post-G0 implementation's
acceptance criteria.

### Failure matrix, audit, verdict

The report's E5 table lists each fixture with outcome and the test that proves
it. Audit records use a struct with no credential/body fields; the redacting
sink additionally scans every emitted line for fixture secrets (token strings,
key seeds, signatures) and the test fails on any hit. The gateway request id
is minted per call and passed downstream as `X-MCTL-Edge-Request-Id` with
`X-MCTL-Edge-Route: gateway`; the reference downstream echoes its own audit id
which the gateway records (plan's mctl-telegram#617 correlation contract).

Verdict section: a 7-row table of the issue's GO criteria with evidence links
and `met | not met | met-with-condition`, then exactly one of
`GO | REVISE | NO-GO`, followed by D6 ownership table and D7 roadmap draft
appropriate to the verdict. The report must also list any accepted-design
assumption that the evidence contradicts (for example the plan's G0 row scope
or "removing a grant hides the tool within one cache TTL" vs the derived
`R_max`), because any such contradiction pushes the verdict to `REVISE`.

## Alternatives

1. **Python stdlib model next to `security-finding-lifecycle`.** Matches the
   existing CI step and house style, but Python's stdlib has no asymmetric
   signature primitive; the model would hand-roll RSA or fall back to HMAC,
   which would fail to demonstrate the very property (offline verification
   without a shared secret) G0.3 is about. Adding `cryptography` to
   `roadmap/requirements.txt` widens the shared dependency set for one spike.
   Dropped in favour of Go stdlib.
2. **Go model built on mcp-go (or both SDKs).** Most realistic for E6, but adds
   third-party modules, `go.sum` and dependency upkeep to a docs/governance
   repo, and the issue explicitly does not require an alternate
   implementation. The authorization boundary is independent of the MCP
   library. Dropped; E6 is done by pinned API inspection plus the reference
   overhead bound.
3. **Prototype against a real mctl-api build (fork/branch with JWKS behind a
   flag), as the plan's original G0 row describes.** Strongest evidence, but
   violates the issue's DevLoop boundary (no production changes outside
   `.github`). Dropped; recorded as a plan/issue scope mismatch for the owner.

## Platform impact

- Migrations: none. No runtime, service, tenant or gitops change; the only
  CI change is an extra test step in `workflow-tests.yml` limited by path
  filter to `docs/spikes/mcp-gateway-g0/**`.
- Backward compatibility: `roadmap/spikes/mcp-gateway-g0.yaml` must pass
  `roadmap/scripts/validate.py`; the `#195` issue binding must stay unique
  across spikes and must not be an epic root or epic work item. `roadmap-publish`
  will start publishing an active spike; nothing else changes.
- Resource impact: CI only (one `go test` run, seconds). No cluster usage.
- Risks and mitigations:
  - Reference evidence mistaken for production proof -> mandatory
    `[REF]`/`[CODE]`/`[DOC]` tags, a non-claims header, and explicit
    deferral statements in E3/E4/E6.
  - Fixture keys mistaken for real secrets by scanners -> deterministic seeds
    named `fixture-only` in `keys.json`, documented in README; no production
    issuer URL is used as a signing identity in fixtures beyond the `iss`
    string.
  - Stale code pins -> every `[CODE]` row carries the SHA and read date;
    implementer re-pins at write time if mctl-api has moved and notes deltas.
  - Go toolchain availability in CI -> use `actions/setup-go` pinned by full
    commit SHA (repo convention, see `actions/checkout@3d3c42e...` in
    `workflow-tests.yml`) with `go-version-file`.
  - Verdict pressure to `GO` from incident fatigue -> verdict computed from the
    seven-criterion table; `needs_reauth` incidents cited only as supporting
    evidence.
