# Platform admins on the ERPact copy's Frappe sites (erpact.tf) and the
# instance-wide login name guard (admins.tf), run in CI (`tofu test`) against
# mocked providers. Each refusal is a run that must fail on its
# precondition, so dropping the check fails this file. Plans are targeted,
# as in admins.tftest.hcl: the root's import blocks crash the mock providers.

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
  tenant_users = jsonencode({
    erpact = jsonencode({
      tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
    })
  })
  platform_admins = jsonencode({
    dmitrii = jsonencode({
      email  = "a@example.com", first_name = "A", last_name = "B",
      frappe = { sites = ["erpact-control.mctl.ai"], roles = ["System Manager"] }
    })
    other = jsonencode({ email = "o@example.com", first_name = "O", last_name = "P" })
  })
}

run "only_admins_with_frappe_are_granted" {
  command = plan
  plan_options {
    target = [zitadel_user_grant.erpact_frappe_admin, zitadel_user_grant.erpact_frappe_tenant]
  }
  assert {
    condition     = keys(zitadel_user_grant.erpact_frappe_admin) == ["dmitrii"]
    error_message = "Only an admin with a frappe field may hold the Frappe role."
  }
  assert {
    condition     = keys(zitadel_user_grant.erpact_frappe_tenant) == ["erpact/tuser"]
    error_message = "Every erpact tenant user must keep the Frappe role."
  }
}

run "verified_email_check_runs_in_both_organizations" {
  command = plan
  plan_options {
    target = [zitadel_trigger_actions.argocd_groups]
  }

  # Distinct ids per action, so the triggers' action_ids sets can be read
  # at plan time. Overrides apply to every instance of a resource.
  override_resource {
    target = zitadel_action.erpact_verified_email
    values = { id = "verify" }
  }
  override_resource {
    target = zitadel_action.argocd_groups
    values = { id = "groups" }
  }

  assert {
    condition     = toset(keys(zitadel_action.erpact_verified_email)) == toset(["erpact", "MCTL"])
    error_message = "An MCTL admin's sign-in must run the check too; actions only run in the user's own organization."
  }
  # Declaring the action is not enough: it only runs if its organization's
  # userinfo trigger lists it, next to argocdGroups.
  assert {
    condition     = zitadel_trigger_actions.argocd_groups["MCTL"].action_ids == toset(["verify", "groups"])
    error_message = "The MCTL userinfo trigger must run erpactVerifiedEmail as well as argocdGroups."
  }
  assert {
    condition     = zitadel_trigger_actions.argocd_groups["erpact"].action_ids == toset(["verify", "groups"])
    error_message = "The erpact userinfo trigger must run erpactVerifiedEmail as well as argocdGroups."
  }
}

run "admin_listed_for_frappe_with_its_own_email" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  assert {
    condition     = [for u in local.erpact_frappe_all_users : u.email] == ["a@example.com"]
    error_message = "The admin must be written under the MCTL account's e-mail, and the tenant user without frappe not at all."
  }
}

run "rejects_an_email_listed_twice" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({
          email  = "A@example.com", first_name = "T", last_name = "U",
          frappe = { sites = ["erpact-control.mctl.ai"], roles = ["System Manager"] }
        })
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}

run "rejects_admin_login_name_held_by_a_tenant_user" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = jsonencode({
      dmitrii = jsonencode({ email = "a@example.com", first_name = "A", last_name = "B", username = "tuser" })
    })
  }
  expect_failures = [zitadel_human_user.platform_admin]
}

# The tenant users' Frappe preconditions hold for admins too.
run "rejects_admin_frappe_site_outside_the_copy" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    platform_admins = jsonencode({
      dmitrii = jsonencode({
        email  = "a@example.com", first_name = "A", last_name = "B",
        frappe = { sites = ["erp.example.com"], roles = ["System Manager"] }
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}

run "rejects_admin_frappe_without_sites" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    platform_admins = jsonencode({
      dmitrii = jsonencode({
        email  = "a@example.com", first_name = "A", last_name = "B",
        frappe = { sites = [], roles = ["System Manager"] }
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}

run "rejects_admin_frappe_administrator_role" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    platform_admins = jsonencode({
      dmitrii = jsonencode({
        email  = "a@example.com", first_name = "A", last_name = "B",
        frappe = { sites = ["erpact-control.mctl.ai"], roles = ["Administrator"] }
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}

run "rejects_admin_frappe_without_roles" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    platform_admins = jsonencode({
      dmitrii = jsonencode({
        email  = "a@example.com", first_name = "A", last_name = "B",
        frappe = { sites = ["erpact-control.mctl.ai"], roles = [] }
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}

run "rejects_frappe_on_another_tenant" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.erpact_frappe_users]
  }
  variables {
    tenant_users = jsonencode({
      erpact = jsonencode({
        tuser = jsonencode({ email = "t@example.com", first_name = "T", last_name = "U" })
      })
      other = jsonencode({
        ouser = jsonencode({
          email  = "x@example.com", first_name = "X", last_name = "Y",
          frappe = { sites = ["erpact-control.mctl.ai"], roles = ["System Manager"] }
        })
      })
    })
  }
  expect_failures = [kubernetes_secret_v1_data.erpact_frappe_users]
}
