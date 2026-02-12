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

  set_sensitive = [
    {
      name  = "configs.secret.extra.github-client-id"
      value = var.github_oauth_client_id
    },
    {
      name  = "configs.secret.extra.github-client-secret"
      value = var.github_oauth_client_secret
    },
  ]
}
