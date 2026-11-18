# The C2 machine users (c2-machine-users.tf), run in CI (`tofu test`) against
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
  smtp_password        = "test"
  customers_github_idp = jsonencode({ client_id = "test-id", client_secret = "test-secret" })
  platform_admins = jsonencode({
    admin = jsonencode({ email = "p@example.com", first_name = "P", last_name = "A" })
  })
  tenant_users = jsonencode({})
}

run "two_machine_users_with_no_credential_but_their_own_key" {
  command = plan
  plan_options {
    target = [
      zitadel_machine_user.c2_consent_reader,
      zitadel_machine_user.c2_control_caller,
      zitadel_machine_key.c2_consent_reader,
      zitadel_machine_key.c2_control_caller,
    ]
  }

  assert {
    condition     = zitadel_machine_user.c2_consent_reader.user_name == "c2-consent-reader" && zitadel_machine_user.c2_control_caller.user_name == "c2-control-caller"
    error_message = "Both machine users must exist, one per direction of trust."
  }
  assert {
    condition     = zitadel_machine_user.c2_consent_reader.with_secret == false && zitadel_machine_user.c2_control_caller.with_secret == false
    error_message = "No client secret: the only credential of each user is its own key."
  }
  assert {
    condition     = zitadel_machine_user.c2_consent_reader.access_token_type == "ACCESS_TOKEN_TYPE_JWT" && zitadel_machine_user.c2_control_caller.access_token_type == "ACCESS_TOKEN_TYPE_JWT"
    error_message = "Both verifiers read JWT access tokens only; an opaque token would never authenticate."
  }
  assert {
    condition     = zitadel_machine_user.c2_consent_reader.org_id == "100000000000000001" && zitadel_machine_user.c2_control_caller.org_id == "100000000000000001"
    error_message = "Both users belong to MCTL, which owns the projects of their audiences (has_project_check)."
  }
  assert {
    condition = alltrue([
      for k in [zitadel_machine_key.c2_consent_reader, zitadel_machine_key.c2_control_caller] :
      startswith(trimspace(k.public_key), "-----BEGIN PUBLIC KEY-----") && !strcontains(k.public_key, "PRIVATE") && k.key_type == "KEY_TYPE_JSON" && k.expiration_date != null && k.expiration_date != ""
    ])
    error_message = "Each key is an operator-held public key that expires, so ZITADEL never generates a private key into the state."
  }
  assert {
    condition     = zitadel_machine_key.c2_consent_reader.public_key != zitadel_machine_key.c2_control_caller.public_key
    error_message = "The two users must not share a key: the private halves live in different pods."
  }
}

run "the_control_audience_is_a_project_of_its_own" {
  command = plan
  plan_options {
    target = [zitadel_project.c2_control]
  }

  assert {
    condition     = zitadel_project.c2_control.has_project_check == true && zitadel_project.c2_control.org_id == "100000000000000001"
    error_message = "The control audience project is owned by MCTL and admits only users of MCTL or an organization it is granted to."
  }
  assert {
    condition     = zitadel_project.c2_control.name == "MCTL C2 control"
    error_message = "The control audience project is named MCTL C2 control."
  }
}

run "mctl_api_accepts_the_consent_reader_audience_for_that_subject_only" {
  command = plan
  plan_options {
    target = [kubernetes_secret_v1_data.mctl_api_oidc]
  }

  override_resource {
    target = zitadel_machine_user.c2_consent_reader
    values = { id = "consent-reader-user" }
  }
  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "mctl-api-project" }
  }

  assert {
    condition     = nonsensitive(jsondecode(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_OIDC_PROVIDERS"]))[0].service_subjects == { "consent-reader-user" = "mctl-api-project" }
    error_message = "The consent reader's subject must be a service subject pinned to the MCTL API project audience, and no other subject listed."
  }
  # mctl-api refuses to boot when a service subject is also a
  # subject_audiences key, so the entry must not carry that key at all.
  assert {
    condition     = !contains(keys(nonsensitive(jsondecode(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_OIDC_PROVIDERS"]))[0]), "subject_audiences")
    error_message = "The entry must not carry subject_audiences alongside service_subjects (mctl-api refuses to boot)."
  }
  # The entry keeps its customers_org_id: the reader is a per-subject
  # exception inside it, not a replacement of the customers enforcement.
  assert {
    condition     = nonsensitive(jsondecode(kubernetes_secret_v1_data.mctl_api_oidc.data["MCTL_OIDC_PROVIDERS"]))[0].customers_org_id != ""
    error_message = "The zitadel entry must keep customers_org_id next to service_subjects."
  }
}

run "consumer_ids_are_published_without_a_credential_and_audiences_differ" {
  command = plan
  plan_options {
    target = [kubernetes_config_map_v1_data.c2_machine_ids]
  }

  override_resource {
    target = zitadel_machine_user.c2_consent_reader
    values = { id = "consent-reader-user" }
  }
  override_resource {
    target = zitadel_machine_user.c2_control_caller
    values = { id = "control-caller-user" }
  }
  override_resource {
    target = zitadel_machine_key.c2_consent_reader
    values = { id = "consent-reader-key" }
  }
  override_resource {
    target = zitadel_machine_key.c2_control_caller
    values = { id = "control-caller-key" }
  }
  override_resource {
    target = zitadel_project.mctl_api
    values = { id = "mctl-api-project" }
  }
  override_resource {
    target = zitadel_project.c2_control
    values = { id = "c2-control-project" }
  }

  assert {
    condition = toset(keys(kubernetes_config_map_v1_data.c2_machine_ids.data)) == toset([
      "issuer", "token_endpoint", "jwks_url",
      "consent_user_id", "consent_key_id", "consent_audience", "consent_scope", "consent_key_expires",
      "control_user_id", "control_key_id", "control_audience", "control_scope", "control_key_expires",
    ])
    error_message = "The ConfigMap holds ids only; key_details or any secret must never be written to it."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.metadata[0].name == "mctl-api-c2-machine-ids" && kubernetes_config_map_v1_data.c2_machine_ids.metadata[0].namespace == "mctl-api"
    error_message = "The ids land in the ConfigMap the Job's Role names."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["consent_user_id"] == "consent-reader-user" && kubernetes_config_map_v1_data.c2_machine_ids.data["control_user_id"] == "control-caller-user"
    error_message = "Each direction publishes its own machine user's id."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["consent_key_id"] == "consent-reader-key" && kubernetes_config_map_v1_data.c2_machine_ids.data["control_key_id"] == "control-caller-key"
    error_message = "Each direction publishes its own key's id."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["consent_audience"] == "mctl-api-project" && kubernetes_config_map_v1_data.c2_machine_ids.data["control_audience"] == "c2-control-project"
    error_message = "The consent token is for the MCTL API project and the control token for the control project."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["consent_audience"] != kubernetes_config_map_v1_data.c2_machine_ids.data["control_audience"]
    error_message = "The two directions must carry different audiences: a token for one must be refused by the other."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["consent_scope"] == "openid urn:zitadel:iam:org:project:id:mctl-api-project:aud" && kubernetes_config_map_v1_data.c2_machine_ids.data["control_scope"] == "openid urn:zitadel:iam:org:project:id:c2-control-project:aud"
    error_message = "Each scope must request exactly its own audience and no other."
  }
  assert {
    condition     = kubernetes_config_map_v1_data.c2_machine_ids.data["issuer"] == "https://auth.mctl.ai" && kubernetes_config_map_v1_data.c2_machine_ids.data["jwks_url"] == "https://auth.mctl.ai/oauth/v2/keys"
    error_message = "The issuer and JWKS URL are the public ZITADEL ones the control verifier is configured with."
  }
}
