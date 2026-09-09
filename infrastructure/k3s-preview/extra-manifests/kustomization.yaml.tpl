apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - letsencrypt-prod.yaml
  - letsencrypt-staging.yaml
  - cert-manager-helmchartconfig.yaml
  # traefik-helmchartconfig.yaml will reference this Middleware from the
  # websecure entrypoint -- that reference lands in the follow-up pull request,
  # not this one -- and a reference to a Middleware that does not exist takes
  # down every router on that entrypoint. Listing this file first does NOT
  # enforce an order: kustomize sorts by kind and ignores the order of this
  # list. Measured -- `kubectl kustomize` emits HelmChartConfig before
  # Middleware with either listing. The ordering guarantee comes only from the
  # two landing in separate `terraform apply` runs (#1119); this position is
  # documentation of intent.
  - cloudflare-origin-allowlist.yaml
  - traefik-helmchartconfig.yaml
  - kured.yaml
  - metrics-server-resources-patch.yaml
