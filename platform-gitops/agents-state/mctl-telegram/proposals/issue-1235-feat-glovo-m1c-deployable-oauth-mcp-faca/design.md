# Design: issue-1235-feat-glovo-m1c-deployable-oauth-mcp-faca

## Current state

What exists in the clone (commit `7a372c0`, "docs(glovo): multi-tenant MCP M0 contracts
and threat model #1233"):

- `docs/contracts/glovo-mcp-tools.json` (`$id` `https://mctl.ai/contracts/glovo-mcp-tools/v1alpha1`):
  the protected resource `https://glovo.mctl.ai/mcp`, scopes `glovo:read` and
  `glovo:basket:prepare`, and seven closed tools with `required_scope`, `effect`, and
  input/output schemas, every object marked `additionalProperties: false`.
- `docs/glovo_contract_test.go`: `TestGlovoContract` pins the tool allowlist
  (`glovoToolAllowlist`), forbidden input properties (`glovoForbiddenProps`: tenant,
  principal, url, token, ...), forbidden names (`place|pay|checkout|purchase|submit_order`).
  `TestGlovoDocsHaveNoCredentialShapes` scans Glovo docs for JWT/cookie/hex/base64.
- `docs/adr/0010-glovo-multitenant-connections.md`: system boundary (facade holds no
  secrets and has no Temporal client; mctl-api is the only Temporal client), identity
  chain, `gcn_` connection state machine, `aar_` approval, typed refusal codes
  (`not_authorized`, `no_tenant`, `ambiguous_tenant`, `scope_unsupported`,
  `not_in_pilot`, `no_install`, `stale_install`, `no_connection`,
  `connection_revoked`, `connection_expired`, `not_found`), gates G0-G6 and tests T0-T16.
- `docs/agent-runtime/glovo-threat-model.md` (TM1-TM16) and
  `docs/contracts/glovo-checkout-handoff.md` (order states, fingerprint, handoff token,
  `OUTCOME_UNKNOWN`).
- `test/glovo-poc/` is a nested Go module (`go.mod` with Temporal SDK). It has an
  in-memory mctl-api stand-in (`controlplane/controlplane.go`: `CP.Resolve`,
  `CP.Revalidate`, typed errors), a fake provider (`fakeglovo/`) and a leak scanner
  (`leakcheck/leakcheck.go`). CI vets/tests it separately (`.github/workflows/build.yml`
  steps "Vet/Test Glovo PoC nested module").

How the existing Telegram server does the same things (patterns to reuse, not code to
share at runtime):

- MCP transport: `internal/mcp/server.go` `(*Server).HTTPHandler` builds
  `mcpserver.NewStreamableHTTPServer(..., mcpserver.WithHTTPContextFunc(httpContext))`
  with `github.com/mark3labs/mcp-go v1.4.0`.
- RFC 9728 metadata: `cmd/server/main.go` `protectedResource` /
  `protectedResourceMetadata`, mounted at `/.well-known/oauth-protected-resource` and
  the `+cfg.MCPPath` alias; tested in `cmd/server/protected_resource_test.go`.
- Router and middleware: chi (`github.com/go-chi/chi/v5`), `middleware.RealIP`,
  `GetHead`, `metrics.Registry.HTTPMiddleware` (`internal/metrics/middleware.go`),
  `Recoverer`, `Timeout`; `/healthz`, `/readyz`, `/metrics` (with CIDR allow) and
  `srv.Shutdown(shutCtx)` in `cmd/server/main.go`.
- Token verification: `internal/auth/sharedhmac/verifier.go` (HS256 with shared
  secret, phased `checkAudience`) and `internal/auth/localjwt` (the service is its own
  issuer). Neither fits: the facade must not hold a signing/verifying secret and is not
  an issuer. `github.com/go-jose/go-jose/v4` and `github.com/coreos/go-oidc/v3` are
  already in `go.mod`.
- Audit/OTel: `internal/mcp/audit_span.go` `auditSpanAttributes` (no arguments or
  values, only ids/tool/status); `go.opentelemetry.io/otel` v1.47.0.
- Redaction: `internal/audit/redact.go` `NewRedactingHandler` slog wrapper with a
  sensitive-field list.
- Strict JSON: `internal/jsonstrict` (`RejectDuplicateKeys`, unknown/trailing data);
  schema validation library `github.com/santhosh-tekuri/jsonschema/v6` is in `go.mod`.
- Separate images: `Dockerfile.agent-worker` is the precedent for a second binary
  with its own image from this repo; `.github/workflows/release-please.yml` job
  `agent-worker-release` dispatches it to `mctl-gitops` `release-deploy.yaml` only if
  `services/labs/agent-worker-managed/values.yaml` exists (guard script
  `.github/scripts/gitops-values-present.sh`), otherwise emits a skip notice.

Deployed state checked:
- `mctl_list_services(team=labs)` (ArgoCD ok, complete=true, 21 services): `mctl-telegram`
  `ghcr.io/mctlhq/mctl-telegram:0.135.0` on `tg.mctl.ai`, `mctl-telegram-preview` on
  `tg-preview.mctl.ai`; no Glovo service and no `glovo.mctl.ai` host exists.
- `$MCTL_GITOPS_ROOT` `services/` (tenants admins, karabu, labs, namax66) and
  `grep -ri glovo services tenants`: no match. `services/labs/mctl-telegram/values.yaml`:
  `image.repository ghcr.io/mctlhq/mctl-telegram`, tag `0.135.0`.
- `tenants/` lists admins, commerce-proof, erpact, karabu, labs, mctl, namax66. Not used:
  the facade never derives tenant from the hosting namespace.
- mctl-api source and its authorization-server behaviour were not observable from
  this run (no clone, no tool exposes it); recorded under `## Open questions` in
  requirements.md, and treated as unknown, not absent.

## Proposed solution

### Shape

A new, independent executable and image in the same Go module:

```
cmd/glovo-mcp/main.go                  entrypoint, config, router, shutdown
internal/glovo/config/                 env parsing (GLOVO_MCP_*), validation, fail-fast
internal/glovo/authn/                  JWKS verifier + protected-resource metadata
internal/glovo/mctlapi/                Client interface + HTTP client (wire v1alpha1)
internal/glovo/mctlapi/fakeapi/        fake mctl-api HTTP harness (tests + local run)
internal/glovo/tools/                  contract loader, schema validation, handlers
internal/glovo/facade/                 chi router, middleware, limits, audit, metrics
internal/glovo/contract/               go:embed copy check of docs/contracts/glovo-mcp-tools.json
Dockerfile.glovo-mcp                   multistage, distroless/alpine non-root
docs/contracts/glovo-facade-mctl-api.md   frozen wire protocol v1alpha1
docs/glovo-mcp.md                      runbook: config, probes, kill switch
```

`internal/glovo/...` imports nothing from `internal/telegram`, `internal/oauth`,
`internal/db`, `internal/bridge` or `cmd/server`. A test
(`internal/glovo/imports_test.go`, using `go list -deps`) enforces this, and enforces
that no `go.temporal.io/*` package is in the binary's dependency graph. The reverse
holds too: `cmd/server` does not import `internal/glovo`, so the tg.mctl.ai binary,
descriptors and portal allowlist do not change.

### Frozen identifiers

- Image: `ghcr.io/mctlhq/mctl-glovo-mcp`, tag format `MAJOR.MINOR.PATCH` (shared with
  the repo release) and `main-<sha7>` for CI-only builds. OCI title `mctl-glovo-mcp`.
- Binary: `/usr/local/bin/mctl-glovo-mcp`; MCP `serverInfo.name` `mctl-glovo-mcp`.
- Prospective gitops component (not created here): `labs/glovo-mcp`.
- Routes: `/mcp` (POST/GET/DELETE per Streamable HTTP), `/.well-known/oauth-protected-resource`
  and `/.well-known/oauth-protected-resource/mcp`, `/healthz`, `/readyz`, `/metrics`
  (CIDR-restricted like `metricsHandler`). Nothing else; unknown paths 404.
- MCP protocol versions accepted: pinned list in `internal/glovo/facade`
  (`2025-06-18`, `2025-03-26`), whatever mcp-go v1.4.0 negotiates within it; a test
  asserts the list so a library bump cannot silently widen it.
- Wire protocol `glovo-facade-mctl-api/v1alpha1` (below).

### Configuration (`internal/glovo/config`)

| Env | Default | Notes |
| --- | --- | --- |
| `GLOVO_MCP_ENABLED` | `false` | kill switch; false => `/mcp` 503, readiness false |
| `GLOVO_MCP_PUBLIC_BASE_URL` | none | e.g. `https://glovo.mctl.ai` |
| `GLOVO_MCP_RESOURCE` | `<base>/mcp` | must equal contract `protected_resource.resource` in prod mode |
| `GLOVO_MCP_ISSUER` | none | exact `iss` |
| `GLOVO_MCP_JWKS_URL` | none | https only (http allowed only with `GLOVO_MCP_DEV=true` on loopback) |
| `GLOVO_MCP_AUTHORIZATION_SERVER` | `= ISSUER` | advertised in PRM |
| `GLOVO_MCP_API_BASE_URL` | none | mctl-api base; https unless dev loopback |
| `GLOVO_MCP_API_CREDENTIAL_FILE` | none | path to the facade's workload credential (mounted file, re-read on change) |
| `GLOVO_MCP_RATE_PER_MIN` / `_BURST` / `_MAX_INFLIGHT` | 30 / 10 / 64 | |
| `GLOVO_MCP_METRICS_ALLOW_CIDR` | `127.0.0.1/32` | |

Startup fails (non-zero exit) on missing or malformed values when enabled. No env
names a tenant.

### Request pipeline

```
chi: RealIP -> request id -> metrics -> Recoverer -> MaxBytes(64 KiB) -> Timeout(30s)
  /mcp: enabled? -> bearer authn (local, no network except cached JWKS)
        -> per-principal rate limit + global inflight semaphore
        -> mcp-go StreamableHTTPServer (WithHTTPContextFunc puts Principal in ctx)
        -> tool handler: strict arg validation -> scope check -> mctlapi.Resolve
           -> mctlapi.<operation> -> output schema validation -> result
        -> audit record + span
```

Authn (`internal/glovo/authn.Verifier`): `go-jose/v4` parses the compact JWS with
`jose.ParseSigned(tok, []jose.SignatureAlgorithm{RS256, ES256})`; keys come from a
JWKS cache (TTL 10 min, refetch on unknown `kid` at most once per 30 s, response cap
64 KiB). Claims checked: `iss` exact; `aud` (string or array) contains exactly
`GLOVO_MCP_RESOURCE`; `exp` required; `nbf`/`iat` skew 60 s; `sub` non-empty; `scope`
space-separated, intersected with the two Glovo scopes; `mctl_tenant` optional string;
`jti` optional (forwarded for revocation checks). The token must arrive only in the
`Authorization` header; a token in the query string (`access_token=`) or form body is
refused with 400 and the query is never logged. On failure: 401 with
`WWW-Authenticate: Bearer error="invalid_token", resource_metadata="..."`; on missing
scope: 403 `error="insufficient_scope", scope="glovo:read glovo:basket:prepare"`.

The result is a `Principal{Subject, Tenant, Scopes, TokenHash}`; the raw token is kept
in an unexported context value used only by `mctlapi` to forward it, never by handlers.

Protected-resource metadata (`authn.MetadataHandler`): `resource`,
`authorization_servers`, `scopes_supported` (read from the embedded contract, not a
second list), `bearer_methods_supported: ["header"]`, `resource_name`. The
authorization-server discovery (`/.well-known/oauth-authorization-server`) is served by
mctl-api, not the facade; the facade only points to it. This is the MCP 2025-06-18
authorization model (RS separate from AS) and matches how Claude/ChatGPT connectors
discover tg.mctl.ai.

### Tools (`internal/glovo/tools`)

The contract JSON is embedded (`//go:embed` of a copy in `internal/glovo/contract`,
with a test asserting byte equality with `docs/contracts/glovo-mcp-tools.json`). At
startup each tool's `input_schema`/`output_schema` is compiled with
`santhosh-tekuri/jsonschema/v6`; tools are registered with `mcplib.NewToolWithRawSchema`
(raw input schema, output schema attached) so the descriptor served equals the
contract. Argument bytes are first passed through `jsonstrict.RejectDuplicateKeys` and
then schema-validated; any failure is `invalid_arguments` without echoing the value.

Every handler follows one template:

```go
func (h *Handlers) getBasket(ctx context.Context, req mcplib.CallToolRequest) (*mcplib.CallToolResult, error) {
    p := authn.FromContext(ctx)                       // never from args
    if err := requireScope(p, "glovo:read"); err != nil { return refusal(err) }
    scope, err := h.api.Resolve(ctx, p)              // checkpoint 1, every call
    if err != nil { return refusal(err) }             // typed code, no effect called
    out, err := h.api.GetBasket(ctx, scope)
    if err != nil { return refusal(err) }
    return h.result(ctx, "glovo_get_basket", out)    // output schema validation
}
```

| Tool | Scope | mctl-api call(s) | Effect class |
| --- | --- | --- | --- |
| `glovo_auth_status` | read | `GET connection` | read |
| `glovo_connect_account` | prepare | `POST connections` (fake provider only, idempotency key) | creates pending `gcn_` |
| `glovo_get_order_history` | read | `GET orders?limit&cursor` (cursor opaque, passed through as body field, not query) | read |
| `glovo_preview_reorder` | read | `POST previews` with `order_ref` (read semantics, no basket write) | read |
| `glovo_get_basket` | read | `GET basket` | read |
| `glovo_prepare_order` | prepare | `POST orders:prepare` -> returns `aar_` consent id | prepare_only |
| `glovo_order_status` | read | `GET orders/{order_id}` | read |

Refusals map to the ADR codes plus facade-local `invalid_arguments`, `rate_limited`,
`upstream_unavailable`, `upstream_invalid`. They are returned as MCP tool results
with `isError: true` and `structuredContent: {"error": "<code>"}`, never with upstream
text. Foreign and missing ids both yield `not_found` (mctl-api decides; the facade
never distinguishes). The facade never fabricates or caches state; it is stateless
apart from the JWKS cache and rate-limit buckets.

`glovo_prepare_order` creates or returns the `aar_` request through mctl-api; there is
no tool that reads a receipt, approves or consumes one. `hir_` ids are not accepted as
input anywhere (no schema field for them), and a test asserts mctl-api fake receipts
are only consumable through the fake's separate human endpoint, never via `/mcp`.

### Wire protocol `glovo-facade-mctl-api/v1alpha1` (frozen here)

Documented in `docs/contracts/glovo-facade-mctl-api.md` and pinned by
`internal/glovo/mctlapi/wire_test.go` (golden request/response fixtures shared by the
real client and `fakeapi`). All under `POST|GET {API_BASE}/api/v1/assistants/glovo/v1alpha1/...`:

- Headers on every call: `Authorization: Bearer <facade workload credential>`,
  `X-Mctl-Subject-Token: <user access token, forwarded for re-verification>`,
  `X-Mctl-Selected-Tenant: <mctl_tenant claim or empty>`, `X-Request-Id`,
  `Content-Type: application/json`. No query strings at all; ids travel in JSON bodies or path segments of opaque ids.
- `POST /resolve` `{}` -> `200 {"scope_ref":"gsc_...","tenant":"<name>","expires_at"}`
  or `403 {"error":"no_tenant|ambiguous_tenant|scope_unsupported|not_in_pilot|not_authorized|no_install|stale_install"}`.
  mctl-api re-verifies the subject token (signature, `aud`, revocation), membership and
  allowlist. `scope_ref` is a short-lived (60 s) opaque handle bound to the subject
  token hash and is passed as `X-Mctl-Scope-Ref` to the next call; mctl-api
  re-checks it, so the facade cannot reuse it for another principal.
- `GET /connection`, `POST /connections {"idempotency_key"}`, `POST /orders:list
  {"limit","cursor"}`, `POST /previews {"order_ref"}`, `GET /basket`,
  `POST /orders:prepare {"preview_id","idempotency_key"}`, `GET /orders/{order_id}`.
  Response bodies are exactly the contract output object; error bodies are
  `{"error":"<ADR code>"}`.
- Timeouts: 5 s per call, no retry on POST except `connections` and `orders:prepare`
  (idempotency key) once on connection reset; reads retried once with jitter.

The facade forwards the user token rather than asserting identity, so a compromised
facade credential alone cannot act as a user (TM3). The client is behind an interface
(`mctlapi.Client`) so RFC 8693 token exchange can replace the header later.

### Fake mctl-api harness (`internal/glovo/mctlapi/fakeapi`)

An `httptest`-servable implementation of v1alpha1 with: an in-memory RSA JWKS issuer
(mints tokens for tests), tenants/members/allowlist/installs, per-principal `gcn_`
connections, orders, previews, `aar_` requests with a separate
`POST /_fake/approve/{aar}` human endpoint, `hir_` records, revocation, and a call
recorder (to assert "no effect endpoint invoked"). A tiny `cmd/glovo-mcp-fakeapi`
(build tag `glovofake`, never in the image) runs it locally so
`cmd/glovo-mcp` plus a real MCP client (`cmd/mcpprobe`, or mcp-go client) can be
exercised end to end. Personas follow CLAUDE.md: Alice and Bob in tenant
`team-alpha`, Carol in `team-beta`, Dana not in the allowlist. Synthetic only.

### Observability

- Prometheus (own registry, not `internal/metrics`'s Telegram registry):
  `glovo_mcp_http_requests_total{route,code}`, `glovo_mcp_tool_calls_total{tool,outcome}`,
  `glovo_mcp_tool_duration_seconds{tool}`, `glovo_mcp_authn_failures_total{reason}`,
  `glovo_mcp_upstream_requests_total{op,code}`, `glovo_mcp_ratelimited_total`. Labels are
  from closed sets only.
- OTel spans `glovo.tool/<name>` and `glovo.upstream/<op>` with `traceparent`
  propagated to mctl-api; attributes modelled on `auditSpanAttributes` (tool,
  outcome, request id, principal hash, tenant hash). Exporter configured by standard
  `OTEL_EXPORTER_OTLP_*`; absent means a no-op provider.
- Audit: one slog JSON line per tool call through `audit.NewRedactingHandler`; new
  sensitive names (`subject_token`, `handoff_url`, `scope_ref`, `authorization`) are
  added to `internal/audit/redact.go`.

### Container and CI

`Dockerfile.glovo-mcp`: `golang:1.26.10-alpine@sha256:<same digest as Dockerfile>`
builder, `CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.version=..." ./cmd/glovo-mcp`,
runtime `alpine:3.20@sha256:<pinned>` with ca-certificates, user 1000, read-only root
compatible, `EXPOSE 8080`, no shell tooling added, OCI labels. A
`.dockerignore`-independent build (copies only `go.mod go.sum cmd/glovo-mcp internal docs/contracts`).

CI (`.github/workflows/build.yml`): existing `go vet ./...` / `go test -race ./...`
already cover the new packages; add a `glovo-mcp-image` job that builds
`Dockerfile.glovo-mcp` with `push: false`, runs the container and probes
`/healthz`, and runs the T15 descriptor diff. Release (`release-please.yml`): a
`glovo-mcp-release` job modelled on `agent-worker-release`, guarded on
`services/labs/glovo-mcp/values.yaml` existing in mctl-gitops; since this proposal
creates no such file, every release emits the skip notice and publishes nothing.
That guard is the "separately approved release gate".

## Alternatives

1. Mount Glovo tools on the existing tg.mctl.ai server (`cmd/server`, `internal/mcp`).
   Rejected by the issue and ADR 0010: wrong resource and identity boundary, the
   Telegram process holds session keys and DB credentials, and descriptor drift
   would break T15.
2. New repository for the facade. Rejected by the owner decision on .github#324 for
   the fake M1.
3. Reuse `internal/auth/sharedhmac` (HS256 shared secret with mctl-api). Rejected: the
   facade would hold a secret able to mint user tokens; asymmetric JWKS keeps the
   facade secret-free for verification. The phased `checkAudience` mode is also
   wrong here: audience is strict from day one.
4. Have the facade assert the subject to mctl-api using only its workload credential.
   Rejected as a confused-deputy risk (TM3); forwarding the user token for
   re-verification keeps mctl-api authoritative.

## Platform impact

- Migrations: none. The facade has no database.
- Backward compatibility: `cmd/server`, `Dockerfile`, tool descriptors and portal
  allowlist unchanged; enforced by the import-boundary test and T15. `go.mod` gains no
  new direct dependency (go-jose, jsonschema, mcp-go, chi, otel, prometheus,
  x/time/rate already present).
- Resources: none deployed. Expected footprint when deployed later: 1 replica, ~30 MiB
  RSS, 50m CPU.
- Risks and mitigations:
  - Wire protocol diverges from what mctl-api M1a/M1b build: frozen v1alpha1 doc and
    golden fixtures; activation blocked until the real mctl-api passes the same
    fixtures (contract test runnable against a URL).
  - Accidental activation: `GLOVO_MCP_ENABLED=false` default, no gitops values, release
    guard skips publication.
  - Token leakage: header-only bearer, query-token refusal, redacting slog handler,
    leak tests reusing the `test/glovo-poc/leakcheck` patterns over logs, metrics,
    spans and tool results.
  - mcp-go upgrade changes protocol behaviour: pinned protocol-version list test and
    descriptor golden test.
  - Abuse/cost fan-out to mctl-api: per-principal limiter, global inflight cap,
    body caps, 5 s upstream timeout.
