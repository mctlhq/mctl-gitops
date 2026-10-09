# The github_login field of tenant users and platform admins
# (github-login.tf), run in CI (`tofu test`) against mocked providers. Each
# rejected case is a run that must fail on its variable or precondition, so
# loosening the validation fails this file. Runs target the resources under
# test only: the root's import blocks crash OpenTofu's mock providers.

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
  tenant_users = jsonencode({
    erpact = jsonencode({
      tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
    })
  })
  platform_admins = jsonencode({
    admin = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B" })
  })
  smtp_password = "test"
}

run "absent_login_writes_no_metadata" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant, zitadel_user_metadata.github_login_admin]
  }
  assert {
    condition     = length(zitadel_user_metadata.github_login_tenant) == 0 && length(zitadel_user_metadata.github_login_admin) == 0
    error_message = "Without github_login no metadata may be written."
  }
}

run "tenant_login_is_written_as_a_json_string" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "Octo-Cat1" })
        other = jsonencode({ email = "o@example.com", first_name = "O", last_name = "T" })
      })
    })
  }
  assert {
    condition     = keys(zitadel_user_metadata.github_login_tenant) == ["erpact/tuser"]
    error_message = "Only the user that declares github_login gets the metadata."
  }
  assert {
    condition     = zitadel_user_metadata.github_login_tenant["erpact/tuser"].key == "github_login"
    error_message = "The metadata key must be github_login."
  }
  assert {
    condition     = nonsensitive(zitadel_user_metadata.github_login_tenant["erpact/tuser"].value) == "\"Octo-Cat1\""
    error_message = "The value must be the login as a JSON string, unchanged."
  }
}

# Actions v1 parse a metadata value that is valid JSON: a bare 1234 would
# reach the script as a number and be refused there.
run "all_digit_login_stays_a_string" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "1234" })
      })
    })
  }
  assert {
    condition     = nonsensitive(zitadel_user_metadata.github_login_tenant["erpact/tuser"].value) == "\"1234\""
    error_message = "An all-digit login must be stored as a JSON string."
  }
}

run "admin_login_is_written_in_the_mctl_organization" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_admin]
  }
  variables {
    platform_admins = jsonencode({
      admin = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B", github_login = "admin-login" })
    })
  }
  assert {
    condition     = zitadel_user_metadata.github_login_admin["admin"].org_id == "100000000000000001"
    error_message = "An admin's login belongs to the MCTL organization."
  }
  assert {
    condition     = nonsensitive(zitadel_user_metadata.github_login_admin["admin"].value) == "\"admin-login\""
    error_message = "The admin's value must be the login as a JSON string."
  }
}

run "longest_login_is_accepted" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "a12345678901234567890123456789012345678" })
      })
    })
  }
}

# The action exists in every organization that runs the token trigger, and
# the trigger lists it next to argocdGroups.
run "action_is_in_every_organization_and_trigger" {
  command = apply
  plan_options {
    target = [zitadel_trigger_actions.argocd_groups]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "octocat" })
      })
      other = jsonencode({
        ouser = jsonencode({ email = "o@example.com", first_name = "O", last_name = "U" })
      })
    })
  }
  assert {
    condition     = toset(keys(zitadel_action.github_login)) == toset(["MCTL", "erpact", "other"])
    error_message = "The action must exist in MCTL and in every tenant organization."
  }
  assert {
    condition = alltrue([
      for org, trigger in zitadel_trigger_actions.argocd_groups :
      contains(trigger.action_ids, zitadel_action.github_login[org].id) && contains(trigger.action_ids, zitadel_action.argocd_groups[org].id)
    ])
    error_message = "Each organization's userinfo trigger must run both argocdGroups and the GitHub login action."
  }
  # By default the portal's client and no other (portal.tf).
  assert {
    condition = alltrue([
      for org in ["MCTL", "erpact", "other"] :
      strcontains(zitadel_action.github_login[org].script, "var clients = [\"${nonsensitive(zitadel_application_oidc.portal_oidc_provider.client_id)}\"];")
    ])
    error_message = "With no extra client IDs the action must allow the portal's OIDC provider client only, in every organization."
  }
  # Only the users whose login this root manages, per organization.
  assert {
    condition     = strcontains(zitadel_action.github_login["erpact"].script, "var users = [\"${zitadel_human_user.tenant["erpact/tuser"].id}\"];")
    error_message = "The erpact action must trust the metadata of erpact/tuser only."
  }
  assert {
    condition     = strcontains(zitadel_action.github_login["other"].script, "var users = [];") && strcontains(zitadel_action.github_login["MCTL"].script, "var users = [];")
    error_message = "Organizations without a managed login must trust no user's metadata."
  }
}

run "client_allowlist_is_rendered_into_the_action" {
  command = apply
  plan_options {
    target = [zitadel_action.github_login]
  }
  variables {
    github_login_client_ids = ["111111111111111111", "222222222222222222"]
  }
  override_resource {
    target = zitadel_application_oidc.portal_oidc_provider
    values = { client_id = "portal-client-id" }
  }
  assert {
    condition     = strcontains(zitadel_action.github_login["MCTL"].script, "var clients = [\"111111111111111111\",\"222222222222222222\",\"portal-client-id\"];")
    error_message = "The action must allow exactly the listed client IDs and the portal's."
  }
  # A client id reaches the script in clear: a sensitive script would be
  # hidden in the Job's plan, and with it every change to the action.
  assert {
    condition     = !issensitive(zitadel_action.github_login["MCTL"].script)
    error_message = "The action script must not be sensitive."
  }
}

run "rejects_duplicate_client_ids" {
  command = plan
  plan_options {
    target = [zitadel_action.github_login]
  }
  variables {
    github_login_client_ids = ["111111111111111111", "111111111111111111"]
  }
  expect_failures = [var.github_login_client_ids]
}

run "rejects_empty_client_id" {
  command = plan
  plan_options {
    target = [zitadel_action.github_login]
  }
  variables {
    github_login_client_ids = [" "]
  }
  expect_failures = [var.github_login_client_ids]
}

run "rejects_the_same_login_twice_ignoring_case" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant, zitadel_user_metadata.github_login_admin]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "OctoCat" })
      })
    })
    platform_admins = jsonencode({
      admin = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B", github_login = "octocat" })
    })
  }
  expect_failures = [zitadel_user_metadata.github_login_tenant, zitadel_user_metadata.github_login_admin]
}

# Malformed values for a tenant user: each must fail the variable.
run "rejects_tenant_login_leading_hyphen" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "-octocat" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_trailing_hyphen" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "octocat-" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_double_hyphen" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "octo--cat" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_too_long" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "a123456789012345678901234567890123456789" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_email" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "t@example.com" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_underscore" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "octo_cat" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_quote" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "octo'cat" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_empty" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = "" }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_null" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = null }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_number" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = 1234 }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_boolean" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = true }) }) })
  }
  expect_failures = [var.tenant_users]
}

run "rejects_tenant_login_list" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_tenant]
  }
  variables {
    tenant_users = jsonencode({ erpact = jsonencode({ tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U", github_login = ["octocat"] }) }) })
  }
  expect_failures = [var.tenant_users]
}

# The same rule on the admins' variable.
run "rejects_admin_login_malformed" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_admin]
  }
  variables {
    platform_admins = jsonencode({ admin = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B", github_login = "octo cat" }) })
  }
  expect_failures = [var.platform_admins]
}

run "rejects_admin_login_number" {
  command = plan
  plan_options {
    target = [zitadel_user_metadata.github_login_admin]
  }
  variables {
    platform_admins = jsonencode({ admin = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B", github_login = 42 }) })
  }
  expect_failures = [var.platform_admins]
}
