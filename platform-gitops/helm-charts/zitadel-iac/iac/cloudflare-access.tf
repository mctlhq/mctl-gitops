# Cloudflare Access signs in through ZITADEL (#1500 step 3).
#
# A public client with PKCE and no secret, so nothing has to travel from this
# state to infrastructure/cloudflare/account, which Terraform applies from
# GitHub Actions. Verified on a local v4.19.2 (#1500, 2026-10-04): with
# OIDC_AUTH_METHOD_TYPE_NONE the token endpoint requires a valid S256
# code_verifier and ignores any client secret sent with it, so a placeholder
# secret on the Cloudflare side cannot break the flow.
#
# The client id is the one value Cloudflare needs from here. It is not a
# secret, but ZITADEL generates it, so the Job writes it into
# zitadel/cloudflare-access-oidc and an operator copies it into
# infrastructure/cloudflare/account (variable zitadel_access_client_id).
# A recreate of the application would change it and silently break the
# Access login until that copy is updated, hence prevent_destroy below.
#
# Its own project, not `zitadel_project.platform`: the role check applies to
# every application of a project, and ZITADEL puts the client ids of every
# application of a project into `aud`.

locals {
  # The Access team domain (infrastructure/cloudflare/README.md, organization
  # auth_domain).
  cloudflare_access_callback = "https://mbank.cloudflareaccess.com/cdn-cgi/access/callback"

  # Who may sign in to Cloudflare Access through ZITADEL: the platform
  # admins (admins.tf), the same set that holds the Argo CD `admins` group,
  # so the two cannot drift apart. Tenant users (Vault
  # secret/platform/zitadel/users/*) are never in it. This grant is the gate;
  # Access policies may narrow it per application.
  cloudflare_access_users = local.platform_admin_user_ids
}

resource "zitadel_project" "cloudflare_access" {
  org_id = local.mctl_org_id
  name   = "Cloudflare Access"

  # Only users with a role on this project, of the organization that owns it,
  # obtain a token: a tenant user is refused with Errors.User.GrantRequired
  # before any redirect to Access. The project is granted to no tenant.
  project_role_check = true
  has_project_check  = true

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "cloudflare_access" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.cloudflare_access.id
  role_key     = "access"
  display_name = "Cloudflare Access sign-in"
}

resource "zitadel_user_grant" "cloudflare_access" {
  for_each = local.cloudflare_access_users

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.cloudflare_access.id
  role_keys  = [zitadel_project_role.cloudflare_access.role_key]
}

# A web application, since Access redirects back to a server-side callback,
# with no client authentication: PKCE is what binds the code to Access.
resource "zitadel_application_oidc" "cloudflare_access" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.cloudflare_access.id
  name       = "cloudflare-access"

  app_type          = "OIDC_APP_TYPE_WEB"
  auth_method_type  = "OIDC_AUTH_METHOD_TYPE_NONE"
  grant_types       = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types    = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris     = [local.cloudflare_access_callback]
  access_token_type = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode          = false
  # Access reads the e-mail from the ID token (email_claim_name).
  id_token_userinfo_assertion = true

  lifecycle {
    prevent_destroy = true
  }
}

# In the Job's own namespace, which its Role already lets it write. The
# provider marks client_id sensitive, so this is where an operator reads it:
#   kubectl -n zitadel get secret cloudflare-access-oidc \
#     -o jsonpath='{.data.clientID}' | base64 -d
resource "kubernetes_secret_v1" "cloudflare_access_oidc" {
  metadata {
    name      = "cloudflare-access-oidc"
    namespace = "zitadel"
    labels = {
      "app.kubernetes.io/name"       = "zitadel-iac"
      "app.kubernetes.io/managed-by" = "zitadel-iac"
    }
  }

  data = {
    clientID = zitadel_application_oidc.cloudflare_access.client_id
  }
}
