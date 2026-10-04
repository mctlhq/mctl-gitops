# Grafana (grafana.mctl.ai) signs in through ZITADEL instead of Dex.
#
# Admins only for now. Grafana runs a single organization on an emptyDir
# database, so it has no tenant organization a tenant role could map to:
# every dashboard and datasource in it is cluster-wide. A tenant role here
# would therefore mean cross-tenant read access. Tenant organizations, with
# datasources scoped to the tenant's namespace and an opt-in "grafana": true
# flag, are a later change; until then this project has no tenant roles and
# project_role_check refuses every tenant user a token.
#
# Like Argo CD (argocd.tf): a project of its own, and the user's roles on it
# only in the `groups` claim (the shared groups action in argocd.tf), which
# Grafana's role_attribute_path maps to Grafana Admin.

locals {
  grafana_url = "https://grafana.mctl.ai"
  # Matched by role_attribute_path in
  # bootstrap/templates/observability/monitoring.yaml.
  grafana_admin_group = "admins"
}

resource "zitadel_project" "grafana" {
  org_id = local.mctl_org_id
  name   = "Grafana"

  project_role_check = true
  has_project_check  = true
  # Loads the user's grants into the token flow; without it the groups action
  # sees no grants (see zitadel_project.argocd).
  project_role_assertion = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "grafana_admin" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.grafana.id
  role_key     = local.grafana_admin_group
  display_name = "Grafana admin"
}

# The platform admins (admins.tf).
resource "zitadel_user_grant" "grafana_admin" {
  for_each = local.platform_admin_user_ids

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.grafana.id
  role_keys  = [zitadel_project_role.grafana_admin.role_key]
}

# A confidential web client with the code flow; Grafana adds PKCE (use_pkce)
# on top of the client secret.
resource "zitadel_application_oidc" "grafana" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.grafana.id
  name       = "grafana"

  app_type                  = "OIDC_APP_TYPE_WEB"
  auth_method_type          = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types               = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types            = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris             = ["${local.grafana_url}/login/generic_oauth"]
  post_logout_redirect_uris = ["${local.grafana_url}/"]
  access_token_type         = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                  = false
  # Grafana reads `groups` from the ID token before it calls userinfo.
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "grafana_oidc" {
  metadata {
    name      = "grafana-oidc-zitadel"
    namespace = "monitoring"
  }

  # Read by Grafana as GF_AUTH_GENERIC_OAUTH_CLIENT_ID / _CLIENT_SECRET
  # (envValueFrom in monitoring.yaml).
  data = {
    client-id     = zitadel_application_oidc.grafana.client_id
    client-secret = zitadel_application_oidc.grafana.client_secret
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
