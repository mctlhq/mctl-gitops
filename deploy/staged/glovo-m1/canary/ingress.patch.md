# Basket canary: ingress, DNS and TLS for glovo.mctl.ai (text only, not applied)

Part of the Glovo Basket MCP production canary (mctlhq/mctl-api#1006, plan
mctlhq/mctl-gitops#2457). Runbook: `docs/runbooks/glovo-basket-canary.md`
(step C). Nothing in this file is reconciled. The two target files below are
under `platform-gitops/**`, where the leak guard (#2470,
`scripts/validate-glovo-m1-staging.py`, `LEAK = glovo|mctl-assistants`)
refuses any Glovo string, so the diff stays text until the activation PR.

## What the code does with the host (mctl-api#1008, `internal/api/glovo_basket.go`)

- `mctl-api` itself serves `glovo.mctl.ai`. There is no second workload and
  no second Service. `withGlovoBasketHost` sends a request whose Host is the
  host of `GLOVO_MCP_RESOURCE` to a router that has only
  `/.well-known/oauth-protected-resource[/mcp]` and `/mcp`; every other path
  is a JSON 404. Any other Host goes to the unchanged main router.
- That router exists only when `GLOVO_BASKET_MCP_ENABLED=true` and every
  dependency is present (`GlovoBasketRoutes.complete()`). With the flag off,
  or on an image without the code, a request for `Host: glovo.mctl.ai` would
  reach the MAIN router: `/healthz`, `/docs`, `/oauth/*`, `/identity/*`,
  `/api/*` under a second host name.
- The protected-resource metadata names `https://api.mctl.ai` as the
  authorization server, so a client fetches the authorization-server metadata,
  `/oauth/authorize` and `/oauth/token` from `api.mctl.ai`, never from the
  Glovo host. The Glovo host needs exactly two public paths at the edge.
- The owner approval page lives on `SELF_URL` (`https://api.mctl.ai`), under
  `/glovo/basket/approvals/*`, not on the Glovo host.

## Ordering rules that follow (hard)

1. The Ingress host is added AFTER the basket MCP is on and verified on the
   pods (runbook step B1), never before. Until then `glovo.mctl.ai` stays a
   Traefik 404 (observed 2026-11-10 on `/`, `/mcp` and the metadata path).
2. Kill switch and rollback remove the Ingress host FIRST, then the flags.
   Removing the flags while the host is still routed re-exposes the main API
   router under the Glovo host name for the length of the rollout.
3. The edge paths are restricted per host, so even rule 2 failing leaves only
   `/mcp` and the metadata path routed. That needs the chart change below.

## DNS, TLS, edge: nothing to change (verified in this repository, read-only)

- DNS: `infrastructure/cloudflare/zones/mctl-ai/dns.tf` has
  `cloudflare_dns_record.wildcard` (`*.mctl.ai`, proxied, A to the origin).
  `glovo.mctl.ai` already resolves. No `dns.tf` change, so no Cloudflare
  apply and no Terraform plan for this canary. Cloudflare changes go through
  gitops Terraform only; there are none here.
- Edge TLS: zone setting `ssl = strict` (`zones/mctl-ai/tls.tf`); Traefik
  serves a Cloudflare Origin CA certificate for the apex and the wildcard as
  its default (`core-infra/traefik-origin-cert.yaml`), so a first-level
  `glovo.mctl.ai` validates with no certificate of its own.
- Certificate: the chart's Ingress carries
  `cert-manager.io/cluster-issuer: letsencrypt-prod` and one TLS secret per
  host, `mctl-api-glovo-mctl-ai-tls`. cert-manager issues it by DNS-01 with
  the existing Cloudflare token (`core-infra/cert-manager-dns01.yaml`, scope:
  DNS write on the four zones, mctl.ai included). No new token, no token
  change. Issuance is a nice-to-have: if it lags, the origin default
  certificate still serves.
- WAF: the zone custom ruleset blocks only spoofed crawler User-Agents and
  archive probes on the apex (`firewall.tf`). No Access application covers
  `glovo.mctl.ai` (`account/*.tf` lists exact hosts). Super Bot Fight Mode is
  not skipped for it, like `api.mctl.ai` for non-Hetzner clients. UNVERIFIED
  until the first real client request: a Cloudflare challenge on a non-browser
  client would show as a 403/503 HTML body on `/mcp` (runbook step C checks).
- Reserved host: `glovo.mctl.ai` is NOT in `reservedPlatformHosts`
  (`bootstrap/values.yaml`), so today any tenant could claim it with an
  Ingress. The activation PR reserves it for `mctl-api`, in the same PR as
  the Ingress (`docs/runbooks/reserved-hosts.md`). Adding `glovo.mctl.ai: []`
  earlier would be useful hardening but trips the leak guard today.

## Prerequisite, mctl-api chart (the chart tracks mctl-api `main`)

`helm/templates/ingress.yaml` routes ONE global `paths` list for every host.
Two small chart changes are needed in `mctlhq/mctl-api`, before this patch:

1. Per-host `paths` override, so the Glovo host routes two paths only.
2. `/glovo` in the default `paths`, so the approval page on `api.mctl.ai`
   (`/glovo/basket/approvals/*`) is routed at all. Without it the page is
   unreachable through Traefik even when the code is deployed.

```diff
--- a/helm/templates/ingress.yaml
+++ b/helm/templates/ingress.yaml
@@ rules: range .Values.ingress.hosts
-          {{- range $paths }}
+          {{- range (default $paths .paths) }}
--- a/helm/values.yaml
+++ b/helm/values.yaml
@@ ingress.paths
     - /devloop
+    # Glovo basket approval page (/glovo/basket/approvals/*, mctl-api#1007).
+    - /glovo
     - /api
```

Checked: with the first change, `helm template` of the chart with the host
list below renders `api.mctl.ai` with the ten default paths and
`glovo.mctl.ai` with `/mcp` and `/.well-known/oauth-protected-resource`
only; the render without a per-host `paths` is byte-identical to today's.
`helm/render_test.go` needs a case for both. Both changes are inert on their
own: no code answers `/glovo/*` until the page is enabled, and no host sets
`paths`. They ship with the mctl-api release that carries the Basket code
(called 4.156.0 in the plan), so the chart change that tracks `main` lands no
earlier than that code.

## The diff (activation step C, its own PR and its own owner GO)

Extract the fenced diff and apply it from the repository root;
`git apply --check` was clean against main at the time of staging (9c87fe961).

```diff
diff --git a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
index eace5f3d9..c06df0607 100644
--- a/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
+++ b/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
@@ -50,6 +50,15 @@ spec:
             tls: true
             hosts:
               - host: api.mctl.ai
+              # Glovo basket MCP (mctlhq/mctl-api#1006). Only the MCP and its
+              # RFC 9728 metadata are routed at the edge; every other path
+              # on this host stays a Traefik 404. Needs the chart's
+              # hosts[].paths override (mctl-api chart change, see the
+              # canary runbook) and the basket MCP already enabled.
+              - host: glovo.mctl.ai
+                paths:
+                  - /mcp
+                  - /.well-known/oauth-protected-resource
 
           env:
             GITOPS_REPO_URL: https://github.com/mctlhq/mctl-gitops.git
diff --git a/platform-gitops/bootstrap/values.yaml b/platform-gitops/bootstrap/values.yaml
index 6e9b999fe..8980110ed 100644
--- a/platform-gitops/bootstrap/values.yaml
+++ b/platform-gitops/bootstrap/values.yaml
@@ -572,6 +572,8 @@ reservedPlatformHosts:
   sso.mctl.ai: [zitadel]
   accounts.mctl.ai: [zitadel]
   api.mctl.ai: [mctl-api]
+  # Glovo basket MCP, served by mctl-api itself (host-routed, mctl-api#1006).
+  glovo.mctl.ai: [mctl-api]
   app.mctl.ai: [backstage]
   ops.mctl.ai: [argocd]
   secrets.mctl.ai: [vault]
```

The activation PR also changes the leak guard so that exactly these two
additions pass and nothing else does. See "Leak guard at activation" in the
runbook; the guard change is reviewed first, as its own commit, with a
selftest that a Glovo string anywhere else in `platform-gitops/**` still
fails.

## Reserved-host proof (required before merge, read-only)

Per `docs/runbooks/reserved-hosts.md`: dump the live routes and run
`scripts/test-reserved-hosts-policy.sh --services --platform --admit
<dump>`. The dump is `kubectl get ingress,ingressroute,ingressroutetcp -A -o
yaml`, which reads no Secret.

## Verification (read-only, after the merge)

```bash
# Rendered Ingress: two hosts, two paths on the Glovo host
kubectl -n mctl-api get ingress mctl-api -o jsonpath='{range .spec.rules[*]}{.host}{"  "}{range .http.paths[*]}{.path}{" "}{end}{"\n"}{end}'
# Certificate (cert-manager); READY may lag, the origin default cert serves meanwhile
kubectl -n mctl-api get certificate mctl-api-glovo-mctl-ai-tls
# Public behaviour of the host-routed router
curl -sS -o /dev/null -w '%{http_code}\n' https://glovo.mctl.ai/mcp                                      # 401
curl -sSi https://glovo.mctl.ai/mcp | grep -i '^www-authenticate'                                         # resource_metadata="https://glovo.mctl.ai/.well-known/oauth-protected-resource"
curl -sS https://glovo.mctl.ai/.well-known/oauth-protected-resource                                       # resource https://glovo.mctl.ai/mcp, authorization_servers [https://api.mctl.ai]
for p in /healthz /readyz /openapi.yaml /docs /oauth/token /identity/links /api/v1/glovo/pilot /devloop/decide/x; do
  curl -sS -o /dev/null -w "$p %{http_code}\n" "https://glovo.mctl.ai$p"; done                             # all 404
```

## Rollback

1. Revert this diff (the Ingress host and the reserved-host entry). Argo prunes
   the Glovo rule; `glovo.mctl.ai` is a Traefik 404 again within about a
   minute. The wildcard DNS record, the certificate secret and the chart
   changes need no action. Verify with the first two `curl` lines above
   (now 404).
2. Only then, if needed, switch the flags off (`env.patch.md`).
