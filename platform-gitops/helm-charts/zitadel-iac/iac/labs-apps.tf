# Public labs applications that offer "Log in with MCTL account" next to
# their own GitHub/Google sign-in (owner decision D4: an extra provider,
# never a replacement): coolify-mcp (coolify.mctl.ai, mctl-coolify-mcp#10)
# and mctl-academy (academy.mctl.ai, mctl-academy#279). Both apps turn the
# button on only when all of ZITADEL_ISSUER, ZITADEL_CLIENT_ID and
# ZITADEL_CLIENT_SECRET are set, and both key a ZITADEL user by its `sub`
# alone: no e-mail match ever reaches a GitHub or Google user's data.
#
# Anyone with an account on this instance may sign in: no project or role
# check, unlike every other project here. These apps grant nothing of the
# platform's; a ZITADEL sign-in there is a personal, self-service identity
# (a coolify-mcp tenant record of its own, an academy learner). Who has an
# account is still decided by login_policy.tf, which allows no
# self-registration today, so in practice the button serves the users this
# repository creates (admins.tf, tenants.tf) until that policy changes.

locals {
  zitadel_issuer = "https://auth.mctl.ai"

  labs_zitadel_apps = {
    coolify-mcp = {
      # MCP_PUBLIC_URL in services/labs/coolify-mcp/values.yaml.
      redirect_uri = "https://coolify.mctl.ai/auth/zitadel/callback"
      secret       = "coolify-mcp-oidc-zitadel"
    }
    mctl-academy = {
      # better-auth's generic OAuth callback under BETTER_AUTH_URL.
      redirect_uri = "https://academy.mctl.ai/api/auth/oauth2/callback/zitadel"
      secret       = "mctl-academy-oidc-zitadel"
    }
  }
}

resource "zitadel_project" "labs_apps" {
  org_id = local.mctl_org_id
  name   = "Labs apps"

  project_role_check     = false
  has_project_check      = false
  project_role_assertion = false

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

# Confidential web clients with the code flow. Both apps add PKCE (S256) and
# authenticate with client_secret_basic, and both verify the ID token's
# signature, iss, aud/azp and expiry before using its sub.
resource "zitadel_application_oidc" "labs_apps" {
  for_each = local.labs_zitadel_apps

  org_id     = local.mctl_org_id
  project_id = zitadel_project.labs_apps.id
  name       = each.key

  app_type          = "OIDC_APP_TYPE_WEB"
  auth_method_type  = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types       = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types    = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris     = [each.value.redirect_uri]
  access_token_type = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode          = false
  # coolify-mcp reads the e-mail it displays from the ID token only.
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "labs_apps_oidc" {
  for_each = local.labs_zitadel_apps

  metadata {
    name      = each.value.secret
    namespace = "labs"
  }

  # Read by the app through envFrom (services/labs/<app>/values.yaml). The
  # keys are the apps' own variable names. The issuer travels here and not
  # in values.yaml `env`: mctl_deploy_service drops env values containing a
  # colon.
  data = {
    ZITADEL_ISSUER        = local.zitadel_issuer
    ZITADEL_CLIENT_ID     = zitadel_application_oidc.labs_apps[each.key].client_id
    ZITADEL_CLIENT_SECRET = zitadel_application_oidc.labs_apps[each.key].client_secret
    ZITADEL_DISPLAY_NAME  = "MCTL account"
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data
  # (infra-components/labs/oidc-zitadel.yaml); see forgejo.tf.
  force = true
}
