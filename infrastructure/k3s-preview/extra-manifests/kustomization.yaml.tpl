apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - letsencrypt-prod.yaml
  - letsencrypt-staging.yaml
  - cert-manager-helmchartconfig.yaml
  # Must precede traefik-helmchartconfig.yaml: that file references this
  # Middleware from the websecure entrypoint, and a reference to a
  # Middleware that does not exist takes down every router on it.
  # Ordering within a single apply is the second line of defence -- the
  # first is that the two land in separate terraform applies (#1119).
  - cloudflare-origin-allowlist.yaml
  - traefik-helmchartconfig.yaml
  - kured.yaml
  - metrics-server-resources-patch.yaml
