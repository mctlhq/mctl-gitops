# Tenant access to the MCTL API project and its /oauth/authorize upstream
# client (mctl-api.tf), run in CI (`tofu test`) against mocked providers. Plans are targeted, as in
# admins.tftest.hcl: the root's import blocks crash the mock providers.

mock_provider "zitadel" {
  mock_data "zitadel_orgs" {
    defaults = { ids = ["100000000000000001"] }
  }
  mock_data "zitadel_human_users" {
    defaults = { user_ids = ["100000000000000002"] }
  }
}

mock_provider "kubernetes" {}

variables {
  smtp_password = "test"
  # A valid value, as in the other test files: targeted plans prune the
  # validation of platform_admins today, which nothing here should rely on.
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({
    acme = jsonencode({
      auser = jsonencode({ email = "a@example.com", first_name = "A", last_name = "U" })
    })
    erpact = jsonencode({
      tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
    })
  })
}

run "every_tenant_organization_is_granted_mctl_api" {
  command = plan
  plan_options {
    target = [zitadel_project_grant.mctl_api_tenant]
  }

  # Known ids at plan time, so the grant's references can be compared.
  # Overrides apply to every instance of a resource.
  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "mctl-api-project" }
  }
  override_resource {
    target = zitadel_org.tenant
    values = { id = "tenant-org" }
  }

  assert {
    condition     = toset(keys(zitadel_project_grant.mctl_api_tenant)) == toset(["acme", "erpact"])
    error_message = "Every tenant organization must be granted MCTL API, or its users get no token for it (has_project_check)."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.mctl_api_tenant : g.project_id == "mctl-api-project"])
    error_message = "The grant must be of the MCTL API project."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.mctl_api_tenant : g.granted_org_id == "tenant-org"])
    error_message = "The grant must go to the tenant organization."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.mctl_api_tenant : g.org_id == "100000000000000001"])
    error_message = "The grant must be made by MCTL, which owns the project."
  }
  # mctl-api reads no ZITADEL role; a tenant organization must have none to
  # hand out here.
  assert {
    condition     = alltrue([for g in zitadel_project_grant.mctl_api_tenant : g.role_keys == null])
    error_message = "The grant must carry no role keys."
  }
}

run "mctl_api_stays_closed_to_other_organizations" {
  command = plan
  plan_options {
    target = [zitadel_project.mctl_api]
  }
  assert {
    condition     = zitadel_project.mctl_api.has_project_check == true
    error_message = "has_project_check must stay on: off admits every organization of the instance, not only the granted tenants."
  }
}

# The client mctl-api signs people in with under OAUTH_UPSTREAM=zitadel or
# both (mctl-api#467). Each attribute is one mctl-api depends on or one that
# keeps the client closed.
run "oauth_upstream_client_is_a_confidential_pkce_web_client" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.mctl_api_oauth]
  }

  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "mctl-api-project" }
  }

  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.name == "mctl-api-oauth"
    error_message = "The client is named mctl-api-oauth."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.project_id == "mctl-api-project" && zitadel_application_oidc.mctl_api_oauth.org_id == "100000000000000001"
    error_message = "The client must be in the MCTL API project of MCTL: has_project_check there is what limits who can sign in."
  }
  # Exactly mctl-api's callback (SELF_URL + /oauth/zitadel/callback): a second
  # entry would be a second place an authorization code can be sent.
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.redirect_uris == tolist(["https://api.mctl.ai/oauth/zitadel/callback"])
    error_message = "The only redirect URI must be https://api.mctl.ai/oauth/zitadel/callback."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.app_type == "OIDC_APP_TYPE_WEB" && zitadel_application_oidc.mctl_api_oauth.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"
    error_message = "The client must be a confidential web client authenticating with client_secret_basic."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.grant_types == tolist(["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]) && zitadel_application_oidc.mctl_api_oauth.response_types == tolist(["OIDC_RESPONSE_TYPE_CODE"])
    error_message = "Authorization code only: no implicit, refresh token or device grant."
  }
  # Every app of the project shares its audience, so a JWT access token of
  # this client would pass mctl-api's bearer check.
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.access_token_type == "OIDC_TOKEN_TYPE_BEARER"
    error_message = "The access token must stay opaque (BEARER), never JWT."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.id_token_userinfo_assertion == true
    error_message = "id_token_userinfo_assertion must be on: mctl-api reads preferred_username from the ID token."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_api_oauth.dev_mode == false
    error_message = "dev_mode must stay off: on, ZITADEL accepts http redirects."
  }
}

# The Job patches one Secret for three consumers. The new keys must carry the
# new client's credentials, not the link client's, and the keys mctl-api and
# the CLI already read must stay.
run "oauth_upstream_client_reaches_the_mctl_api_secret" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.mctl_api_oidc]
  }

  override_resource {
    target = zitadel_application_api.mctl_api
    values = { client_id = "api-client-id" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_cli
    values = { client_id = "cli-client-id" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_api_link
    values = { client_id = "link-client-id", client_secret = "link-client-secret" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_api_oauth
    values = { client_id = "oauth-client-id", client_secret = "oauth-client-secret" }
  }

  assert {
    condition     = kubernetes_secret_v1_data.mctl_api_oidc.metadata[0].name == "mctl-api-oidc-zitadel" && kubernetes_secret_v1_data.mctl_api_oidc.metadata[0].namespace == "mctl-api"
    error_message = "The keys go into mctl-api/mctl-api-oidc-zitadel, the Secret the chart's oauthZitadelSecret names."
  }
  assert {
    condition = toset(keys(kubernetes_secret_v1_data.mctl_api_oidc.data)) == toset([
      "MCTL_OIDC_PROVIDERS",
      "MCTL_CLI_ZITADEL_CLIENT_ID",
      "ZITADEL_LINK_CLIENT_ID",
      "ZITADEL_LINK_CLIENT_SECRET",
      "OAUTH_ZITADEL_CLIENT_ID",
      "OAUTH_ZITADEL_CLIENT_SECRET",
    ])
    error_message = "mctl-api/mctl-api-oidc-zitadel must carry exactly the six keys its consumers read."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["OAUTH_ZITADEL_CLIENT_ID"]) == "oauth-client-id"
    error_message = "OAUTH_ZITADEL_CLIENT_ID must be the mctl-api-oauth client id."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["OAUTH_ZITADEL_CLIENT_SECRET"]) == "oauth-client-secret"
    error_message = "OAUTH_ZITADEL_CLIENT_SECRET must be the mctl-api-oauth client secret."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["ZITADEL_LINK_CLIENT_ID"]) == "link-client-id" && nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["ZITADEL_LINK_CLIENT_SECRET"]) == "link-client-secret"
    error_message = "The link client's keys must still carry the link client's credentials."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_CLI_ZITADEL_CLIENT_ID"]) == "cli-client-id"
    error_message = "MCTL_CLI_ZITADEL_CLIENT_ID must still be the CLI's client id."
  }
  # `name` and `issuer` key external_identities, and OAUTH_ZITADEL_PROVIDER
  # and ZITADEL_LINK_PROVIDER both default to this entry's name.
  assert {
    condition = nonsensitive(jsondecode(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_OIDC_PROVIDERS"])) == [
      { name = "zitadel", issuer = "https://auth.mctl.ai", audiences = ["api-client-id"] },
    ]
    error_message = "MCTL_OIDC_PROVIDERS must stay the single `zitadel` entry with the API application's audience."
  }
}
