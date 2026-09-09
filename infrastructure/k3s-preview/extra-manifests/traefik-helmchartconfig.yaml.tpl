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
    # The `http:` level is NOT a typo, even though the sibling keys this file
    # merges over (proxyProtocol, forwardedHeaders) are flat. Rendered against
    # the chart, `ports.websecure.http.middlewares` produces
    # --entryPoints.websecure.http.middlewares=..., while the flat spelling is
    # rejected outright: "ports.websecure: Additional property middlewares is
    # not allowed". The chart ships values.schema.json with
    # additionalProperties: false, so guessing here does not degrade quietly,
    # it fails the HelmChart install. Asked and answered in review on #1141.
    #
    # This MERGES over the base HelmChart's ports.websecure (proxyProtocol and
    # forwardedHeaders trustedIPs) rather than replacing it -- helm-controller
    # deep-merges valuesContent. Verified by rendering the chart with the
    # module's base values and this file together: all four arguments survive
    # (middlewares, websecure proxyProtocol and forwardedHeaders trustedIPs, and
    # the web -> websecure redirect). If trustedIPs were lost, Traefik would see
    # the load balancer's private address as the client and the allowlist would
    # refuse ALL traffic.
    #
    # The `render` job in .github/workflows/cloudflare-origin-allowlist.yml
    # re-runs exactly that check on every pull request touching this file. It
    # exists because the failure mode here is silence: a values path that stops
    # producing the argument leaves the origin open with nothing in any log to
    # say so. Validated by mutation -- the flat spelling and a removed reference
    # both fail it.
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
    #
    # Consequence for tenant custom domains, which is real even though nothing
    # exercises it yet (measured: zero non-mctl ingress hosts, zero
    # letsencrypt-http01 certificates). A custom domain must reach the platform
    # THROUGH Cloudflare -- an unproxied CNAME to <team>-<service>.mctl.ai
    # resolves to the edge, which is fine. What no longer works is proving
    # ownership by TXT and then pointing an A record straight at the origin:
    # certificates still issue, because HTTP-01 arrives on `web` and `web`
    # has no middleware, but HTTPS traffic then arrives on websecure from
    # ordinary client addresses and gets 403. The verifier in
    # wft-add-custom-domain.yaml accepts that shape today; making it reject the
    # direct-A case is tracked separately. Raised by Codex on #1141.
    ports:
      websecure:
        http:
          middlewares:
            - traefik-cloudflare-origin@kubernetescrd
