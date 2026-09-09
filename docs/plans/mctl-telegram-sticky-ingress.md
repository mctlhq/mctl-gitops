# mctl-telegram sticky ingress — what can be deployed, and what is blocked

Status: **blocked on a cluster-infrastructure decision.** Written while working
`mctlhq/mctl-telegram#145`, which asks for the Layer-1 sticky-routing reference
manifests to be adapted into a real overlay here.

## The finding that blocks it

`#145` frames the choice as "nginx-snippet path vs Istio/Envoy path for the
preprod cluster". Neither controller is installed.

The preprod cluster is k3s provisioned by the `kube-hetzner` Terraform module
with its default ingress, **Traefik** (`infrastructure/k3s-preview/kube.tf`,
"Ingress: Traefik (default)"). Every deployed service goes through it:
`base-service`'s `values.yaml` sets `ingress.className: traefik`, and the chart's
forward-auth support renders a `traefik.io/v1alpha1 Middleware`. Nothing in
`platform-gitops/bootstrap/` installs `ingress-nginx`, and nothing installs
Istio — there is no `istiod`, no ingress gateway, and no `EnvoyFilter` CRD.

So both reference manifests in `mctlhq/mctl-telegram` `deploy/ingress/` target a
runtime this cluster does not have:

- `sticky-nginx.yaml` needs ingress-nginx with `allow-snippet-annotations: "true"`
  and `annotations-risk-level: "Critical"`.
- `sticky-envoy.yaml` needs Istio ≥ 1.14 with an Envoy ingress gateway.

**Traefik cannot substitute.** Its only session-affinity mechanism is a sticky
*cookie* on a Service or ServiceSubset. It has no consistent-hash load balancer
and no way to hash on a request header, which is precisely what the design needs:
the routing key is derived from the JWT `sub` claim, and MCP clients are
server-to-server callers that do not necessarily carry cookies. A cookie is not a
weaker version of this design; it is a different one that does not solve the
problem.

This is why no sticky overlay lands in this repo yet. Writing one against a
controller that is not installed would reproduce exactly the failure `#546` and
`mctlhq/mctl-telegram#491` are about — a manifest that looks deployed, is
reconciled by nothing, and drifts.

## The decision that is actually needed

Three options, in rough order of cost. All three are cluster-infrastructure
changes and need an operator with cluster access to decide and to land the
Terraform / bootstrap side.

1. **Install ingress-nginx as a second IngressClass alongside Traefik**, and move
   only `labs/mctl-telegram` onto it. Smallest blast radius of the three, but it
   means a second LoadBalancer service (a second Hetzner LB, or sharing one), a
   second cert-manager solver path, and enabling `Critical`-risk snippet
   annotations on that controller. The snippet risk is contained by the fact that
   the platform team owns every Ingress in this repo, but it is a real, standing
   loosening of the controller's default posture.
2. **Install Istio.** The most capable option and the one whose Lua filter the
   reference manifest is written against, but it brings a service mesh, sidecar
   injection decisions, and its own upgrade cadence into a cluster that has none
   of that today. Hard to justify for one service's routing.
3. **Do it in the application instead.** `mctlhq/mctl-telegram#126` records that
   the relay is single-replica-only because `bridge.Hub` holds daemon websockets
   in process. Sticky ingress relaxes that at the routing tier; a shared backend
   (the Hub's registry in Postgres or Redis, with cross-replica forwarding) fixes
   it at the source and needs no new ingress controller at all. This is the only
   option that also survives a client that reconnects to a different pod.

## What this repo has done in the meantime

The one parameterisation item from `#145` that is not blocked on the routing
decision has landed: the **POD_NAME downward-API env**.

`base-service` gained an `envValueFrom` value (a map of env name → `valueFrom`
block), because the chart's `env:` map renders every value as a literal string
and so could not express the downward API at all. `labs/mctl-telegram` now sets:

```yaml
envValueFrom:
  POD_NAME:
    fieldRef:
      fieldPath: metadata.name
```

The service resolves `replica_id` as `REPLICA_ID` > `POD_NAME` > `"unknown"`
(`internal/config/config.go`), so before this the `mctl_telegram_replica_id`
gauge shipped in mctl-telegram#124 was published with `replica_id="unknown"`.
It is harmless at the current `replicaCount: 1` and is a prerequisite for the
gauge telling one replica from another once there is more than one.

## What sticky ingress would and would not make safe

Worth stating plainly, because it is easy to read "sticky routing" as "safe to
scale out".

**Would**: pin all requests carrying a given JWT `sub` to one pod, so a user's
MCP calls consistently reach the replica holding their Telegram MTProto session
and their Local Bridge websocket.

**Would not**:

- Make `bridge.Hub` cross-replica. It is still an in-process registry
  (`#126`). A daemon connected to pod A is invisible to pod B; sticky routing
  only arranges for the user's calls to keep arriving at pod A. If pod A
  restarts, the daemon reconnects — possibly to pod B — and any request in
  flight against the old hash target fails.
- Make MTProto session ownership safe. `labs/mctl-telegram` runs
  `strategy: Recreate` specifically so that overlapping pods never open the same
  auth keys. Sticky routing does not change that constraint, and moving to a
  rolling update remains a separate decision that needs an exclusive
  session-owner runtime.
- Survive a rehash. Ketama minimises but does not eliminate remapping: scaling
  the Deployment moves some fraction of users to a new pod, which for those users
  is a session re-establish, not a transparent move.

In other words, sticky ingress is a necessary condition for multi-replica, not a
sufficient one. Scaling `replicaCount` above 1 should not follow from this
document alone.

## References

- `mctlhq/mctl-telegram#145` — adapt the reference manifests into an overlay
- `mctlhq/mctl-telegram#126` — Layer-1 redo with a controller-acceptance gate
- `mctlhq/mctl-telegram` PR #141 — the reference manifests and their kind-based
  acceptance workflow (`.github/workflows/sticky-ingress-acceptance.yml`)
- `mctlhq/mctl-telegram` PR #124 — Layer 2, the `mctl_telegram_replica_id` gauge
