# kubectl sign-in (kubernetes.tf, #1881), run in CI (`tofu test`) against
# mocked providers. Plans are targeted, as in admins.tftest.hcl: the root's
# import blocks crash the mock providers.

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
    acme = jsonencode({
      auser = jsonencode({ email = "a@example.com", first_name = "A", last_name = "U" })
    })
    erpact = jsonencode({
      kuser = jsonencode({ email = "k@example.com", first_name = "K", last_name = "U", kubectl = true })
      vuser = jsonencode({ email = "v@example.com", first_name = "V", last_name = "U", vault = true })
    })
  })
}

run "the_project_refuses_users_without_a_role" {
  command = plan
  plan_options {
    target = [zitadel_project.kubernetes]
  }

  assert {
    condition     = zitadel_project.kubernetes.project_role_check == true && zitadel_project.kubernetes.has_project_check == true
    error_message = "Without project_role_check every member of a granted organization gets an API server token."
  }
  assert {
    condition     = zitadel_project.kubernetes.project_role_assertion == true
    error_message = "Without project_role_assertion the groups action sees no grants and the token carries no groups."
  }
}

run "only_opted_in_users_are_granted" {
  command = plan
  plan_options {
    target = [zitadel_user_grant.kubernetes_tenant]
  }

  assert {
    condition     = toset(keys(zitadel_user_grant.kubernetes_tenant)) == toset(["erpact/kuser"])
    error_message = "Only a user whose entry says \"kubectl\": true may hold a Kubernetes role; Vault's opt-in or tenant membership alone must not grant it."
  }
  assert {
    condition     = zitadel_user_grant.kubernetes_tenant["erpact/kuser"].role_keys == toset(["erpact"])
    error_message = "A user holds their own tenant's role and no other."
  }
}

run "no_admins_role" {
  command = plan
  plan_options {
    target = [zitadel_project_role.kubernetes_tenant]
  }

  assert {
    condition     = toset(keys(zitadel_project_role.kubernetes_tenant)) == toset(["acme", "erpact"])
    error_message = "Roles are the tenants alone: an admins role would open an OIDC path to cluster-wide RBAC."
  }
}

run "the_cli_client_is_public_with_pkce_and_loopback_redirects" {
  command = plan
  plan_options {
    target = [zitadel_application_oidc.kubernetes]
  }

  assert {
    condition     = zitadel_application_oidc.kubernetes.app_type == "OIDC_APP_TYPE_NATIVE" && zitadel_application_oidc.kubernetes.auth_method_type == "OIDC_AUTH_METHOD_TYPE_NONE"
    error_message = "kubelogin cannot keep a secret: the client is native with PKCE and no client secret."
  }
  assert {
    condition     = toset(zitadel_application_oidc.kubernetes.redirect_uris) == toset(["http://localhost:8000", "http://localhost:18000"])
    error_message = "Only kubelogin's loopback redirects; any other URI could receive a code for the API server's audience."
  }
  assert {
    condition     = zitadel_application_oidc.kubernetes.id_token_userinfo_assertion == true
    error_message = "The API server reads groups from the ID token."
  }
}
