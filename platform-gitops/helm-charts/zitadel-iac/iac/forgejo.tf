# Forgejo (git.mctl.ai) signs in through ZITADEL (#1520 S4).
#
# ZITADEL generates the client secret itself, so it never exists in git or in
# anyone's hands: it goes from this state straight into the Secret
# forgejo/forgejo-oidc-zitadel, which the forgejo Application pre-creates and
# lets this Job's service account read and patch by name, nothing else
# (infra-components/data/forgejo/oidc-zitadel.yaml). The forgejo chart's
# init container registers it as the authentication source "ZITADEL".
#
# Who may sign in is decided by Forgejo, not here: registration stays
# disabled there, so a ZITADEL identity can only be linked to an existing
# Forgejo account (by that account's own credentials), never create one.

data "zitadel_orgs" "mctl" {
  name        = "MCTL"
  name_method = "TEXT_QUERY_METHOD_EQUALS"
}

locals {
  # The instance's first organization (FirstInstance.Org in
  # bootstrap/templates/core-infra/zitadel.yaml). Platform applications live
  # there; tenant organizations (tenants.tf) only hold their users. one()
  # fails on several matches; zitadel_project's precondition covers none.
  mctl_org_id = one(data.zitadel_orgs.mctl.ids)

  forgejo_url = "https://git.mctl.ai"
  # Forgejo's callback path carries the authentication source name, so this
  # must match the name in the forgejo chart's gitea.oauth entry.
  forgejo_auth_source = "ZITADEL"
}

resource "zitadel_project" "platform" {
  org_id = local.mctl_org_id
  name   = "MCTL platform"

  lifecycle {
    # org_id is optional on this resource, so a missing organization would
    # not fail the plan by itself: one() yields null for zero matches and the
    # project would land wherever the API defaults to.
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_application_oidc" "forgejo" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.platform.id
  name       = "forgejo"

  app_type                  = "OIDC_APP_TYPE_WEB"
  auth_method_type          = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types               = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types            = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris             = ["${local.forgejo_url}/user/oauth2/${local.forgejo_auth_source}/callback"]
  post_logout_redirect_uris = ["${local.forgejo_url}/"]
  access_token_type         = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                  = false
  # Forgejo reads e-mail and name from the ID token.
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "forgejo_oidc" {
  metadata {
    name      = "forgejo-oidc-zitadel"
    namespace = "forgejo"
  }

  # The key names the forgejo chart expects in gitea.oauth[].existingSecret.
  data = {
    key    = zitadel_application_oidc.forgejo.client_id
    secret = zitadel_application_oidc.forgejo.client_secret
  }

  field_manager = "zitadel-iac"
  # The Secret is created by Argo CD with no data; nothing else owns these
  # fields, so taking them over on the first apply is expected.
  force = true
}
