# The portal's ZITADEL project, its OIDC provider's upstream client and the
# Secret that carries the client's credentials (portal.tf), run in CI
# (`tofu test`) against mocked providers. Plans are targeted, as in
# admins.tftest.hcl: the root's import blocks crash the mock providers.
# That the client receives the mctl:github_login claim is asserted in
# github_login.tftest.hcl.

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

run "every_tenant_organization_is_granted_the_portal" {
  command = plan
  plan_options {
    target = [zitadel_project_grant.portal_tenant]
  }

  # Known ids at plan time, so the grant's references can be compared.
  # Overrides apply to every instance of a resource.
  override_resource {
    target = zitadel_project.portal
    values = { id = "portal-project" }
  }
  override_resource {
    target = zitadel_org.tenant
    values = { id = "tenant-org" }
  }

  assert {
    condition     = toset(keys(zitadel_project_grant.portal_tenant)) == toset(["acme", "erpact"])
    error_message = "Every tenant organization must be granted MCTL Portal, or its users get no token for it (has_project_check)."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.portal_tenant : g.project_id == "portal-project"])
    error_message = "The grant must be of the MCTL Portal project."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.portal_tenant : g.granted_org_id == "tenant-org"])
    error_message = "The grant must go to the tenant organization."
  }
  assert {
    condition     = alltrue([for g in zitadel_project_grant.portal_tenant : g.org_id == "100000000000000001"])
    error_message = "The grant must be made by MCTL, which owns the project."
  }
  # The portal reads no ZITADEL role; a tenant organization must have none
  # to hand out here.
  assert {
    condition     = alltrue([for g in zitadel_project_grant.portal_tenant : g.role_keys == null])
    error_message = "The grant must carry no role keys."
  }
}

run "portal_stays_closed_to_other_organizations" {
  command = plan
  plan_options {
    target = [zitadel_project.portal]
  }
  assert {
    condition     = zitadel_project.portal.name == "MCTL Portal" && zitadel_project.portal.org_id == "100000000000000001"
    error_message = "The project is MCTL Portal, owned by MCTL."
  }
  assert {
    condition     = zitadel_project.portal.has_project_check == true
    error_message = "has_project_check must stay on: off admits every organization of the instance, not only the granted tenants."
  }
}

# Each attribute is one the portal's OIDC provider depends on or one that
# keeps the client closed.
run "oidc_provider_client_is_a_confidential_pkce_web_client" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.portal_oidc_provider]
  }

  override_resource {
    target = zitadel_project.portal
    values = { id = "portal-project" }
  }

  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.name == "portal-oidc-provider"
    error_message = "The client is named portal-oidc-provider."
  }
  # Not the MCTL API project: there the portal's tokens would carry
  # mctl-api's audience.
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.project_id == "portal-project" && zitadel_application_oidc.portal_oidc_provider.org_id == "100000000000000001"
    error_message = "The client must be in the MCTL Portal project of MCTL: has_project_check there is what limits who can sign in."
  }
  # Exactly the provider's callback (issuer + /zitadel/callback): a second
  # entry would be a second place an authorization code can be sent.
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.redirect_uris == tolist(["https://app.mctl.ai/api/oidc-provider/zitadel/callback"])
    error_message = "The only redirect URI must be https://app.mctl.ai/api/oidc-provider/zitadel/callback."
  }
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.app_type == "OIDC_APP_TYPE_WEB" && zitadel_application_oidc.portal_oidc_provider.auth_method_type == "OIDC_AUTH_METHOD_TYPE_BASIC"
    error_message = "The client must be a confidential web client authenticating with client_secret_basic."
  }
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.grant_types == tolist(["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]) && zitadel_application_oidc.portal_oidc_provider.response_types == tolist(["OIDC_RESPONSE_TYPE_CODE"])
    error_message = "Authorization code only: no implicit, refresh token or device grant."
  }
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.access_token_type == "OIDC_TOKEN_TYPE_BEARER"
    error_message = "The access token must stay opaque (BEARER): the provider reads the ID token only."
  }
  # The provider never calls userinfo, so without the assertion the
  # mctl:github_login claim would never reach it and every sign-in would be
  # refused as not mapped.
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.id_token_userinfo_assertion == true
    error_message = "id_token_userinfo_assertion must be on: the provider reads mctl:github_login from the ID token."
  }
  assert {
    condition     = zitadel_application_oidc.portal_oidc_provider.dev_mode == false
    error_message = "dev_mode must stay off: on, ZITADEL accepts http redirects."
  }
}

run "oidc_provider_client_reaches_the_portal_secret" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.portal_oidc]
  }

  override_resource {
    target = zitadel_application_oidc.portal_oidc_provider
    values = { client_id = "portal-client-id", client_secret = "portal-client-secret" }
  }

  assert {
    condition     = kubernetes_secret_v1_data.portal_oidc.metadata[0].name == "backstage-oidc-zitadel" && kubernetes_secret_v1_data.portal_oidc.metadata[0].namespace == "backstage"
    error_message = "The keys go into backstage/backstage-oidc-zitadel, the Secret the mctl-portal-oidc-zitadel Application pre-creates."
  }
  assert {
    condition     = toset(keys(kubernetes_secret_v1_data.portal_oidc.data)) == toset(["OIDC_ZITADEL_CLIENT_ID", "OIDC_ZITADEL_CLIENT_SECRET"])
    error_message = "backstage/backstage-oidc-zitadel must carry exactly the two keys the portal reads."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.portal_oidc.data["OIDC_ZITADEL_CLIENT_ID"]) == "portal-client-id"
    error_message = "OIDC_ZITADEL_CLIENT_ID must be the portal-oidc-provider client id."
  }
  assert {
    condition     = nonsensitive(kubernetes_secret_v1_data.portal_oidc.data["OIDC_ZITADEL_CLIENT_SECRET"]) == "portal-client-secret"
    error_message = "OIDC_ZITADEL_CLIENT_SECRET must be the portal-oidc-provider client secret."
  }
  assert {
    condition     = kubernetes_secret_v1_data.portal_oidc.field_manager == "zitadel-iac" && kubernetes_secret_v1_data.portal_oidc.force == true
    error_message = "The Job patches the Secret Argo CD created, as field manager zitadel-iac."
  }
}
