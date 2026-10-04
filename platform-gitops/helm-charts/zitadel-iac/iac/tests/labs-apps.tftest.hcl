# The public labs apps' sign-in clients (labs-apps.tf), run in CI
# (`tofu test`) against mocked providers. Targeted plans, as in
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
  smtp_password   = "test"
  tenant_users    = jsonencode({})
  platform_admins = jsonencode({})
}

run "labs_apps_clients_and_secrets" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.labs_apps_oidc]
  }

  # Public self-service apps: any account on the instance may sign in. A
  # project or role check would refuse everyone without a grant, which here
  # is everyone.
  assert {
    condition     = !zitadel_project.labs_apps.project_role_check && !zitadel_project.labs_apps.has_project_check
    error_message = "The labs apps project must not require a project grant or a role."
  }
  assert {
    condition = (
      zitadel_application_oidc.labs_apps["coolify-mcp"].redirect_uris == tolist(["https://coolify.mctl.ai/auth/zitadel/callback"]) &&
      zitadel_application_oidc.labs_apps["mctl-academy"].redirect_uris == tolist(["https://academy.mctl.ai/api/auth/oauth2/callback/zitadel"])
    )
    error_message = "Each app must have exactly its own callback as redirect URI."
  }
  assert {
    condition = alltrue([
      for app in zitadel_application_oidc.labs_apps :
      app.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC" && app.id_token_userinfo_assertion
    ])
    error_message = "Both apps authenticate with client_secret_basic and read the e-mail from the ID token."
  }
  # The apps read these keys by name through envFrom; a renamed key turns
  # the button off silently.
  assert {
    condition = alltrue([
      for s in kubernetes_secret_v1_data.labs_apps_oidc :
      s.metadata[0].namespace == "labs" &&
      toset(keys(s.data)) == toset(["ZITADEL_ISSUER", "ZITADEL_CLIENT_ID", "ZITADEL_CLIENT_SECRET", "ZITADEL_DISPLAY_NAME"]) &&
      s.data["ZITADEL_ISSUER"] == "https://auth.mctl.ai"
    ])
    error_message = "Each labs Secret must carry the four ZITADEL_* keys the apps read, with the auth.mctl.ai issuer."
  }
  assert {
    condition = (
      kubernetes_secret_v1_data.labs_apps_oidc["coolify-mcp"].metadata[0].name == "coolify-mcp-oidc-zitadel" &&
      kubernetes_secret_v1_data.labs_apps_oidc["mctl-academy"].metadata[0].name == "mctl-academy-oidc-zitadel"
    )
    error_message = "The Secret names must match infra-components/labs/oidc-zitadel.yaml, which grants the Job patch on them by name."
  }
}
