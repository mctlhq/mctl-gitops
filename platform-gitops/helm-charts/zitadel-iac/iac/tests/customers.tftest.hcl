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

run "the_idp_never_links_and_creates_nothing_by_default" {
  command = plan
  variables {
    identity_hook_token_functions_enabled = false
    identity_hook_create_gate_enabled     = false
    identity_hook_intent_enabled          = false
  }
  plan_options {
    target = [zitadel_org_idp_github.customers]
  }

  assert {
    condition = (
      zitadel_org_idp_github.customers.is_linking_allowed == false &&
      zitadel_org_idp_github.customers.auto_linking == "AUTO_LINKING_OPTION_UNSPECIFIED" &&
      zitadel_org_idp_github.customers.is_creation_allowed == false &&
      zitadel_org_idp_github.customers.is_auto_creation == false
    )
    error_message = "A GitHub identity must never attach to an existing account, and creation stays off until the intent hook is on (phase 3.3)."
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

run "the_hook_secret_carries_the_login_client_caller" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.mctl_api_zitadel_hook]
  }

  assert {
    condition     = kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_HOOK_LOGIN_CLIENT_USER_ID"] == "login-client"
    error_message = "The gate's allowed caller comes from var.identity_hook_login_client_user_id (default login-client)."
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

# ----------------------------------------------- phase 3 toggles (customers_executions.tf)

run "no_execution_exists_with_every_toggle_off" {
  command = plan
  # Explicit: customers_rollout.auto.tfvars.json sets the production values,
  # and tofu test loads it like a run does.
  variables {
    identity_hook_token_functions_enabled = false
    identity_hook_create_gate_enabled     = false
    identity_hook_intent_enabled          = false
  }
  plan_options {
    target = [
      zitadel_action_execution_function.identity_token_claims,
      zitadel_action_execution_request.identity_create_user,
      zitadel_action_execution_response.identity_intent,
    ]
  }

  assert {
    condition = (
      length(zitadel_action_execution_function.identity_token_claims) == 0 &&
      length(zitadel_action_execution_request.identity_create_user) == 0 &&
      length(zitadel_action_execution_response.identity_intent) == 0
    )
    error_message = "Every execution is instance-wide; none may exist until its rollout toggle is turned on."
  }
}

# What production runs: the toggles as customers_rollout.auto.tfvars.json
# sets them. Every phase 3 step is on: the token functions, the creation
# gate, the intent hook and account creation on the customers IdP.
run "production_rollout_is_at_step_3_3" {
  command = plan
  plan_options {
    target = [
      zitadel_action_execution_function.identity_token_claims,
      zitadel_action_execution_request.identity_create_user,
      zitadel_action_execution_response.identity_intent,
      zitadel_org_idp_github.customers,
    ]
  }

  assert {
    condition     = toset(keys(zitadel_action_execution_function.identity_token_claims)) == toset(["preuserinfo", "preaccesstoken"])
    error_message = "Production is at step 3.3: preuserinfo and preaccesstoken route to the token target."
  }
  assert {
    condition     = length(zitadel_action_execution_request.identity_create_user) == 15
    error_message = "Production is at step 3.3: the creation gate covers all 15 methods."
  }
  assert {
    condition     = length(zitadel_action_execution_response.identity_intent) == 1
    error_message = "Production is at step 3.3: the intent response routes to the hook."
  }
  assert {
    condition     = zitadel_org_idp_github.customers.is_creation_allowed && zitadel_org_idp_github.customers.is_auto_creation
    error_message = "Production is at step 3.3: account creation on the customers IdP is on."
  }
}

run "step_3_1_adds_only_the_token_functions" {
  command = plan
  variables {
    identity_hook_token_functions_enabled = true
    identity_hook_create_gate_enabled     = false
    identity_hook_intent_enabled          = false
  }
  plan_options {
    target = [
      zitadel_action_execution_function.identity_token_claims,
      zitadel_action_execution_request.identity_create_user,
      zitadel_action_execution_response.identity_intent,
    ]
  }

  assert {
    condition     = toset(keys(zitadel_action_execution_function.identity_token_claims)) == toset(["preuserinfo", "preaccesstoken"])
    error_message = "Step 3.1 routes preuserinfo and preaccesstoken to the token target."
  }
  assert {
    condition     = length(zitadel_action_execution_request.identity_create_user) == 0 && length(zitadel_action_execution_response.identity_intent) == 0
    error_message = "Step 3.1 must not add the gate or the intent hook."
  }
}

run "step_3_2_gates_every_user_creating_method" {
  command = plan
  variables {
    identity_hook_token_functions_enabled = true
    identity_hook_create_gate_enabled     = true
    identity_hook_intent_enabled          = false
  }
  plan_options {
    target = [
      zitadel_action_execution_request.identity_create_user,
      zitadel_action_execution_response.identity_intent,
      zitadel_org_idp_github.customers,
    ]
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
  assert {
    condition     = length(zitadel_action_execution_response.identity_intent) == 0 && zitadel_org_idp_github.customers.is_creation_allowed == false
    error_message = "Step 3.2 must not open account creation; that is step 3.3."
  }
}

run "step_3_3_opens_creation_with_the_intent_hook" {
  command = plan
  variables {
    identity_hook_token_functions_enabled = true
    identity_hook_create_gate_enabled     = true
    identity_hook_intent_enabled          = true
  }
  plan_options {
    target = [zitadel_action_execution_response.identity_intent, zitadel_org_idp_github.customers]
  }

  assert {
    condition     = length(zitadel_action_execution_response.identity_intent) == 1 && zitadel_action_execution_response.identity_intent[0].method == "/zitadel.user.v2.UserService/RetrieveIdentityProviderIntent"
    error_message = "Step 3.3 routes the intent response to the hook."
  }
  assert {
    condition     = zitadel_org_idp_github.customers.is_creation_allowed && zitadel_org_idp_github.customers.is_auto_creation
    error_message = "Step 3.3 opens account creation in the same change as the intent hook."
  }
}

run "creation_never_opens_without_the_gate" {
  command = plan
  variables {
    identity_hook_token_functions_enabled = false
    identity_hook_create_gate_enabled     = false
    identity_hook_intent_enabled          = true
  }
  plan_options {
    target = [zitadel_org_idp_github.customers]
  }

  expect_failures = [zitadel_org_idp_github.customers]
}

run "customer_copy_is_scoped_to_the_customer_organization" {
  command = plan
  plan_options {
    target = [zitadel_hosted_login_translation.customers_en, zitadel_verify_email_message_text.customers_en]
  }
  override_resource {
    target = zitadel_org.customers
    values = { id = "customers-org" }
  }
  assert {
    condition = (
      zitadel_hosted_login_translation.customers_en.org_id == "customers-org" &&
      zitadel_verify_email_message_text.customers_en.org_id == "customers-org" &&
      strcontains(zitadel_verify_email_message_text.customers_en.text, "Continue with GitHub") &&
      !strcontains(zitadel_verify_email_message_text.customers_en.text, "set up a passkey")
    )
    error_message = "Customer copy must be org-scoped and direct people to GitHub, preserving staff defaults."
  }
}

run "customer_login_ui_directs_every_entry_path_to_github" {
  command = plan
  plan_options {
    target = [zitadel_hosted_login_translation.customers_en]
  }
  assert {
    condition = alltrue([
      for text in [
        jsondecode(zitadel_hosted_login_translation.customers_en.translations).loginname.description,
        jsondecode(zitadel_hosted_login_translation.customers_en.translations).loginname.errors.localAuthenticationNotAllowed,
        jsondecode(zitadel_hosted_login_translation.customers_en.translations).idp.description,
        jsondecode(zitadel_hosted_login_translation.customers_en.translations).idp.signInWithGithub,
        jsondecode(zitadel_hosted_login_translation.customers_en.translations).register.disabled.description,
      ] : strcontains(text, "GitHub") && !strcontains(lower(text), "set up a passkey") && !strcontains(lower(text), "set a password")
    ])
    error_message = "Every customer login entry path must direct to GitHub, never ask for a local password/passkey."
  }
}
