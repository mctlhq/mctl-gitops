# Sticky routing by user_id for multi-replica deployments

## Context

`internal/telegram/clientpool.go` maintains a `ClientPool` whose `entries`
field is an `map[int64]*entry` keyed by internal `user_id`. Each `entry` wraps
a live, in-process `*telegram.Client` goroutine (lines 60-91). This state is
not shared across pods: when the Kubernetes Deployment scales to two or more
replicas, a user whose requests land on different replicas triggers a fresh
MTProto session on each replica. Telegram treats each new session as a new
device login and fires a "New login" security notification — damaging user trust
and raising red flags for security-conscious users. Additionally, pool memory
grows in proportion to (active users * replicas) instead of active users alone,
which undermines the capacity planning documented in `docs/hpa.md`.

The Beta readiness requirement (referenced in issue #90) is that the service can
be scaled to a second replica the day after a load test shows it is needed.
Without sticky routing that scale-out is harmful to users. This proposal
specifies the load-balancer configuration, observability additions, and
documentation needed to enable safe multi-replica operation.

## User stories

- AS a Telegram user I WANT every request from my MCP client to consistently
  reach the same mctl-telegram replica SO THAT I do not receive spurious
  "New login" security notifications when the deployment scales out.
- AS an operator I WANT a Prometheus gauge and a startup log line identifying
  the serving replica SO THAT I can verify at a glance that sticky routing is
  in effect and that a given user_id consistently hits the same pod.
- AS a platform engineer I WANT working Ingress and Service manifests for both
  NGINX Ingress Controller and Envoy/Gateway API SO THAT sticky routing can be
  activated as part of any HPA scale-out event without subsequent remediation.
- AS a security reviewer I WANT documentation explaining why sub-based
  consistent hashing at the load balancer is safe SO THAT the routing design
  does not require repeated re-justification during audits.

## Acceptance criteria (EARS)

- WHEN a Bearer token is present in the `Authorization` header, THE SYSTEM
  SHALL derive the routing key from the JWT `sub` claim (format
  `tg:<telegram_id>`) at the ingress tier without relying on any header
  supplied by the client.
- WHEN the ingress tier derives a routing key, THE SYSTEM SHALL strip any
  client-supplied `X-Mctl-Route-Key` header before the extraction step so that
  a client cannot pre-load or override the routing key.
- WHEN a routing key is derived, THE SYSTEM SHALL route all requests bearing
  the same routing key to the same upstream pod via ketama consistent-hash
  modulo current pod membership.
- WHEN a pod is added or removed from the upstream pool, THE SYSTEM SHALL
  re-hash only the minimum subset of users required to restore even
  distribution; users whose hash slot was not affected SHALL continue hitting
  the same pod without a new session.
- WHEN the `Authorization` header is absent or unparseable at the ingress tier,
  THE SYSTEM SHALL forward the request to any upstream pod unmodified; the
  application-level auth middleware in `internal/auth/middleware.go` remains the
  authoritative access gate and SHALL reject the request if credentials are
  missing or invalid.
- WHEN mctl-telegram starts, THE SYSTEM SHALL emit a structured slog line at
  INFO level containing the field `replica_id` sourced from the `REPLICA_ID`
  environment variable, falling back to `POD_NAME`, then to the literal string
  `"unknown"`.
- WHEN mctl-telegram starts, THE SYSTEM SHALL register a Prometheus gauge
  `mctl_telegram_replica_id` labeled by `replica_id` and set it to 1, keeping
  it at 1 for the lifetime of the process.
- WHILE multi-replica sticky routing is active, THE SYSTEM SHALL NOT require
  any distributed in-memory store (Redis or equivalent) for the `ClientPool`;
  all session state SHALL remain local to each pod.
- IF the `REPLICA_ID` environment variable is unset and `POD_NAME` is also
  unset, THE SYSTEM SHALL use the value `"unknown"` for the replica_id label
  without failing startup.
- WHEN either `deploy/ingress/sticky-nginx.yaml` or
  `deploy/ingress/sticky-envoy.yaml` is shipped, THE SYSTEM SHALL pass
  `kubectl apply --dry-run=server` against a representative cluster
  (ingress-nginx-controller-installed for the NGINX file, Istio-installed for
  the Envoy file) with no admission errors.
- WHEN an authenticated request bearing a valid bearer token traverses the
  configured ingress, THE SYSTEM SHALL emit an access-log line containing the
  injected `X-Mctl-Route-Key` header value derived from the JWT `sub` claim
  (verifiable via NGINX `log_format` or Envoy `%REQ(X-MCTL-ROUTE-KEY)%`
  formatter).
- IF the Lua snippet relies on a function or symbol not exported by the host
  Lua API (ingress-nginx OpenResty namespace for NGINX, Envoy
  `stream_handle` namespace for Envoy), THE SYSTEM SHALL be rejected by the
  proposal review — the snippet MUST only call documented host APIs (see
  design.md `Implementation constraints` section).

## Out of scope

- Distributed / shared `ClientPool` backed by Redis or another external store.
- Local Bridge mode (M4), which removes the multi-replica problem at the
  architecture level; tracked separately in ROADMAP.
- RS256/JWKS-based JWT signature verification at the ingress tier.
- Automatic session migration or rebalancing when consistent-hash remaps a user
  to a new pod after a node failure or rolling restart.
- Changes to the HPA trigger expressions in `docs/hpa.md` beyond the new
  sticky-routing section.

## Open questions

1. The Kubernetes Deployment manifest lives in `mctl-gitops`, not in this
   repository. The `deploy/ingress/` YAML files produced here are standalone
   examples. It is assumed the platform team will adapt them into the
   appropriate kustomize overlay in `mctl-gitops` — this should be confirmed
   before the examples are treated as directly deployable.
2. `mctl_telegram_replica_id` follows the Prometheus info-metric convention
   (constant value 1, descriptive label). If the operator intended a different
   value (for example, an ordinal replica index as a float), the gauge
   semantics should be clarified; the proposal uses the info-metric pattern
   as the most idiomatic choice.
3. The soak test for #90 (2 replicas + sticky routing, 30-minute canary
   assertion) is listed as a task here for completeness but the test scenario
   itself belongs to issue #90. The dependency between this issue and #90 should
   be agreed on — specifically, whether the soak test blocks Beta readiness for
   this feature or runs in parallel.
