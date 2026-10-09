# The portal (app.mctl.ai) signs people in through ZITADEL instead of GitHub
# (#1500 phase 3, mctlhq/mctl-portal#150).
#
# The portal keeps knowing a person by their GitHub login: its catalog Users,
# tenant membership and the sessions of its OIDC provider are all keyed by
# it. So its clients are the ones that receive the mctl:github_login claim
# (github-login.tf), and a ZITADEL user without that claim is refused by the
# portal, never matched by e-mail and never created.
#
# A project of its own, like mctl-api's (mctl-api.tf): ZITADEL puts the
# client ids of every application of a project into `aud`, so in a shared
# project another application's tokens would carry the portal's audience.
#
# No roles: what a person may do in the portal comes from the catalog
# membership of their GitHub login, not from a ZITADEL role.

resource "zitadel_project" "portal" {
  org_id = local.mctl_org_id
  name   = "MCTL Portal"

  # Only users of MCTL, which owns the project, and of an organization it is
  # granted to (zitadel_project_grant.portal_tenant below) obtain a token for
  # it. Any other organization of the instance, present or future, stays
  # refused. No project_role_check: the project has no roles.
  has_project_check = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

# Every tenant organization, so its users can sign in to the portal:
# has_project_check is satisfied by an active grant of the project to the
# user's organization, and no user grant is needed while project_role_check
# is off (see zitadel_project_grant.mctl_api_tenant). No role keys: there is
# nothing to hand out. A grant per declared tenant rather than
# has_project_check off, which would admit every organization of the
# instance; removing a tenant removes its grant.
resource "zitadel_project_grant" "portal_tenant" {
  for_each = local.tenants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.portal.id
  granted_org_id = zitadel_org.tenant[each.key].id
}

# The ZITADEL upstream of the portal's OIDC provider
# (plugins/oidc-provider-backend, oidcProvider.upstream = zitadel or both):
# the provider signs a person in here instead of at GitHub, reads
# mctl:github_login from the ID token and issues its own session and tokens
# for that login, as its GitHub callback does.
#
# A confidential web client: client secret (sent as HTTP Basic) plus PKCE,
# redirect only to the provider's callback. The provider requests `openid`
# and reads the ID token only, so the access token stays opaque (BEARER).
# The userinfo assertion is what puts the claim of the userinfo trigger
# (github-login.tf) into the ID token; without it the claim is only in the
# userinfo response, which the provider never calls.
resource "zitadel_application_oidc" "portal_oidc_provider" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.portal.id
  name       = "portal-oidc-provider"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = ["https://app.mctl.ai/api/oidc-provider/zitadel/callback"]
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = true
}

# The portal UI's own sign-in (auth provider `oidc`, mctlhq/mctl-portal#150
# step 2, `auth.signIn` = zitadel or both): Backstage signs a person in here
# and resolves them to the catalog User of their mctl:github_login.
#
# A confidential web client like portal_oidc_provider, redirecting only to
# the Backstage auth handler. Unlike the provider's client it also has the
# refresh-token grant: Backstage refreshes its session with the refresh token
# ZITADEL returns for `offline_access`, and without the grant every session
# would end when the first access token expires. The userinfo assertion puts
# mctl:github_login into the ID token, which is where the portal reads it.
resource "zitadel_application_oidc" "portal_ui" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.portal.id
  name       = "portal"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = ["https://app.mctl.ai/api/auth/oidc/handler/frame"]
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = true
}

locals {
  # The clients that receive mctl:github_login: the portal's two, whose ids
  # ZITADEL generates, and any listed in github_login_client_ids. A client id
  # is public (it is in every authorization URL); the provider marks it
  # sensitive, which would hide the whole action script in the plan.
  github_login_clients = concat(
    var.github_login_client_ids,
    [
      nonsensitive(zitadel_application_oidc.portal_oidc_provider.client_id),
      nonsensitive(zitadel_application_oidc.portal_ui.client_id),
    ],
  )
}

# backstage/backstage-oidc-zitadel is pre-created empty by the
# mctl-portal-oidc-zitadel Application, which also lets this Job's service
# account read and patch it by name, nothing else
# (infra-components/mctl-platform/mctl-portal/oidc-zitadel.yaml).
resource "kubernetes_secret_v1_data" "portal_oidc" {
  metadata {
    name      = "backstage-oidc-zitadel"
    namespace = "backstage"
  }

  # The keys are the env vars the portal's app-config substitutes:
  # OIDC_ZITADEL_* into oidcProvider.zitadel, AUTH_OIDC_* into
  # auth.providers.oidc. Neither is used while its switch
  # (oidcProvider.upstream, auth.signIn) is github, the default.
  data = {
    OIDC_ZITADEL_CLIENT_ID     = zitadel_application_oidc.portal_oidc_provider.client_id
    OIDC_ZITADEL_CLIENT_SECRET = zitadel_application_oidc.portal_oidc_provider.client_secret
    AUTH_OIDC_CLIENT_ID        = zitadel_application_oidc.portal_ui.client_id
    AUTH_OIDC_CLIENT_SECRET    = zitadel_application_oidc.portal_ui.client_secret
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
