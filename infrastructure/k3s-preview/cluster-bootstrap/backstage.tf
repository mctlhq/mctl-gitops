# backstage-secrets now managed by ExternalSecret (backstage-oauth)
# See: platform-gitops/apps/templates/backstage-secrets.yaml

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
