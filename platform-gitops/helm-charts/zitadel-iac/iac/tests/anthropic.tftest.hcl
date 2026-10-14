# Anthropic SSO (anthropic.tf), run in CI (`tofu test`) against mocked
# providers. Plans are targeted, as in admins.tftest.hcl: the root's import
# blocks crash the mock providers.

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
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({
    erpact = jsonencode({
      tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
    })
  })
}

run "the_project_refuses_users_without_a_role" {
  command = plan
  plan_options {
    target = [zitadel_project.anthropic]
  }

  assert {
    condition     = zitadel_project.anthropic.project_role_check == true && zitadel_project.anthropic.has_project_check == true
    error_message = "Without project_role_check every MCTL user, and with has_project_check off every organization's, could sign in to Anthropic."
  }
  assert {
    condition     = zitadel_project.anthropic.project_role_assertion == true
    error_message = "Without project_role_assertion the groups action sees no grants and the token carries no groups."
  }
}

run "only_personal_platform_admins_are_granted" {
  command = plan
  plan_options {
    target = [zitadel_user_grant.anthropic_admin]
  }

  assert {
    condition     = toset(keys(zitadel_user_grant.anthropic_admin)) == toset(["admin"])
    error_message = "Only the personal platform admins hold the Anthropic role: not the break-glass mctl-admin, not tenant users."
  }
}

run "the_client_is_confidential_with_the_workos_callback_only" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.anthropic]
  }

  assert {
    condition     = zitadel_application_oidc.anthropic.app_type == "OIDC_APP_TYPE_WEB" && zitadel_application_oidc.anthropic.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"
    error_message = "WorkOS authenticates with a client secret: a web client with basic auth."
  }
  assert {
    condition     = toset(zitadel_application_oidc.anthropic.redirect_uris) == toset(["https://auth.workos.com/sso/oidc/oLjmLkaVNnlHjlyQBvblz4Ock/callback"])
    error_message = "Only the WorkOS connection's callback; any other URI could receive a code for this client."
  }
  assert {
    condition     = zitadel_application_oidc.anthropic.id_token_userinfo_assertion == true
    error_message = "WorkOS reads email, names and groups from the ID token."
  }
}

run "the_groups_action_covers_the_anthropic_project" {
  command = plan
  plan_options {
    target = [zitadel_action.argocd_groups]
  }

  override_resource {
    target = zitadel_project.anthropic
    values = { id = "anthropic-project" }
  }

  assert {
    condition     = strcontains(zitadel_action.argocd_groups["MCTL"].script, "'anthropic-project'")
    error_message = "WorkOS requires a groups claim; the shared groups action must copy the Anthropic project's roles into it."
  }
}
