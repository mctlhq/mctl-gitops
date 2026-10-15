# The `customers` organization: self-service accounts for mctl.ai, created by
# signing in with GitHub (mctl-web onboarding B1, mctlhq/mctl-web
# docs/plans/site-onboarding-review.md, "B1 shape after B0").
#
# Nobody is declared here. An account is created by Login V2 on a person's
# first GitHub sign-in, in the shape the identity hook in mctl-api sets
# (mctlhq/mctl-api docs/zitadel-identity-hook.md): username
# `<login>@mctl.ai`, GitHub's primary verified email, one GitHub IdP link,
# and `github_id` / `github_login` metadata. The hook refuses everything else.
#
# The hook is three Actions v2 targets, each wired to its executions below.
# Executions are instance-wide, not per organization: the hook itself passes
# through whatever is not about `customers`. Consequences, accepted in B0:
#   - with mctl-api unreachable, every v2 CreateUser and the other gated
#     methods fail in EVERY organization, this root's own user resources
#     included (provider 3.8.7 creates users through user v2 CreateUser);
#   - the token functions do not interrupt, so a failing hook issues tokens
#     without `mctl:*` claims rather than blocking admin tokens too; every
#     relying party treats a missing `mctl:github_id` as a refusal.
#
# No project grants to the portal or mctl-api: customer accounts get no
# access there until C0 and C2 are live (stage B1b, a separate change).

locals {
  customers_domain = "mctl.ai"

  # The hook's endpoints. A public hostname, not the in-cluster Service:
  # ZITADEL's default HTTPClient.DenyList refuses private addresses (B0
  # item 6), and production does not override it.
  identity_hook_base = "https://api.mctl.ai/api/v1/webhooks/zitadel"

  # Login V2 authenticates to the API as the System API user `login-client`
  # (infra-components/identity/zitadel/login-service-key.yaml). For a System
  # API user the `userID` ZITADEL puts in an execution payload is the user's
  # name, so the gate's allowed caller is this literal. The hook logs any
  # other caller it refuses, which is how a mismatch shows up.
  login_client_user_id = "login-client"

  # Every user-creating, IdP-linking and metadata-writing method of ZITADEL v4.19.2 that the gate
  # covers. Re-check this list on every ZITADEL upgrade: a method missing here
  # is a way into `customers` that skips the hook (B0 found v1
  # ImportHumanUser bypassing a v2-only gate). The organization-creating
  # methods (AddOrg, SetUpOrg, AddOrganization) are left out on purpose: they
  # create users only in a new organization. SCIM is plain HTTP and no
  # execution covers it.
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

  # The mctl-web Worker's callbacks. The dev client is for `wrangler dev`
  # only; no production allowlist (mctl-api, the portal, the Worker) may
  # accept its client id (acceptance criterion 5).
  mctl_web_callback     = "https://mctl.ai/api/zitadel/callback"
  mctl_web_dev_callback = "http://localhost:8787/api/zitadel/callback"

  customers_github_idp = jsondecode(var.customers_github_idp)
}

resource "zitadel_org" "customers" {
  name = "customers"
}

# Usernames are `<login>@mctl.ai`, and Login V2 finds the organization from
# that suffix (allow_domain_discovery below). The instance domain policy
# leaves validate_org_domains off (ZITADEL's default), so the domain is
# verified on creation and needs no DNS record.
resource "zitadel_organization_domain" "customers" {
  organization_id = zitadel_org.customers.id
  domain          = local.customers_domain
}

# The GitHub OAuth App's credentials come from Vault
# secret/platform/zitadel/github-idp (ExternalSecret zitadel-iac-github-idp).
# The client secret is write-only in the provider: it never enters the state.
#
# Auto-creation and auto-update on, so Login V2 creates the account on the
# first sign-in and refreshes it on each later one; what it creates is
# whatever the identity hook put in the intent response. Linking off: a
# GitHub identity never attaches to an existing account, admin or tenant.
resource "zitadel_org_idp_github" "customers" {
  org_id              = zitadel_org.customers.id
  name                = "GitHub"
  client_id           = local.customers_github_idp.client_id
  client_secret       = local.customers_github_idp.client_secret
  scopes              = ["read:user", "user:email"]
  is_linking_allowed  = false
  is_creation_allowed = true
  is_auto_creation    = true
  is_auto_update      = true
  auto_linking        = "AUTO_LINKING_OPTION_UNSPECIFIED"
}

# An organization login policy replaces the instance policy as a whole, so
# every field is restated here rather than inherited (login_policy.tf):
#   - GitHub is the only way in: user_login = false (no password, no
#     passkey), no second factors, passwordless not allowed;
#   - force_mfa = false with force_mfa_local_only = true: ZITADEL asks no
#     second factor after GitHub (owner decision, stage B: recovery is
#     GitHub's), and would ask one only of a local sign-in, which this policy
#     has none of;
#   - allow_register = false: accounts come from the IdP's creation path,
#     which B0 showed needs no registration form.
resource "zitadel_login_policy" "customers" {
  org_id                        = zitadel_org.customers.id
  user_login                    = false
  allow_register                = false
  allow_external_idp            = true
  allow_domain_discovery        = true
  force_mfa                     = false
  force_mfa_local_only          = true
  passwordless_type             = "PASSWORDLESS_TYPE_NOT_ALLOWED"
  hide_password_reset           = true
  ignore_unknown_usernames      = true
  disable_login_with_email      = true
  disable_login_with_phone      = true
  default_redirect_uri          = "https://mctl.ai"
  password_check_lifetime       = "240h0m0s"
  external_login_check_lifetime = "240h0m0s"
  mfa_init_skip_lifetime        = "0s"
  second_factor_check_lifetime  = "18h0m0s"
  multi_factor_check_lifetime   = "12h0m0s"
  second_factors                = []
  multi_factors                 = []
  idps                          = [zitadel_org_idp_github.customers.id]
}

# mctl-web, in a project of its own: ZITADEL puts the client ids of every
# application of a project into `aud`, so sharing one would let another
# client's tokens carry mctl-web's audience. has_project_check limits tokens
# to users of `customers`, the owning organization; no other organization is
# granted the project.
resource "zitadel_project" "mctl_web" {
  org_id            = zitadel_org.customers.id
  name              = "mctl-web"
  has_project_check = true
}

# A public client with PKCE: the Worker keeps no client secret.
resource "zitadel_application_oidc" "mctl_web" {
  org_id     = zitadel_org.customers.id
  project_id = zitadel_project.mctl_web.id
  name       = "mctl-web"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_NONE"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = [local.mctl_web_callback]
  post_logout_redirect_uris   = ["https://mctl.ai"]
  access_token_type           = "OIDC_TOKEN_TYPE_JWT"
  dev_mode                    = false
  id_token_userinfo_assertion = true
}

# The development client, in a separate project so its tokens never carry
# the production client's audience.
resource "zitadel_project" "mctl_web_dev" {
  org_id            = zitadel_org.customers.id
  name              = "mctl-web-dev"
  has_project_check = true
}

resource "zitadel_application_oidc" "mctl_web_dev" {
  org_id     = zitadel_org.customers.id
  project_id = zitadel_project.mctl_web_dev.id
  name       = "mctl-web-dev"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_NONE"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = [local.mctl_web_dev_callback]
  post_logout_redirect_uris   = ["http://localhost:8787"]
  access_token_type           = "OIDC_TOKEN_TYPE_JWT"
  dev_mode                    = true
  id_token_userinfo_assertion = true
}

# ------------------------------------------------------------ identity hook
#
# One target per role, each with its own signing key. interrupt_on_error is
# in each target's name ON PURPOSE: ZITADEL accepts an UpdateTarget that
# flips restCall.interruptOnError and changes nothing (B0 item 5), so a flip
# must replace the target, and a new name forces that. A replace changes the
# signing key; the hook accepts two keys per target for the switch
# (ZITADEL_HOOK_*_SIGNING_KEYS), and the replace needs its address in
# allowedDeletes like any other.

resource "zitadel_action_target" "identity_intent" {
  name               = "mctl-identity-intent-interrupt"
  endpoint           = "${local.identity_hook_base}/intent"
  target_type        = "REST_CALL"
  timeout            = "10s"
  interrupt_on_error = true
  payload_type       = "PAYLOAD_TYPE_JSON"
}

resource "zitadel_action_target" "identity_create_user" {
  name               = "mctl-identity-create-user-interrupt"
  endpoint           = "${local.identity_hook_base}/create-user"
  target_type        = "REST_CALL"
  timeout            = "10s"
  interrupt_on_error = true
  payload_type       = "PAYLOAD_TYPE_JSON"
}

resource "zitadel_action_target" "identity_token_claims" {
  name               = "mctl-identity-token-claims-nointerrupt"
  endpoint           = "${local.identity_hook_base}/token-claims"
  target_type        = "REST_CALL"
  timeout            = "5s"
  interrupt_on_error = false
  payload_type       = "PAYLOAD_TYPE_JSON"
}

# Login V2 reads this response to decide between creating and updating the
# user; the hook replaces that decision for the customers GitHub IdP.
resource "zitadel_action_execution_response" "identity_intent" {
  method     = "/zitadel.user.v2.UserService/RetrieveIdentityProviderIntent"
  target_ids = [zitadel_action_target.identity_intent.id]
}

resource "zitadel_action_execution_request" "identity_create_user" {
  for_each = local.identity_hook_create_methods

  method     = each.value
  target_ids = [zitadel_action_target.identity_create_user.id]
}

resource "zitadel_action_execution_function" "identity_token_claims" {
  for_each = toset(["preuserinfo", "preaccesstoken"])

  name       = each.value
  target_ids = [zitadel_action_target.identity_token_claims.id]
}

# The hook's configuration, for mctl-api's env (ZITADEL_HOOK_*). Everything in
# it is generated by ZITADEL, so it is not written in git. The Secret is
# pre-created empty by the admins-mctl-api Application, which lets this Job
# read and patch it by name only
# (infra-components/mctl-platform/mctl-api/zitadel-hook.yaml). Nothing reads
# it until the mctl-api Deployment references it, in a separate change;
# until then the hook answers 503 and every gated call fails, so that change
# lands with, not after, the first apply of this file.
resource "kubernetes_secret_v1_data" "mctl_api_zitadel_hook" {
  metadata {
    name      = "mctl-api-zitadel-hook"
    namespace = "mctl-api"
  }

  data = {
    ZITADEL_HOOK_CUSTOMERS_ORG_ID     = zitadel_org.customers.id
    ZITADEL_HOOK_GITHUB_IDP_ID        = zitadel_org_idp_github.customers.id
    ZITADEL_HOOK_LOGIN_CLIENT_USER_ID = local.login_client_user_id
    ZITADEL_HOOK_USERNAME_DOMAIN      = local.customers_domain
    # Both mctl-web clients, so development sees the same claims. A dev token
    # is still refused in production: every production relying party checks
    # `aud` against its own client ids, and the dev client is in a project
    # of its own.
    ZITADEL_HOOK_CLAIM_CLIENT_IDS = join(",", [
      zitadel_application_oidc.mctl_web.client_id,
      zitadel_application_oidc.mctl_web_dev.client_id,
    ])
    ZITADEL_HOOK_INTENT_SIGNING_KEYS = zitadel_action_target.identity_intent.signing_key
    ZITADEL_HOOK_CREATE_SIGNING_KEYS = zitadel_action_target.identity_create_user.signing_key
    ZITADEL_HOOK_TOKEN_SIGNING_KEYS  = zitadel_action_target.identity_token_claims.signing_key
    # Not read by mctl-api: the public client ids the Worker needs.
    MCTL_WEB_CLIENT_ID     = zitadel_application_oidc.mctl_web.client_id
    MCTL_WEB_DEV_CLIENT_ID = zitadel_application_oidc.mctl_web_dev.client_id
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
