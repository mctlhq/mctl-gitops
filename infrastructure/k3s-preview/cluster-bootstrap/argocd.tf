resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "9.4.1"
  namespace        = "argocd"
  create_namespace = true
  wait             = true
  wait_for_jobs    = true
  values = [
    file("${path.module}/helm-values/argocd.yaml"),
  ]

  # All secrets now managed by ExternalSecrets:
  # - argocd-github-oauth: OAuth credentials
  # - argocd-repo-credentials: GitHub PAT for repo access
  # No set_sensitive needed!
}
