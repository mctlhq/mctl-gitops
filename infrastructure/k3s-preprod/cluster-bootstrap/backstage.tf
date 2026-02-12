resource "kubernetes_namespace" "backstage" {
  metadata {
    name = "backstage"
  }
}

resource "kubernetes_secret" "backstage_secrets" {
  metadata {
    name      = "backstage-secrets"
    namespace = kubernetes_namespace.backstage.metadata[0].name
  }

  data = {
    AUTH_GITHUB_CLIENT_ID     = var.backstage_github_client_id
    AUTH_GITHUB_CLIENT_SECRET = var.backstage_github_client_secret
  }
}
