# Design: issue-91-sticky-routing-by-user-id-for-multi-repl

## Current state

### ClientPool

`internal/telegram/clientpool.go` declares `ClientPool` (lines 60-72):

```go
type ClientPool struct {
    APIID       int
    APIHash     string
    IdleTimeout time.Duration
    MaxSessions int
    Store       *db.Store
    metrics     *metrics.Registry
    mu          sync.Mutex
    entries     map[int64]*entry
}
```

`entries` maps an internal `user_id int64` to an `*entry`, where each entry
holds a running `*telegram.Client` goroutine pair (`run` + `gc`). The `acquire`
method (line 191) creates a new entry when none exists for the user. There is no
cross-process state: each replica maintains its own map independently.

When a second replica receives a request for a user whose client is live on
replica 1, `acquire` creates a fresh `*telegram.Client` with a fresh MTProto
session. Telegram registers this as a new device login.

### Auth middleware and JWT structure

`internal/auth/middleware.go:19`: `Middleware` verifies the Bearer token via the
configured `auth.Provider`, then stores the resulting `*auth.Identity` in the
request context via `auth.With`. This runs inside the pod after the load
balancer has already selected the upstream.

`internal/auth/localjwt/issuer.go:32-42`: in `local-jwt` mode the JWT payload
carries:
- `sub` — `"tg:<telegram_id>"` (stable, human-readable)
- `tg_id` — the numeric Telegram ID as `int64`

`internal/auth/sharedhmac/verifier.go`: the `shared-hmac-legacy` path verifies
tokens signed by `api.mctl.ai`; the same `sub` format is used.

Both modes place the `sub` claim in a standard, statically located field of a
base64url-encoded JWT payload — no custom header or server-side lookup is needed
to read it.

### Config and startup

`internal/config/config.go`: no `REPLICA_ID` or `POD_NAME` field. No replica
identity is propagated into the application.

`cmd/server/main.go:48-55`: `slog.Info("starting", ...)` logs auth mode,
listen address, and telegram configuration. No replica identity.

### Metrics

`internal/metrics/metrics.go:69-157`: twelve collectors registered on a fresh
`prometheus.Registry`. No replica-identity gauge exists. All gauges follow the
pattern `prometheus.NewGauge(prometheus.GaugeOpts{Name: "mctl_...", Help: "..."})`.

### Documentation

`docs/hpa.md`: covers per-session memory budgets, `TELEGRAM_MAX_SESSIONS` table,
HPA stanza, Prometheus Adapter rule, and `MctlTelegramPoolNearCapacity` alert.
There is no section on sticky routing or multi-replica session safety.

No `deploy/` directory exists in this repository today.

---

## Proposed solution

The fix operates at two independent layers. Both must be active for the
multi-replica deployment to be safe.

### Layer 1: load-balancer consistent-hash routing

**Why the LB cannot verify the JWT signature**: NGINX Ingress community edition
and Envoy without the Istio JWT AuthN filter do not ship HS256 verification as
a first-class feature. Adding signature verification at the LB tier would
require distributing the `OAUTH_JWT_SIGNING_KEY` to a component outside the pod
boundary, which increases the attack surface for key exposure.

**Why omitting signature verification at the LB is acceptable**: the routing
key is used exclusively to select an upstream pod; it carries no authorization
weight. The application's auth middleware (`internal/auth/middleware.go`) is
the authoritative gate: it re-verifies the signature and rejects tampered
tokens. A client that edits its JWT payload to change the `sub` claim changes
only which pod handles the request; the forged token is rejected by the pod's
own auth check. There is no privilege escalation.

The ingress tier MUST strip the `X-Mctl-Route-Key` header from client requests
before its own extraction step so a client cannot inject a routing key without a
JWT.

**NGINX Ingress (community edition)**

Requires ingress-nginx v1.2 or later (LuaJIT enabled by default in the official
image).

```
# deploy/ingress/sticky-nginx.yaml
```

Key annotations:
- `nginx.ingress.kubernetes.io/upstream-hash-by: "$http_x_mctl_route_key"` —
  ketama consistent-hash on the injected header.
- `nginx.ingress.kubernetes.io/configuration-snippet` — a Lua block that:
  1. Clears any client-supplied `X-Mctl-Route-Key`.
  2. Extracts the second dot-delimited segment of the `Authorization: Bearer`
     value (the JWT payload), base64url-decodes it with `ngx.decode_base64`,
     and JSON-extracts the `sub` field via `cjson.decode`.
  3. Sets `ngx.req.set_header("X-Mctl-Route-Key", sub)`.

Unauthenticated requests (no Authorization header) skip step 3; the header
stays absent and NGINX falls back to round-robin for that request, which is the
correct behaviour (the application will 401 it anyway).

**Envoy / Gateway API (Istio)**

```
# deploy/ingress/sticky-envoy.yaml
```

Two resources:
1. `EnvoyFilter` (patch type `HTTP_FILTER`) with a Lua filter that replicates
   the extraction logic above, setting `x-mctl-route-key` on the decoded `sub`.
2. `DestinationRule` with `trafficPolicy.loadBalancer.consistentHash.httpHeaderName:
   "x-mctl-route-key"`.

For Gateway API (without Istio) the equivalent is an `HTTPRoute` with a request
header modifier filter together with a `BackendLBPolicy` (GEP-1731) specifying
`consistent_hash.httpHeader: "x-mctl-route-key"`. Because `BackendLBPolicy` is
experimental in Gateway API v1.2, the Envoy example uses the Istio
`DestinationRule` which is stable and widely deployed.

### Implementation constraints (P1 traps discovered in PR #98)

A previous implementation attempt (`mctlhq/mctl-telegram#98`, closed
unmerged) shipped Ingress manifests that *parsed* and looked correct
but rendered sticky routing non-functional in both flavours. The
implementer's next attempt MUST treat these as hard constraints:

1. **NGINX `configuration-snippet` accepts NGINX directives, not raw
   Lua statements.** A snippet that contains bare `local auth = ...`
   at the top level will either be rejected by ingress-nginx or
   silently no-op. Lua must be wrapped in a directive block:
   ```nginx
   rewrite_by_lua_block {
     local auth = ngx.req.get_headers()["authorization"]
     -- ...
     ngx.req.set_header("X-Mctl-Route-Key", sub)
   }
   ```
   Reference: ingress-nginx Lua module documentation; see
   `nginx.ingress.kubernetes.io/configuration-snippet` examples that
   show `*_by_lua_block` wrapping for any non-trivial logic.

2. **Envoy `HTTP_FILTER` patch requires the `Lua` filter config type,
   not `LuaPerRoute`.** `LuaPerRoute` is a per-route override message
   for an already-installed Lua filter; it does not accept
   `inline_code` and will be rejected/ignored at filter-install time.
   The EnvoyFilter patch must use:
   ```yaml
   value:
     "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
     inline_code: |
       -- function envoy_on_request(handle) ... end
   ```

3. **Envoy Lua stream-handle API does not expose
   `base64.decode`.** Only `base64Escape()` is provided. JWT payloads
   are base64url and must be decoded manually (e.g. via a bit-ops
   helper) or, preferably, the JWT `sub` should be lifted into a
   header upstream (e.g. by Istio AuthorizationPolicy /
   `jwt_payload`-claim header injection) and consumed by the Lua
   filter directly. Calling `base64.decode(...)` from `envoy_on_request`
   produces a runtime error and silently disables stickiness for every
   authenticated request.

Validation of the next attempt MUST include `kubectl apply
--dry-run=server` on both manifests and, where possible, a live smoke
of the header injection (NGINX access log showing the injected
`X-Mctl-Route-Key`, or Envoy access log via the
`%REQ(X-MCTL-ROUTE-KEY)%` format string).

### Layer 2: application — replica identity and observability

**`internal/config/config.go`** — add one field:

```go
ReplicaID string // REPLICA_ID env var; fallback to POD_NAME; fallback to "unknown"
```

Sourced as:
```go
ReplicaID: envOr("REPLICA_ID", envOr("POD_NAME", "unknown")),
```

Operators wire `POD_NAME` via the Kubernetes downward API in the Deployment
spec (`fieldPath: metadata.name`). No existing deployments are broken because
the fallback is the harmless string `"unknown"`.

**`cmd/server/main.go`** — extend the existing `slog.Info("starting", ...)` call
to include `"replica_id", cfg.ReplicaID`. After the metrics registry is
constructed and the pool-capacity gauge is set, add:

```go
m.TelegramReplicaID.WithLabelValues(cfg.ReplicaID).Set(1)
slog.Info("replica identity", "replica_id", cfg.ReplicaID)
```

**`internal/metrics/metrics.go`** — add to `Registry`:

```go
// TelegramReplicaID is an info-type gauge (constant value 1) labeled by
// replica_id. Operators use it to verify that a given user_id consistently
// hits the same replica by cross-referencing with pod-scoped pool metrics.
TelegramReplicaID *prometheus.GaugeVec
```

Constructed in `New()`:

```go
r.TelegramReplicaID = prometheus.NewGaugeVec(prometheus.GaugeOpts{
    Name: "mctl_telegram_replica_id",
    Help: "Info gauge (always 1) identifying this replica. " +
        "Label replica_id is sourced from REPLICA_ID / POD_NAME env vars.",
}, []string{"replica_id"})
```

Registered alongside the existing collectors in `reg.MustRegister(...)`.

The gauge is NOT set inside `New()` itself because the `replica_id` label value
comes from config, which is not available to `metrics.New()`. The caller
(`cmd/server/main.go`) sets it after config load.

**`docs/hpa.md`** — extend with a new section "Sticky routing for multi-replica
deployments" covering:
- The in-process pool problem and the "New login" UX impact.
- The two-layer solution summary.
- Security analysis (why payload-only extraction without sig verification is
  acceptable at the routing tier).
- Downward API snippet for `POD_NAME`.
- How to verify: `kubectl exec` into a pod, `curl /metrics`, and check
  `mctl_telegram_replica_id{replica_id="..."}`.
- One-time "New login" notifications on pod restarts/re-hashes and why this
  is unavoidable.
- Reference to the `deploy/ingress/` examples.

---

## Alternatives

### Alternative 1: Kubernetes Service `sessionAffinity: ClientIP`

Kubernetes Services support `sessionAffinity: ClientIP` with a configurable
timeout. This provides IP-level stickiness without any ingress change.

**Rejected** because MCP clients frequently share a single egress IP (corporate
NAT, shared gateway). Multiple users behind the same NAT would all hash to the
same pod, producing a severe load imbalance. Stickiness must be at user_id
granularity, not IP granularity.

### Alternative 2: Redis-backed distributed ClientPool

Replace the in-process `entries map[int64]*entry` with a distributed lease
backed by Redis (or equivalent). Each `Borrow()` acquires a lease for
`user_id`; the lease directs the request to whichever pod holds the MTProto
connection. If the pod dies, the lease expires and another pod re-creates the
session.

**Rejected for this issue** because:
- The issue explicitly marks this out of scope.
- It adds a stateful dependency (Redis) and increases `Borrow()` latency with
  a network round-trip on every tool invocation.
- It does not eliminate "New login" notifications on pod failures; it only
  reduces their frequency.
- Sticky routing at the LB achieves the same zero-extra-session goal with no
  new infrastructure dependency.

### Alternative 3: Cap replicas to 1 via Deployment maxReplicas

Set `maxReplicas: 1` in the HPA spec to prevent multi-replica operation until a
full distributed-pool solution is ready.

**Rejected** because it blocks the Beta readiness goal described in the issue
and makes the HPA configuration in `docs/hpa.md` non-functional for its stated
purpose.

---

## Platform impact

### Migrations

None. The `ReplicaID` field has safe defaults; the gauge is additive; no schema
changes are required.

### Backward compatibility

- Existing single-replica deployments continue to work unchanged. The new
  `mctl_telegram_replica_id{replica_id="unknown"}` gauge appears in metrics but
  breaks no existing dashboards or alert rules.
- The Ingress examples are opt-in; they are not applied automatically by any
  CI step in this repository.

### Resource impact

- One additional Prometheus time-series per replica (negligible).
- The Lua extraction snippet adds sub-millisecond overhead per request at the
  ingress tier (one base64 decode + one JSON parse of a small payload).

### Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| ingress-nginx upgrade changes Lua API surface | Low | Pin ingress-nginx version in the example manifest; document in the sticky routing section of `docs/hpa.md` |
| Consistent-hash rebalancing on pod add/remove causes one-time "New login" per re-mapped user | Low-Medium | Document in ops runbook; accept as unavoidable; alert on `mctl_telegram_client_errors_total` spike after scale events |
| Client forges `X-Mctl-Route-Key` before Lua extraction (if header strip is misconfigured) | Low | Routes to an arbitrary pod; rejected by app-level auth; no privilege escalation. The soak test should assert header stripping works |
| `POD_NAME` not injected via downward API | Low | Fallback to `"unknown"` keeps startup working; monitoring alert on `replica_id="unknown"` can catch missing configuration |
