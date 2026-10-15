# The customers organization and the identity hook wiring (customers.tf), run
# in CI (`tofu test`) against mocked providers. Plans are targeted, as in
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
  smtp_password        = "test"
  customers_github_idp = jsonencode({ client_id = "test-id", client_secret = "test-secret" })
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({
    erpact = jsonencode({
      tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
    })
  })
}

run "the_login_policy_admits_github_only" {
  command = plan
  plan_options {
    target = [zitadel_login_policy.customers]
  }

  assert {
    condition = (
      zitadel_login_policy.customers.user_login == false &&
      zitadel_login_policy.customers.allow_register == false &&
      zitadel_login_policy.customers.passwordless_type == "PASSWORDLESS_TYPE_NOT_ALLOWED" &&
      length(zitadel_login_policy.customers.second_factors) == 0 &&
      length(zitadel_login_policy.customers.multi_factors) == 0
    )
    error_message = "customers must have no local sign-in, no registration form, no passkeys and no second factors: GitHub is the only way in."
  }
  assert {
    condition     = zitadel_login_policy.customers.force_mfa == false && zitadel_login_policy.customers.force_mfa_local_only == true
    error_message = "No ZITADEL second factor after GitHub (owner decision, stage B); force_mfa_local_only keeps any local path from skipping MFA."
  }
}

run "the_idp_creates_but_never_links" {
  command = plan
  plan_options {
    target = [zitadel_org_idp_github.customers]
  }

  assert {
    condition = (
      zitadel_org_idp_github.customers.is_linking_allowed == false &&
      zitadel_org_idp_github.customers.auto_linking == "AUTO_LINKING_OPTION_UNSPECIFIED" &&
      zitadel_org_idp_github.customers.is_creation_allowed == true &&
      zitadel_org_idp_github.customers.is_auto_creation == true
    )
    error_message = "A GitHub identity must never attach to an existing account; accounts are created by the hook-shaped intent only."
  }
  assert {
    condition     = contains(tolist(zitadel_org_idp_github.customers.scopes), "user:email")
    error_message = "The hook reads /user/emails with the intent token, which needs the user:email scope."
  }
}

run "the_gate_targets_interrupt_and_the_token_target_does_not" {
  command = plan
  plan_options {
    target = [
      zitadel_action_target.identity_intent,
      zitadel_action_target.identity_create_user,
      zitadel_action_target.identity_token_claims,
    ]
  }

  assert {
    condition     = zitadel_action_target.identity_intent.interrupt_on_error && zitadel_action_target.identity_create_user.interrupt_on_error
    error_message = "Without interrupt_on_error ZITADEL ignores the hook's refusals and the gate is open."
  }
  assert {
    condition     = !zitadel_action_target.identity_token_claims.interrupt_on_error
    error_message = "An interrupting token function blocks admin tokens and burns refresh tokens when the hook fails (B0 item 5)."
  }
  # interruptOnError cannot be changed in place (B0 item 5), so the flag is
  # part of the name and a flip replaces the target.
  assert {
    condition = alltrue([
      for t in [zitadel_action_target.identity_intent, zitadel_action_target.identity_create_user, zitadel_action_target.identity_token_claims] :
      endswith(t.name, t.interrupt_on_error ? "-interrupt" : "-nointerrupt")
    ])
    error_message = "A target's name must end in -interrupt or -nointerrupt matching interrupt_on_error, so flipping the flag replaces the target."
  }
  assert {
    condition = alltrue([
      for t in [zitadel_action_target.identity_intent, zitadel_action_target.identity_create_user, zitadel_action_target.identity_token_claims] :
      startswith(t.endpoint, "https://api.mctl.ai/api/v1/webhooks/zitadel/") && t.target_type == "REST_CALL"
    ])
    error_message = "Targets are restCall on mctl-api's public hostname (DenyList refuses private addresses)."
  }
}

run "every_user_creating_method_is_gated" {
  command = plan
  plan_options {
    target = [zitadel_action_execution_request.identity_create_user]
  }

  assert {
    condition = toset(keys(zitadel_action_execution_request.identity_create_user)) == toset([
      "/zitadel.user.v2.UserService/CreateUser",
      "/zitadel.user.v2.UserService/AddHumanUser",
      "/zitadel.user.v2beta.UserService/AddHumanUser",
      "/zitadel.resources.user.v3alpha.ZITADELUsers/CreateUser",
      "/zitadel.management.v1.ManagementService/AddHumanUser",
      "/zitadel.management.v1.ManagementService/ImportHumanUser",
      "/zitadel.management.v1.ManagementService/AddMachineUser",
      "/zitadel.admin.v1.AdminService/ImportData",
      "/zitadel.user.v2.UserService/AddIDPLink",
      "/zitadel.user.v2beta.UserService/AddIDPLink",
      "/zitadel.resources.user.v3alpha.ZITADELUsers/AddIDPAuthenticator",
      "/zitadel.management.v1.ManagementService/SetUserMetadata",
      "/zitadel.management.v1.ManagementService/BulkSetUserMetadata",
      "/zitadel.user.v2.UserService/SetUserMetadata",
      "/zitadel.user.v2.UserService/UpdateUser",
    ])
    error_message = "The creation gate must cover every user-creating, IdP-linking and user-metadata-writing method of ZITADEL v4.19.2 (B0 found v1 ImportHumanUser bypassing a v2-only gate)."
  }
}

run "the_clients_are_separate_public_pkce_clients" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.mctl_web, zitadel_application_oidc.mctl_web_dev]
  }

  # Mocked ids are otherwise identical; distinct ids make the comparison
  # below about the references, not about the mock.
  override_resource {
    target = zitadel_project.mctl_web
    values = { id = "200000000000000001" }
  }
  override_resource {
    target = zitadel_project.mctl_web_dev
    values = { id = "200000000000000002" }
  }

  assert {
    condition     = zitadel_application_oidc.mctl_web.project_id != zitadel_application_oidc.mctl_web_dev.project_id
    error_message = "mctl-web-dev needs a project of its own, or its tokens would carry mctl-web's audience."
  }
  assert {
    condition = alltrue([
      for a in [zitadel_application_oidc.mctl_web, zitadel_application_oidc.mctl_web_dev] :
      a.auth_method_type == "OIDC_AUTH_METHOD_TYPE_NONE"
    ])
    error_message = "Both clients are public PKCE clients; the Worker keeps no client secret."
  }
  assert {
    condition     = zitadel_application_oidc.mctl_web.dev_mode == false && alltrue([for u in zitadel_application_oidc.mctl_web.redirect_uris : startswith(u, "https://mctl.ai/")])
    error_message = "The production client redirects to https://mctl.ai only, with dev mode off."
  }
}
