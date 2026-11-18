# The values mctl-api refuses to boot on, rendered by this root and compared
# with tests/fixtures/mctl-api-config-check.json, which CI then feeds to the
# deployed mctl-api image's own validator (`--check-config`,
# scripts/check-mctl-api-oidc-config.py). gitops#2737 put service_subjects on
# the entry that has customers_org_id; mctl-api refused to boot and the
# 4.166.0 rollout crash-looped (2026-11-17), because nothing ran the rendered
# JSON through that validator.
#
# This file is the link between the two: the rendering and the fixture cannot
# differ, so the validator always sees what this root would write. Change the
# entry or a cross-checked key and the run below fails until the fixture is
# updated, and the validator then judges the new fixture. The ids are mocked
# (numeric, as ZITADEL's are, because mctl-api checks their shape).
#
# Plans are targeted, as in admins.tftest.hcl: the root's import blocks crash
# the mock providers.

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
  # Production turns the Google IdP on (customers_rollout.auto.tfvars.json),
  # which tofu test also loads; the mocked client stands in for Vault.
  customers_google_idp = jsonencode({ client_id = "g-id", client_secret = "g-secret" })
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({})
}

run "rendered_mctl_api_config_equals_the_fixture_the_validator_checks" {
  command = plan
  plan_options {
    target = [
      kubernetes_secret_v1_data.mctl_api_oidc,
      kubernetes_secret_v1_data.mctl_api_zitadel_hook,
    ]
  }

  override_resource {
    target = zitadel_org.customers
    values = { id = "100000000000000001" }
  }
  override_resource {
    target = zitadel_org_idp_github.customers
    values = { id = "100000000000000002" }
  }
  override_resource {
    target = zitadel_application_api.mctl_api
    values = { client_id = "100000000000000003" }
  }
  override_resource {
    target = zitadel_org_idp_google.customers
    values = { id = "100000000000000004" }
  }

  assert {
    condition = (
      jsondecode(nonsensitive(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_OIDC_PROVIDERS"])) ==
      jsondecode(file("tests/fixtures/mctl-api-config-check.json"))["MCTL_OIDC_PROVIDERS"]
    )
    error_message = "MCTL_OIDC_PROVIDERS as rendered differs from tests/fixtures/mctl-api-config-check.json. Update the fixture in the same PR; CI then runs the deployed mctl-api's own validator on it (mctl-api --check-config)."
  }
  assert {
    condition = (
      nonsensitive(kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_HOOK_CUSTOMERS_ORG_ID"]) ==
      jsondecode(file("tests/fixtures/mctl-api-config-check.json"))["ZITADEL_HOOK_CUSTOMERS_ORG_ID"]
    )
    error_message = "ZITADEL_HOOK_CUSTOMERS_ORG_ID as rendered differs from the fixture."
  }
  assert {
    condition = (
      nonsensitive(kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_HOOK_GITHUB_IDP_ID"]) ==
      jsondecode(file("tests/fixtures/mctl-api-config-check.json"))["ZITADEL_HOOK_GITHUB_IDP_ID"]
    )
    error_message = "ZITADEL_HOOK_GITHUB_IDP_ID as rendered differs from the fixture."
  }
  assert {
    condition = (
      nonsensitive(kubernetes_secret_v1_data.mctl_api_zitadel_hook.data["ZITADEL_HOOK_GOOGLE_IDP_ID"]) ==
      jsondecode(file("tests/fixtures/mctl-api-config-check.json"))["ZITADEL_HOOK_GOOGLE_IDP_ID"]
    )
    error_message = "ZITADEL_HOOK_GOOGLE_IDP_ID as rendered differs from the fixture."
  }
}
