apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    # Traefik Hub CRDs were manually deleted on 2026-05-10.
    # The hub.enabled key is not accepted by the chart schema in Traefik >=v3.x
    # (additional properties not allowed), so it has been removed entirely.

    # SOC F11: pin the kube-hetzner Traefik PDB. Live is 3 replicas with
    # maxUnavailable 33% (desiredHealthy 2). Do not set minAvailable here:
    # the chart emits both fields independently, and Kubernetes rejects a
    # PDB that sets both. minAvailable: 1 would also weaken the live budget.
    # Replica count is already 3; do not drop it.
    podDisruptionBudget:
      enabled: true
      maxUnavailable: 33%

    # #1119: refuse anything that did not arrive through Cloudflare.
    #
    # The reference is <namespace>-<name>@kubernetescrd -- namespace traefik,
    # name cloudflare-origin -- and renders as
    #   --entryPoints.websecure.http.middlewares=traefik-cloudflare-origin@kubernetescrd
    # A reference to a Middleware that does not exist takes down EVERY router on
    # this entrypoint, so the object ships in its own manifest, listed before
    # this one in kustomization.yaml and applied in an earlier terraform apply.
    # Break-glass: infrastructure/k3s-preview/README.md.
    #
    # This MERGES over the base HelmChart's ports.websecure (proxyProtocol and
    # forwardedHeaders trustedIPs) rather than replacing it -- helm-controller
    # deep-merges valuesContent. Verify after an apply that all three arguments
    # are present on the deployment: if trustedIPs were lost, Traefik would see
    # the load balancer's private address as the client and the allowlist would
    # refuse ALL traffic.
    #
    # web deliberately does not get this middleware, for three reasons:
    #   1. It would protect nothing. The http->https redirection is in the
    #      STATIC config (--entryPoints.web.http.redirections.entryPoint.to=:443),
    #      so :80 never reaches a backend -- measured and written down in
    #      platform-gitops/services/labs/mctl-telegram-preview/values.yaml.
    #   2. Whether entrypoint middlewares apply to the internal redirect router
    #      is version-dependent and undocumented. Betting a working global
    #      redirect on it, for no security gain, is a bad trade.
    #   3. It would break ACME HTTP-01 for tenant custom domains
    #      (wft-add-custom-domain.yaml attaches letsencrypt-http01): Let's
    #      Encrypt's validation servers are not in Cloudflare's ranges.
    ports:
      websecure:
        http:
          middlewares:
            - traefik-cloudflare-origin@kubernetescrd
