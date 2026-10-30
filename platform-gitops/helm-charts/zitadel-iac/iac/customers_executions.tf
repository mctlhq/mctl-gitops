# Customers rollout PHASE 3: the Actions v2 executions that route ZITADEL to
# the identity hook in mctl-api (customers.tf holds the targets). Each
# group is behind its own toggle so the rollout is one step per change,
# with a smoke test after each (docs/runbooks/zitadel.md, "Customers
# organization and the identity hook"):
#
#   3.1 identity_hook_token_functions_enabled: preuserinfo and
#       preaccesstoken. The target does not interrupt, so a failing hook
#       only leaves `mctl:*` claims out; no organization loses tokens.
#   3.2 identity_hook_create_gate_enabled: the request gate on every
#       user-creating, IdP-linking and user-metadata-writing method. It
#       interrupts and is instance-wide: from here on an mctl-api outage
#       fails those methods in EVERY organization.
#   3.3 identity_hook_intent_enabled: the response hook on
#       RetrieveIdentityProviderIntent, and account creation on the
#       customers GitHub IdP. Customer accounts can be created from here on.
#
# Creation opens last, and only behind the gate: the IdP refuses to plan
# creation on while the gate is off (precondition in customers.tf), so no
# path creates a customers account the gate has not checked (B0 item 3).
#
# Kill switch: an admin deletes the executions in the ZITADEL console
# (Actions > Executions); then revert the toggle in git, or the next hourly
# run recreates them.

locals {
  # Every user-creating, IdP-linking and metadata-writing method of ZITADEL
  # v4.19.2 that the gate covers. Re-check this list on every ZITADEL
  # upgrade: a method missing here is a way into `customers` that skips the
  # hook (B0 found v1 ImportHumanUser bypassing a v2-only gate). The
  # organization-creating methods (AddOrg, SetUpOrg, AddOrganization) are
  # left out on purpose: they create users only in a new organization. SCIM
  # is plain HTTP and no execution covers it.
  identity_hook_create_methods = toset([
    "/zitadel.user.v2.UserService/CreateUser",
    "/zitadel.user.v2.UserService/AddHumanUser",
    "/zitadel.user.v2beta.UserService/AddHumanUser",
    "/zitadel.resources.user.v3alpha.ZITADELUsers/CreateUser",
    "/zitadel.management.v1.ManagementService/AddHumanUser",
    "/zitadel.management.v1.ManagementService/ImportHumanUser",
    "/zitadel.management.v1.ManagementService/AddMachineUser",
    "/zitadel.admin.v1.AdminService/ImportData",
    # IdP-linking methods: a GitHub link added to an existing user would let
    # that GitHub account sign in as the user. Management v1 has no add-link
    # RPC in v4.19.2.
    "/zitadel.user.v2.UserService/AddIDPLink",
    "/zitadel.user.v2beta.UserService/AddIDPLink",
    "/zitadel.resources.user.v3alpha.ZITADELUsers/AddIDPAuthenticator",
    # Metadata writers: github_id/github_login are pinned after creation.
    # This routes zitadel-iac's own github_login writes (github-login.tf)
    # through the hook too; the hook allows them outside customers.
    "/zitadel.management.v1.ManagementService/SetUserMetadata",
    "/zitadel.management.v1.ManagementService/BulkSetUserMetadata",
    "/zitadel.user.v2.UserService/SetUserMetadata",
    "/zitadel.user.v2.UserService/UpdateUser",
  ])
}

# 3.1
resource "zitadel_action_execution_function" "identity_token_claims" {
  for_each = var.identity_hook_token_functions_enabled ? toset(["preuserinfo", "preaccesstoken"]) : toset([])

  name       = each.value
  target_ids = [zitadel_action_target.identity_token_claims.id]
}

# 3.2
resource "zitadel_action_execution_request" "identity_create_user" {
  for_each = var.identity_hook_create_gate_enabled ? local.identity_hook_create_methods : toset([])

  method     = each.value
  target_ids = [zitadel_action_target.identity_create_user.id]
}

# 3.3. Login V2 reads this response to decide between creating and updating
# the user; the hook replaces that decision for the customers GitHub IdP.
resource "zitadel_action_execution_response" "identity_intent" {
  count = var.identity_hook_intent_enabled ? 1 : 0

  method     = "/zitadel.user.v2.UserService/RetrieveIdentityProviderIntent"
  target_ids = [zitadel_action_target.identity_intent.id]
}
