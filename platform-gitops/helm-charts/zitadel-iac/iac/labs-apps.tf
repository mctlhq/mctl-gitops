# The public labs applications offer "Log in with MCTL account" next to
# their own GitHub and Google sign-in (owner decision D4 on #1500: an extra
# provider, never a replacement): coolify-mcp (coolify.mctl.ai,
# mctlhq/mctl-coolify-mcp#10) and mctl-academy (academy.mctl.ai,
# mctlhq/mctl-academy#279).
#
# This file creates the clients and writes each one's credentials into a
# Secret in namespace labs. It turns nothing on: an app offers the button
# only once its Deployment reads that Secret (an `envFrom` entry in
# services/labs/<app>/values.yaml, a change of its own), and both apps treat
# the absence of ZITADEL_* as "no ZITADEL".
#
# Both apps key a ZITADEL user by `sub` alone. Neither matches a ZITADEL
# sign-in to a GitHub or Google user by e-mail, and neither grants anything
# of the platform's: a sign-in is a personal coolify-mcp tenant record or an
# academy learner account.
#
# One project per app, not one for both: ZITADEL puts the client ids of
# every application of a project into `aud` (see mctl-api.tf), so in a
# shared project a token issued to one app would carry the other's audience.
# Both apps also check `azp`; separate projects mean that check is not the
# only thing between them.

locals {
  labs_apps = {
    coolify-mcp = {
      project = "Coolify MCP"
      # MCP_PUBLIC_URL (services/labs/coolify-mcp/values.yaml) +
      # /auth/zitadel/callback (mctl-coolify-mcp src/lib/identity.ts).
      redirect_uri = "https://coolify.mctl.ai/auth/zitadel/callback"
      secret       = "coolify-mcp-oidc-zitadel"
    }
    mctl-academy = {
      project = "MCTL Academy"
      # BETTER_AUTH_URL + better-auth's generic OAuth callback for provider
      # id `zitadel` (mctl-academy server/auth.mjs).
      redirect_uri = "https://academy.mctl.ai/api/auth/oauth2/callback/zitadel"
      secret       = "mctl-academy-oidc-zitadel"
    }
  }

  # "<app>/<tenant>" for every app and every declared tenant.
  labs_app_tenant_grants = merge([
    for app, _ in local.labs_apps : {
      for tenant, _ in local.tenants : "${app}/${tenant}" => { app = app, tenant = tenant }
    }
  ]...)
}

resource "zitadel_project" "labs_app" {
  for_each = local.labs_apps

  org_id = local.mctl_org_id
  name   = each.value.project

  # Users of MCTL, which owns the project, and of a tenant organization it
  # is granted to below. Any other organization of the instance, present or
  # future, is refused by ZITADEL itself. No project_role_check: the apps
  # have no roles and every account that may sign in is an ordinary user
  # there. Whether these apps should instead admit every account of the
  # instance (has_project_check off) is an owner decision; today the two
  # sets are the same people, since login_policy.tf allows no
  # self-registration and every organization is MCTL or a declared tenant.
  has_project_check = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

# Every tenant organization, as for MCTL API (mctl-api.tf): the set is the
# tenant list in Vault, and removing a tenant removes its grants. No role
# keys: there are no roles to hand out.
resource "zitadel_project_grant" "labs_app_tenant" {
  for_each = local.labs_app_tenant_grants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.labs_app[each.value.app].id
  granted_org_id = zitadel_org.tenant[each.value.tenant].id
}

# Confidential web clients, the shape of mctl_api_oauth (mctl-api.tf):
# client secret sent as HTTP Basic, authorization code only, redirect to the
# app's own callback and nowhere else. Both apps add PKCE (S256) themselves
# and read the ID token only, after verifying its signature, iss, aud/azp
# and expiry; the userinfo assertion puts the e-mail and email_verified into
# that token. The access token stays opaque (BEARER): nothing verifies it as
# a JWT, and academy uses it only to ask userinfo.
resource "zitadel_application_oidc" "labs_app" {
  for_each = local.labs_apps

  org_id     = local.mctl_org_id
  project_id = zitadel_project.labs_app[each.key].id
  name       = each.key

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = [each.value.redirect_uri]
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "labs_app_oidc" {
  for_each = local.labs_apps

  metadata {
    name      = each.value.secret
    namespace = "labs"
  }

  # The keys are the apps' own variable names, so the Secret can be read
  # with envFrom as it is. The issuer is here and not in values.yaml `env`:
  # mctl_deploy_service drops env values that contain a colon. Each Secret
  # takes the credentials of the application with its own key, each.key.
  data = {
    ZITADEL_ISSUER        = "https://auth.mctl.ai"
    ZITADEL_CLIENT_ID     = zitadel_application_oidc.labs_app[each.key].client_id
    ZITADEL_CLIENT_SECRET = zitadel_application_oidc.labs_app[each.key].client_secret
    ZITADEL_DISPLAY_NAME  = "MCTL account"
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data
  # (infra-components/labs/oidc-zitadel.yaml); see forgejo.tf.
  force = true
}
