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

# The identity hook's customer-creation refusal ends on Login v2's static
# IdP failure page, which shows only idp.loginError. Its copy must send
# staff and partners to the other button, and must not reveal that a
# creation allowlist exists (mctl-api#653).
run "customer_login_error_points_staff_to_the_mctl_account" {
  command = plan
  plan_options {
    target = [zitadel_hosted_login_translation.customers_en]
  }
  assert {
    condition = (
      strcontains(jsondecode(zitadel_hosted_login_translation.customers_en.translations).idp.loginError.description, "Sign in with MCTL account") &&
      alltrue([
        for word in ["allowlist", "allow list", "not allowed", "invite", "approved"] :
        !strcontains(lower(jsondecode(zitadel_hosted_login_translation.customers_en.translations).idp.loginError.description), word)
      ])
    )
    error_message = "idp.loginError must point staff to Sign in with MCTL account without revealing the customer allowlist."
  }
}

run "customers_get_authentication_without_project_roles" {
  command = plan
  plan_options {
    target = [zitadel_project_grant.customers_portal, zitadel_project_grant.customers_mctl_api]
  }
  override_resource {
    target = zitadel_org.customers
    values = { id = "customers-org" }
  }
  override_resource {
    target = zitadel_project.portal
    values = { id = "portal-project" }
  }
  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "api-project" }
  }
  assert {
    condition = (
      zitadel_project_grant.customers_portal.project_id == "portal-project" &&
      zitadel_project_grant.customers_mctl_api.project_id == "api-project" &&
      alltrue([for g in [zitadel_project_grant.customers_portal, zitadel_project_grant.customers_mctl_api] :
        g.granted_org_id == "customers-org" && g.org_id == "100000000000000001" && g.role_keys == null
      ])
    )
    error_message = "Only customers gain authentication to Portal/API; the grants must carry no authorization roles."
  }
  assert {
    condition     = zitadel_project.portal.has_project_check && zitadel_project.mctl_api.has_project_check
    error_message = "Unlisted organizations must remain unable to authenticate."
  }
}

run "customer_claims_reach_only_the_explicit_clients" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.mctl_api_zitadel_hook]
  }
  override_resource {
    target = zitadel_application_oidc.mctl_web
    values = { client_id = "web" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_web_dev
    values = { client_id = "web-dev" }
  }
  override_resource {
    target = zitadel_application_oidc.portal_ui
    values = { client_id = "portal" }
  }
  override_resource {
    target = zitadel_application_oidc.portal_oidc_provider
    values = { client_id = "portal-provider" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_api_oauth
    values = { client_id = "api-oauth" }
  }
  override_resource {
    target = zitadel_application_oidc.mctl_cli
    values = { client_id = "cli" }
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_PORTAL_CLIENT_ID"]) == "portal"
    error_message = "C0 purpose=signin needs the portal UI client id, or live customer sign-in answers 503."
  }
  assert {
    condition = toset(split(",", nonsensitive(kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_HOOK_CLAIM_CLIENT_IDS"]))) == toset([
      "web", "web-dev", "portal", "api-oauth", "cli"
    ])
    error_message = "Each approved customer sign-in client needs proven GitHub claims; no other client may receive them."
  }
}

run "customer_copy_covers_every_supported_locale" {
  command = plan
  plan_options {
    target = [zitadel_hosted_login_translation.customers_en, zitadel_hosted_login_translation.customers_fallback, zitadel_verify_email_message_text.customers_en, zitadel_verify_email_message_text.customers_fallback]
  }
  override_resource {
    target = zitadel_org.customers
    values = { id = "customers-org" }
  }
  assert {
    condition = (
      setunion(toset(["en"]), toset(keys(zitadel_hosted_login_translation.customers_fallback))) == local.customer_copy_languages &&
      setunion(toset(["en"]), toset(keys(zitadel_verify_email_message_text.customers_fallback))) == local.customer_copy_languages
    )
    error_message = "Every shipped login locale needs customer-specific login and verification copy."
  }
  assert {
    condition = alltrue([
      for lang, value in zitadel_hosted_login_translation.customers_fallback :
      value.language == lang && value.org_id == "customers-org" && value.translations == zitadel_hosted_login_translation.customers_en.translations
    ])
    error_message = "Non-English browsers must not inherit staff password/passkey enrollment instructions."
  }
}

run "customer_lifecycle_is_scoped_to_customer_user_management" {
  command = plan
  plan_options {
    target = [zitadel_org_member.customer_lifecycle, zitadel_project.customer_lifecycle]
  }
  assert {
    condition = (
      zitadel_machine_user.customer_lifecycle.org_id == local.mctl_org_id &&
      zitadel_machine_user.customer_lifecycle.with_secret == true &&
      zitadel_machine_user.customer_lifecycle.access_token_type == "ACCESS_TOKEN_TYPE_JWT" &&
      zitadel_org_member.customer_lifecycle.org_id == zitadel_org.customers.id &&
      toset(zitadel_org_member.customer_lifecycle.roles) == toset(["ORG_USER_MANAGER"]) &&
      zitadel_project.customer_lifecycle.org_id == local.mctl_org_id &&
      zitadel_project.customer_lifecycle.has_project_check == true
    )
    error_message = "Lifecycle credentials must be JWT machine credentials outside customers, with only customer-org user management."
  }
}
