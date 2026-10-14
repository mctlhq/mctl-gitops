# The Anthropic organization (claude.ai, Claude Console) signs in through
# ZITADEL. Anthropic's SSO is run by WorkOS, which has no ZITADEL preset, so
# this is its "Custom OIDC" connection: WorkOS is the relying party, and it
# asks for a confidential client with the authorization code flow, a
# discovery endpoint (https://auth.mctl.ai/.well-known/openid-configuration)
# and sub, email, given_name, family_name and groups in the ID token.
#
# Who may sign in is decided here, as for Cloudflare Access: the role and
# project checks refuse anyone without the `admins` role on this project
# before WorkOS sees them. Which Anthropic role each group maps to is set on
# Anthropic's side. Anthropic also routes a user to this connection by the
# domain of their e-mail address, so a holder of the grant whose address is
# not at a domain verified there is not sent here at all.
#
# Its own project, not `zitadel_project.platform`: the role check applies to
# every application of a project, and ZITADEL puts the client ids of every
# application of a project into `aud`.

locals {
  # The callback of the WorkOS connection, from step 2 of Anthropic's SSO
  # setup. It identifies the connection, so a new connection on Anthropic's
  # side is a new value here.
  anthropic_sso_callback = "https://auth.workos.com/sso/oidc/oLjmLkaVNnlHjlyQBvblz4Ock/callback"

  # The personal platform admins (admins.tf). Not the break-glass mctl-admin:
  # it has no mailbox, so Anthropic has no account to match it to, and the
  # Anthropic organization has its own recovery that does not depend on
  # ZITADEL.
  anthropic_users = { for user_name, user in zitadel_human_user.platform_admin : user_name => user.id }
}

resource "zitadel_project" "anthropic" {
  org_id = local.mctl_org_id
  name   = "Anthropic"

  project_role_check = true
  has_project_check  = true
  # Loads the user's grants into the token flow; without it the groups action
  # sees no grants (see zitadel_project.argocd).
  project_role_assertion = true

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "anthropic_admin" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.anthropic.id
  role_key     = "admins"
  display_name = "Anthropic admin"
}

resource "zitadel_user_grant" "anthropic_admin" {
  for_each = local.anthropic_users

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.anthropic.id
  role_keys  = [zitadel_project_role.anthropic_admin.role_key]
}

# A confidential web client: WorkOS authenticates with the client secret at
# the token endpoint. The user's roles reach `groups` through the shared
# groups action (argocd.tf); with id_token_userinfo_assertion they are in the
# ID token, which is where WorkOS reads every claim it asks for.
resource "zitadel_application_oidc" "anthropic" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.anthropic.id
  name       = "anthropic"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = [local.anthropic_sso_callback]
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = true

  # A recreate changes the client id and secret, and breaks every sign-in to
  # Anthropic until an operator enters the new pair in the WorkOS connection.
  lifecycle {
    prevent_destroy = true
  }
}

# In the Job's own namespace, which its Role already lets it write, as
# zitadel/cloudflare-access-oidc. Nothing in the cluster reads it: an
# operator copies both values into the WorkOS connection (step 4), from
#   kubectl -n zitadel get secret anthropic-sso-oidc \
#     -o jsonpath='{.data.clientID}' | base64 -d
# and the same for clientSecret.
resource "kubernetes_secret_v1" "anthropic_sso_oidc" {
  metadata {
    name      = "anthropic-sso-oidc"
    namespace = "zitadel"
    labels = {
      "app.kubernetes.io/name"       = "zitadel-iac"
      "app.kubernetes.io/managed-by" = "zitadel-iac"
    }
  }

  data = {
    clientID     = zitadel_application_oidc.anthropic.client_id
    clientSecret = zitadel_application_oidc.anthropic.client_secret
  }
}
