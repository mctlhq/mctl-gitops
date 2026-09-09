apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - letsencrypt-prod.yaml
  - letsencrypt-staging.yaml
  - cert-manager-helmchartconfig.yaml
  # traefik-helmchartconfig.yaml references this Middleware from the websecure
  # entrypoint, and a reference to a Middleware that does not exist takes down
  # every router on it. Listing this file first does NOT enforce that order:
  # kustomize sorts by kind and ignores the order of this list. Measured --
  # `kubectl kustomize` emits HelmChartConfig before Middleware with either
  # listing. The ordering guarantee comes only from the two landing in separate
  # `terraform apply` runs (#1119); this position is documentation of intent.
  - cloudflare-origin-allowlist.yaml
  - traefik-helmchartconfig.yaml
  - kured.yaml
  - metrics-server-resources-patch.yaml
