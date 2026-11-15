# The orchestrator DevLoop machine user (orchestrator-devloop.tf,
# mctlhq/mctl-api#963), run in CI (`tofu test`) against mocked providers.
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
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({})
}

run "the_machine_user_has_no_credential_but_our_own_key" {
  command = plan
  plan_options {
    target = [
      zitadel_machine_user.orchestrator_devloop,
      zitadel_machine_key.orchestrator_devloop,
    ]
  }

  assert {
    condition     = zitadel_machine_user.orchestrator_devloop.with_secret == false
    error_message = "The orchestrator machine user must have no client secret: its only credential is the key generated on the Mac mini."
  }
  assert {
    condition     = zitadel_machine_user.orchestrator_devloop.access_token_type == "ACCESS_TOKEN_TYPE_JWT"
    error_message = "mctl-api verifies JWT access tokens only; an opaque token would never authenticate."
  }
  assert {
    condition     = zitadel_machine_user.orchestrator_devloop.org_id == "100000000000000001"
    error_message = "The machine user must belong to MCTL, which owns the MCTL API project (has_project_check)."
  }
  assert {
    condition     = startswith(trimspace(zitadel_machine_key.orchestrator_devloop.public_key), "-----BEGIN PUBLIC KEY-----") && !strcontains(zitadel_machine_key.orchestrator_devloop.public_key, "PRIVATE")
    error_message = "The key must be the mini's own public key, so ZITADEL never generates a private key into the state."
  }
  assert {
    condition     = zitadel_machine_key.orchestrator_devloop.expiration_date != null && zitadel_machine_key.orchestrator_devloop.expiration_date != ""
    error_message = "The key must expire."
  }
}

run "mctl_api_maps_exactly_this_machine_user" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.orchestrator_devloop_env]
  }

  override_resource {
    target = zitadel_machine_user.orchestrator_devloop
    values = { id = "orchestrator-user" }
  }

  assert {
    condition = kubernetes_secret_v1_data.orchestrator_devloop_env.data == tomap({
      MCTL_ORCHESTRATOR_DEVLOOP_PROVIDER = "zitadel"
      MCTL_ORCHESTRATOR_DEVLOOP_SUBJECT  = "orchestrator-user"
    })
    error_message = "mctl-api must map the zitadel provider entry and this machine user's id, and nothing else."
  }
  assert {
    condition     = kubernetes_secret_v1_data.orchestrator_devloop_env.metadata[0].name == "mctl-api-orchestrator-devloop" && kubernetes_secret_v1_data.orchestrator_devloop_env.metadata[0].namespace == "mctl-api"
    error_message = "The env must land in the Secret the mctl-api Deployment reads (envFromOptionalSecrets)."
  }
}

run "the_operator_ids_carry_no_credential" {
  command = plan
  plan_options {
    target = [kubernetes_config_map_v1_data.orchestrator_devloop_ids]
  }

  override_resource {
    target = zitadel_machine_user.orchestrator_devloop
    values = { id = "orchestrator-user" }
  }
  override_resource {
    target = zitadel_machine_key.orchestrator_devloop
    values = { id = "orchestrator-key" }
  }
  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "mctl-api-project" }
  }

  assert {
    condition     = toset(keys(kubernetes_config_map_v1_data.orchestrator_devloop_ids.data)) == toset(["user_id", "key_id", "project_id", "issuer", "key_expires"])
    error_message = "The ConfigMap holds ids only; key_details or any secret must never be written to it."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.orchestrator_devloop_ids.data["user_id"] == "orchestrator-user" && kubernetes_config_map_v1_data.orchestrator_devloop_ids.data["key_id"] == "orchestrator-key"
    error_message = "The ids must be the machine user's and its key's."
  }
}
