# Design: egress-network-policy

## Current state

According to `context/architecture.md`, openclaw is deployed in three Kubernetes namespaces: `ovk`, `labs`,
`admins`. Each namespace contains an independent openclaw deployment with its own S3 bucket for
state (ADR 0002). Deployment is managed via mctl-gitops → ArgoCD.

Currently, none of the three namespaces has a Kubernetes NetworkPolicy. This means openclaw pods
have unrestricted egress: they can initiate TCP/UDP connections to any IP — both inside the cluster
(other namespaces, control plane) and outside (arbitrary external hosts). CVE-2026-41297 (SSRF in
marketplace) is a clear demonstration of how this gap lets an attacker steer the pod's outbound requests.

## Proposed solution

Create one `NetworkPolicy` manifest per namespace. The manifests are added to the mctl-gitops
repository and applied via ArgoCD sync — no openclaw code changes, no Docker image changes, no RAM
impact.

### Manifest structure

Each NetworkPolicy manifest contains:

1. **Default deny egress** — base rule: all egress is blocked unless explicitly allowed.
2. **Allow DNS** — UDP/TCP port 53 to kube-dns (namespace `kube-system`, label
   `k8s-app: kube-dns`). Without DNS the pod cannot resolve any hostname.
3. **Allow S3** — HTTPS (TCP 443) to the tenant's S3 endpoint. The exact CIDR or FQDN
   depends on the provider (AWS S3, Minio, etc.) — set in the tenant overlay.
4. **Allow channel APIs** — HTTPS (TCP 443) to channel API endpoints:
   - Telegram: `api.telegram.org`
   - Discord: `discord.com`, `gateway.discord.gg`
   - Slack: `slack.com`, `wss-primary.slack.com`
   - WhatsApp (Baileys): `web.whatsapp.com`, `*.whatsapp.net`
   - Other channels by analogy (full list in the manifest based on the architecture)
5. **Allow upstream marketplace** — HTTPS to `api.clawhub.io` (or the current marketplace
   endpoint of upstream openclaw).
6. **Allow mctl-api MCP** — HTTPS to `api.mctl.ai` for MCP integration.

### Per-tenant overlays

Because tenants may use different S3 regions or have specific channels, NetworkPolicies are
expressed as Kustomize overlays in mctl-gitops:

```
gitops/
  base/
    network-policy/
      egress-network-policy.yaml   # base template with shared rules
  overlays/
    labs/
      network-policy/
        patch-s3-cidr.yaml         # labs-specific S3 endpoint
    admins/
      network-policy/
        patch-s3-cidr.yaml
    ovk/
      network-policy/
        patch-s3-cidr.yaml
```

### Application order

Rollout follows ADR 0001: labs → admins → ovk. NetworkPolicies are applied sequentially with
an observation window:
1. Apply in `labs`, observe for N days — confirm no required request is blocked
   (watch openclaw logs for connection errors).
2. Apply in `admins`.
3. Apply in `ovk`.

NetworkPolicy does not require stopping the s3-sync canary and does not affect the restore-state
probe (ADR 0002), since the S3 endpoint is explicitly allowed in the whitelist.

### Important: labs RAM

Kubernetes NetworkPolicy is implemented at the kube-proxy/iptables (or CNI plugin) level. It
does not add a sidecar container and does not increase the openclaw pod's RAM. For the `labs`
tenant (close to the memory limit) this is the key property of the solution.

## Alternatives

### 1. Service mesh (Istio / Linkerd)

Provides L7 egress control, mTLS, detailed audit logs. However:
- Requires injecting a sidecar (Envoy proxy) into every pod → significant RAM growth, critical for `labs`.
- Substantial operational complexity (CRDs, certificate rotation, control plane).
- Overkill for the task at hand — we need an L4 whitelist, not L7 inspection.

Dropped as disproportionate in complexity/RAM impact.

### 2. External egress gateway (Squid, Envoy as a separate pod)

All openclaw pod traffic is routed through an egress proxy that filters by FQDN.
- Provides FQDN-level filtering instead of IP/CIDR (useful for cloud-hosted channel APIs with dynamic IPs).
- Adds a separate pod → extra cluster-level RAM, latency, SPOF.
- More complex to configure and to roll back.

Dropped: the upside (FQDN resolution) does not outweigh the complexity for the current threat model.
May be revisited as a separate proposal if channel API IP ranges turn out to be unstable.

### 3. Do nothing (close SSRF only via openclaw upgrade)

CVE-2026-41297 is fixed in 2026.3.31+. However:
- Future SSRF in openclaw or its plugins remains unaddressed at the network layer.
- Defense-in-depth requires network isolation regardless of the application version.
- Effort is extremely low (manifest only, no code changes).

Dropped as insufficient.

## Platform impact

### Migration

No data migration. The change is only the addition of NetworkPolicy manifests to gitops.

### Backward compatibility

Kubernetes NetworkPolicy is additive: until egress rules are applied, behaviour does not change.
After they are applied, only connections outside the whitelist are blocked.
The risk of a false block on legitimate traffic is the main operational risk; mitigated
by the staged rollout through labs.

### Resource impact

- openclaw pod RAM: **unchanged** (NetworkPolicy — iptables rules, not a sidecar).
- CPU: minimal per-packet iptables overhead, negligible at current load.
- `labs` tenant: **memory-wise unaffected** — not risky.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Block of a needed channel API (incomplete whitelist) | Medium | Rollout through labs with observation; openclaw logs; easy rollback by removing the manifest |
| S3 endpoint CIDR changes (cloud provider) | Low | Use FQDN-based egress rules if the CNI supports them (Calico NetworkPolicy), or monitor S3 connectivity |
| Cluster CNI plugin does not support NetworkPolicy | Low | Verify on labs before rollout to production namespaces |
| Block of mctl MCP integration | Low | `api.mctl.ai` is explicitly in the whitelist; verified in T3 |
