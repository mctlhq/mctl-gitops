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
- a wildcard over a platform domain (`*.mctl.ai`, `*.mctl.ru`, `*.mctl.me`);
- an Ingress rule without a host, or `spec.defaultBackend`;
- an IngressRoute match that is not a plain `&&` conjunction with at least one
  literal `Host(...)` / `HostSNI(...)`: `||`, `!`, `HostRegexp`,
  `HostSNIRegexp`, `HostHeader`, the v2 multi-host `Host(a, b)`, `HostSNI(*)`.

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
   scripts/test-reserved-hosts-policy.sh --services --admit /tmp/live-routes.yaml
   ```

   Needs Docker, kubectl, helm and Python with PyYAML. It starts k3s at the
   cluster's version, installs the policies as the bootstrap chart renders
   them, and server-side dry-runs every fixture, every GitOps service's routes
   and every live object. Exit 0 = everything admitted that should be and
   everything refused that should be.

CI runs the same script with `--services` (no live dump; CI has no cluster
access).

## When a sync is refused

The ArgoCD sync error names the policy and, for Ingress hosts, the offending
host. Either the object is wrong (a tenant used a platform name: pick another
host) or the map is (a platform component moved namespace: fix the owner in
`reservedPlatformHosts`). Never delete the binding to get a sync through — the
binding is the control.

## Bumping the cluster or traefik

`K3S_IMAGE` and `TRAEFIK_VERSION` at the top of the test script track the
cluster's Kubernetes version and traefik image. Bump them with the cluster:
the API server's CEL environment is what decides whether the expressions
type-check (for example, `cel.bind` is not available on 1.33).
