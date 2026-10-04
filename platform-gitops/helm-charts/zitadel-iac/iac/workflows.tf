# Argo Workflows (workflows.mctl.ai) signs in through ZITADEL instead of Dex.
#
# Like Argo CD (argocd.tf): a project of its own, roles `admins` and one per
# tenant, and the user's roles on this project only in the `groups` claim
# (the shared groups action in argocd.tf). Argo Workflows maps that claim to a
# ServiceAccount through its SSO RBAC rules (platform-gitops/argo-workflows):
# `admins` to argo-workflows-admin (every namespace), a tenant name to
# sso-team-<tenant>, which is bound in that tenant's namespace only. A user
# whose groups match no rule is refused by the Argo server.
#
# Its own project, so no other application's token carries Argo Workflows'
# audience, and project_role_check refuses a token to anyone without a role
# here: a tenant user is never let in by default.

locals {
  workflows_url = "https://workflows.mctl.ai"
  # The rbac-rule of argo-workflows-admin
  # (platform-gitops/argo-workflows/config/sa-and-rbac.yaml).
  workflows_admin_group = "admins"
}

resource "zitadel_project" "workflows" {
  org_id = local.mctl_org_id
  name   = "Argo Workflows"

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

resource "zitadel_project_role" "workflows_admin" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.workflows.id
  role_key     = local.workflows_admin_group
  display_name = "Argo Workflows admin"
}

resource "zitadel_project_role" "workflows_tenant" {
  for_each = local.tenants

  org_id       = local.mctl_org_id
  project_id   = zitadel_project.workflows.id
  role_key     = each.key
  display_name = "Argo Workflows tenant ${each.key}"

  lifecycle {
    # A tenant named like the admin group would hand argo-workflows-admin to
    # every opted-in user of that tenant.
    precondition {
      condition     = each.key != local.workflows_admin_group
      error_message = "Tenant \"${each.key}\" collides with the Argo Workflows admin group; admins are granted through platform_admin_user_ids only."
    }
  }
}

# A tenant organization may hand out its own tenant role, and no other.
resource "zitadel_project_grant" "workflows_tenant" {
  for_each = local.tenants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.workflows.id
  granted_org_id = zitadel_org.tenant[each.key].id
  role_keys      = [zitadel_project_role.workflows_tenant[each.key].role_key]
}

# Opt-in, like Argo CD: only a tenant user whose Vault entry carries
# "workflows": true holds their tenant's role. Membership of a tenant
# organization alone grants no Argo Workflows access.
resource "zitadel_user_grant" "workflows_tenant" {
  for_each = { for key, user in local.users : key => user if try(user.workflows, false) == true }

  org_id           = zitadel_org.tenant[each.value.tenant].id
  user_id          = zitadel_human_user.tenant[each.key].id
  project_id       = zitadel_project.workflows.id
  project_grant_id = zitadel_project_grant.workflows_tenant[each.value.tenant].id
  role_keys        = [zitadel_project_role.workflows_tenant[each.value.tenant].role_key]
}

# The platform admins (admins.tf).
resource "zitadel_user_grant" "workflows_admin" {
  for_each = local.platform_admin_user_ids

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.workflows.id
  role_keys  = [zitadel_project_role.workflows_admin.role_key]
}

# The Argo server is a confidential client with the code flow; it presents
# exactly one redirect URI (sso.redirectUrl in
# bootstrap/templates/core-infra/argo-workflows.yaml).
resource "zitadel_application_oidc" "workflows" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.workflows.id
  name       = "argo-workflows"

  app_type                  = "OIDC_APP_TYPE_WEB"
  auth_method_type          = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types               = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types            = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris             = ["${local.workflows_url}/oauth2/callback"]
  post_logout_redirect_uris = ["${local.workflows_url}/"]
  access_token_type         = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                  = false
  # The Argo server reads `groups` from the ID token.
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "workflows_oidc" {
  metadata {
    name      = "argo-workflows-sso-zitadel"
    namespace = "argo-workflows"
  }

  # The keys server.sso.clientId / clientSecret name.
  data = {
    client-id     = zitadel_application_oidc.workflows.client_id
    client-secret = zitadel_application_oidc.workflows.client_secret
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
