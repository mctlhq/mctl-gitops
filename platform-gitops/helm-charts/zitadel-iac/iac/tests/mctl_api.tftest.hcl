# Tenant access to the MCTL API project (mctl-api.tf), run in CI
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
  smtp_password   = "test"
  platform_admins = "{}"
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
