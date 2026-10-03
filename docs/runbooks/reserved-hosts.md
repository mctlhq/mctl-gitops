# Reserved platform hostnames

Platform hosts under `mctl.ai` (and the `mctl.ru` / `mctl.me` apexes) belong
to the namespace that serves them. Two ValidatingAdmissionPolicies enforce
it cluster-wide (#1503):

| Piece | Where |
| --- | --- |
| Owner map: host → namespaces allowed to serve it | `platform-gitops/bootstrap/values.yaml` → `reservedPlatformHosts` |
| Policies + bindings | `platform-gitops/bootstrap/templates/system/admission-policies.yaml` (`mctl-reserved-platform-hosts-ingress`, `-ingressroute`) |
| Proof against a real API server | `scripts/test-reserved-hosts-policy.sh`, fixtures in `tests/fixtures/reserved-hosts/` |
| CI | `validate-manifests.yml` job `reserved-hosts` |

## What is refused

In every namespace, for `networking.k8s.io/v1 Ingress` and
`traefik.io/v1alpha1 IngressRoute` / `IngressRouteTCP`:

- a host (rule, TLS host, or `tls.domains`) listed in the map whose owner list
  does not contain the object's namespace;
- a wildcard over a platform domain (`*.mctl.ai`, `*.mctl.ru`, `*.mctl.me`),
  or over any reserved host owned by another namespace (reserving
  `x.id.mctl.ai` also refuses a tenant `*.id.mctl.ai`);
- an Ingress rule without a host, or `spec.defaultBackend`;
- an IngressRoute match that is not a plain `&&` conjunction with at least one
  literal `Host(...)` / `HostSNI(...)`: `||`, `!`, `HostRegexp`,
  `HostSNIRegexp`, `HostHeader`, the v2 multi-host `Host(a, b)`, `HostSNI(*)`,
  double-quoted arguments, and a host literal that is not at the top level of
  the conjunction or is not a DNS name (a decoy `Host(` inside another
  matcher's argument).

`HostSNI(*)` is refused because on a shared entrypoint it catches every TLS
connection no more specific router claims. Traefik requires it for a non-TLS
`IngressRouteTCP`, so such a router cannot be created anywhere today; one that
is genuinely needed (on its own entrypoint) gets a reviewed exemption in the
policy, not a carve-out in a tenant.

The second group exists because traefik orders routers by rule length: a long
rule with no host constraint outranks `Host(auth.mctl.ai) && PathPrefix(/)`
for the paths it covers, so it can take a platform host's traffic without
naming it. Hosts are compared case-insensitively and without a trailing dot,
as traefik matches them.

Hosts not in the map are unrestricted.

## Adding or moving a platform host

1. Add (or change) the entry in `reservedPlatformHosts` in the same PR that
   adds the Ingress. A host reserved for nobody in the cluster gets `[]`.
2. Before merging, prove the map against what is actually running, so a
   wrong owner cannot refuse a component's next sync:

   ```bash
   export KUBECONFIG=~/.kube/mctl-preview-config.yaml
   kubectl get ingress,ingressroute,ingressroutetcp -A -o yaml > /tmp/live-routes.yaml
   unset KUBECONFIG
   scripts/test-reserved-hosts-policy.sh --services --platform --admit /tmp/live-routes.yaml
   ```

   Needs Docker, kubectl, helm and Python with PyYAML. It starts k3s at the
   cluster's version, installs the policies as the bootstrap chart renders
   them, and server-side dry-runs every fixture, every GitOps service's routes,
   every platform route (below) and every live object. Exit 0 = everything admitted that should be and
   everything refused that should be.

CI runs the same script with `--services --platform` (no live dump; CI has
no cluster access). `--platform` covers the hosts the platform serves itself:
for every Application the bootstrap chart renders (plus `argocd-self-managed`),
each reserved host under an `ingress` key of its Helm values becomes an
Ingress in the Application's destination namespace, and raw Ingress /
IngressRoute manifests in its `infra-components` paths are taken as they are.
Upstream charts are not pulled, so a host an upstream chart serves under some
other key is not seen; the script prints a `note:` for every reserved host no
platform route serves, and those are only covered by the live dump.
`tests/fixtures/reserved-hosts/values-test.yaml` adds one test-only reserved
name to exercise the wildcard rule; it never reaches a deployment.

## When a sync is refused

The ArgoCD sync error names the policy and, for Ingress hosts, the offending
host. Either the object is wrong (a tenant used a platform name: pick another
host) or the map is (a platform component moved namespace: fix the owner in
`reservedPlatformHosts`). Never delete the binding to get a sync through — the
binding is the control.

Not every refusal is a sync. traefik itself is installed by the kube-hetzner
module through a k3s `HelmChart`, outside ArgoCD: if a traefik bump enables
the dashboard, its stock IngressRoute (`Host(...) && (PathPrefix(/api) ||
PathPrefix(/dashboard))`) is refused for `||`, and the failure shows up as a
failing `helm-install-traefik` job in `kube-system`, not as an OutOfSync
Application. Split it into two routes in the HelmChart values. Likewise,
`base-service` now fails at render time (`ingress.enabled needs ingress.host or
ingress.hosts`) rather than emitting a host-less rule the policy would refuse.

## Bumping the cluster or traefik

`K3S_IMAGE` and `TRAEFIK_VERSION` at the top of the test script track the
cluster's Kubernetes version and traefik image. The traefik CRDs are fetched
by commit, not tag, and checked against a digest, so a traefik bump updates
`TRAEFIK_VERSION`, `TRAEFIK_COMMIT` (`git ls-remote
https://github.com/traefik/traefik refs/tags/<tag>`) and `TRAEFIK_CRDS_SHA256`
together. Bump them with the cluster:
the API server's CEL environment is what decides whether the expressions
type-check (for example, `cel.bind` is not available on 1.33).
