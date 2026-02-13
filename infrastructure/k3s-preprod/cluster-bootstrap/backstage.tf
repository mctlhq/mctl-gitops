resource "kubernetes_secret" "backstage_secrets" {
  metadata {
    name      = "backstage-secrets"
    namespace = "backstage"
  }

  data = {
    AUTH_GITHUB_CLIENT_ID     = var.backstage_github_client_id
    AUTH_GITHUB_CLIENT_SECRET = var.backstage_github_client_secret
  }
}

resource "kubernetes_secret" "backstage_ghcr" {
  metadata {
    name      = "ghcr-credentials"
    namespace = "backstage"
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "ghcr.io" = {
          auth = base64encode("dmitriimashkov:${var.github_repo_pat}")
        }
      }
    })
  }
}
