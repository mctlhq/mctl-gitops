# The public labs apps' sign-in clients (labs-apps.tf), run in CI
# (`tofu test`) against mocked providers. Plans are targeted, as in
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

run "each_app_has_a_project_closed_to_other_organizations" {
  command = plan
  plan_options {
    target = [zitadel_project.labs_app]
  }

  assert {
    condition     = toset(keys(zitadel_project.labs_app)) == toset(["coolify-mcp", "mctl-academy"])
    error_message = "One project per app: a shared project puts each app's client id into the other's tokens."
  }
  assert {
    condition     = alltrue([for p in zitadel_project.labs_app : p.has_project_check == true])
    error_message = "has_project_check must stay on: off admits every organization of the instance, not only MCTL and the granted tenants."
  }
  assert {
    condition     = alltrue([for p in zitadel_project.labs_app : p.org_id == "100000000000000001"])
    error_message = "The projects belong to MCTL."
  }
  assert {
    condition     = zitadel_project.labs_app["coolify-mcp"].name != zitadel_project.labs_app["mctl-academy"].name
    error_message = "The two projects must be told apart by name."
  }
}

run "every_tenant_organization_is_granted_each_app" {
  command = plan
  plan_options {
    target = [zitadel_project_grant.labs_app_tenant]
  }

  # Known ids at plan time, so the grant's references can be compared.
  # Overrides apply to every instance of a resource.
  override_resource {
    target = zitadel_project.labs_app
    values = { id = "labs-app-project" }
  }
  override_resource {
    target = zitadel_org.tenant
    values = { id = "tenant-org" }
  }

  assert {
    condition = toset(keys(zitadel_project_grant.labs_app_tenant)) == toset([
      "coolify-mcp/acme", "coolify-mcp/erpact", "mctl-academy/acme", "mctl-academy/erpact",
    ])
    error_message = "Every tenant organization must be granted each app's project, or its users get no token for it (has_project_check)."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.labs_app_tenant : g.project_id == "labs-app-project"])
    error_message = "The grant must be of a labs app project."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.labs_app_tenant : g.granted_org_id == "tenant-org"])
    error_message = "The grant must go to the tenant organization."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.labs_app_tenant : g.org_id == "100000000000000001"])
    error_message = "The grant must be made by MCTL, which owns the projects."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.labs_app_tenant : g.role_keys == null])
    error_message = "The grant must carry no role keys."
  }
}

# Each attribute is one the apps depend on or one that keeps the client closed.
run "each_client_is_a_confidential_web_client_with_its_own_callback" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.labs_app]
  }

  override_resource {
    target = zitadel_project.labs_app
    values = { id = "labs-app-project" }
  }

  assert {
    condition     = toset(keys(zitadel_application_oidc.labs_app)) == toset(["coolify-mcp", "mctl-academy"])
    error_message = "Exactly the two apps have a client."
  }
  assert {
    condition     = alltrue([for key, app in zitadel_application_oidc.labs_app : app.name == key])
    error_message = "Each client is named after its app."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.project_id == "labs-app-project" && app.org_id == "100000000000000001"])
    error_message = "Each client must be in a labs app project of MCTL: has_project_check there is what limits who can sign in."
  }
  # Exactly the app's own callback: a second entry would be a second place an
  # authorization code can be sent.
  assert {
    condition     = zitadel_application_oidc.labs_app["coolify-mcp"].redirect_uris == tolist(["https://coolify.mctl.ai/auth/zitadel/callback"])
    error_message = "coolify-mcp's only redirect URI must be https://coolify.mctl.ai/auth/zitadel/callback."
  }
  assert {
    condition     = zitadel_application_oidc.labs_app["mctl-academy"].redirect_uris == tolist(["https://academy.mctl.ai/api/auth/oauth2/callback/zitadel"])
    error_message = "mctl-academy's only redirect URI must be https://academy.mctl.ai/api/auth/oauth2/callback/zitadel."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.app_type == "OIDC_APP_TYPE_WEB" && app.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"])
    error_message = "Each client must be a confidential web client authenticating with client_secret_basic, which is what both apps send."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.grant_types == tolist(["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]) && app.response_types == tolist(["OIDC_RESPONSE_TYPE_CODE"])])
    error_message = "Authorization code only: no implicit, refresh token or device grant."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.access_token_type == "OIDC_TOKEN_TYPE_BEARER"])
    error_message = "The access token must stay opaque (BEARER)."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.id_token_userinfo_assertion == true])
    error_message = "id_token_userinfo_assertion must be on: both apps read the e-mail and email_verified from the ID token."
  }
  assert {
    condition     = alltrue([for app in zitadel_application_oidc.labs_app : app.dev_mode == false])
    error_message = "dev_mode must stay off: on, ZITADEL accepts http redirects."
  }
}

# The apps read these keys by name through envFrom; a renamed or missing key
# is a half-set configuration, which both apps refuse to start with.
run "each_client_reaches_its_own_secret_in_labs" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.labs_app_oidc]
  }

  # Overrides apply to every instance, so these values cannot tell the two
  # clients apart; that each Secret takes its own client is each.key in
  # labs-apps.tf.
  override_resource {
    target = zitadel_application_oidc.labs_app
    values = { client_id = "labs-client-id", client_secret = "labs-client-secret" }
  }

  assert {
    condition     = toset(keys(kubernetes_secret_v1_data.labs_app_oidc)) == toset(["coolify-mcp", "mctl-academy"])
    error_message = "Exactly the two apps have a Secret."
  }
  # infra-components/labs/oidc-zitadel.yaml grants the Job patch on these two
  # names and nothing else.
  assert {
    condition = (
      kubernetes_secret_v1_data.labs_app_oidc["coolify-mcp"].metadata[0].name == "coolify-mcp-oidc-zitadel" &&
      kubernetes_secret_v1_data.labs_app_oidc["mctl-academy"].metadata[0].name == "mctl-academy-oidc-zitadel"
    )
    error_message = "The Secret names must match infra-components/labs/oidc-zitadel.yaml."
  }
  assert {
    condition     = alltrue([for s in kubernetes_secret_v1_data.labs_app_oidc : s.metadata[0].namespace == "labs"])
    error_message = "Both Secrets are in namespace labs, where the apps run."
  }
  assert {
    condition = alltrue([
      for s in kubernetes_secret_v1_data.labs_app_oidc :
      toset(keys(s.data)) == toset(["ZITADEL_ISSUER", "ZITADEL_CLIENT_ID", "ZITADEL_CLIENT_SECRET", "ZITADEL_DISPLAY_NAME"])
    ])
    error_message = "Each Secret must carry exactly the four ZITADEL_* keys the apps read."
  }
  assert {
    condition     = alltrue([for s in kubernetes_secret_v1_data.labs_app_oidc : nonsensitive(s.data["ZITADEL_ISSUER"]) == "https://auth.mctl.ai"])
    error_message = "ZITADEL_ISSUER must be https://auth.mctl.ai, without a trailing slash: both apps compare it with the ID token's iss."
  }
  assert {
    condition = alltrue([
      for s in kubernetes_secret_v1_data.labs_app_oidc :
      nonsensitive(s.data["ZITADEL_CLIENT_ID"]) == "labs-client-id" && nonsensitive(s.data["ZITADEL_CLIENT_SECRET"]) == "labs-client-secret"
    ])
    error_message = "ZITADEL_CLIENT_ID and ZITADEL_CLIENT_SECRET must be the application's client id and secret, in that order."
  }
  assert {
    condition     = alltrue([for s in kubernetes_secret_v1_data.labs_app_oidc : nonsensitive(s.data["ZITADEL_DISPLAY_NAME"]) == "MCTL account"])
    error_message = "The button reads \"MCTL account\"."
  }
}
