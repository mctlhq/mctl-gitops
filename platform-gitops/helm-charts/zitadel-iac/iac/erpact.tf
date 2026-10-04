# The Frappe sites of the ERPact copy (tenant erpact) sign their users in
# through ZITADEL (mctlhq/mctl-gitops#1501). Pilot on the copy only.
#
# These are the tenant's own end users, not MCTL principals: the project
# below has no roles and is granted to nobody, so the path confers no Argo CD,
# mctl-api or tenant-admin rights (those live on other projects).
#
# ZITADEL generates the client secret, so it never exists in git or in
# anyone's hands: it goes from this state straight into the Secret
# erpact/erpact-oidc-zitadel, which the erpact-oidc-zitadel Application
# pre-creates and lets this Job's service account read and patch by name,
# nothing else (infra-components/erpact/oidc-zitadel.yaml). The tenant's
# restore Jobs read it and write each site's Social Login Key `mctl`.
#
# Who may sign in to a site is decided twice: here, only users of the erpact
# organization and the platform admins who opted in (has_project_check, the
# project grant to MCTL and the `frappe` user grants below), and in Frappe,
# only users the site already has, matched by e-mail; sign-up of unknown
# users is disabled there.

locals {
  erpact_tenant = "erpact"

  # Frappe's callback for a Social Login Key of provider type Custom named
  # `mctl` (frappe.integrations.oauth2_logins.custom). Must match the key
  # name the restore Jobs create.
  erpact_frappe_callback = "/api/method/frappe.integrations.oauth2_logins.custom/mctl"

  # The second Social Login Key, `mctl_admin` (provider name "MCTL Admin",
  # which Frappe scrubs to that key name; the restore Jobs check the two
  # match), for platform admins. The `mctl` key's org scope pins sign-in to the
  # erpact organization, and ZITADEL refuses a user of any other
  # organization there even with a grant ("User is no member of the required
  # organization", measured on v4.19.2), so admins, who are MCTL users, need
  # a key scoped to the MCTL organization (admin_org_id below). A second key
  # rather than no scope: without one, every tenant user would sign in in
  # the MCTL organization's context, where a plain tenant user name does not
  # resolve.
  erpact_frappe_admin_callback = "/api/method/frappe.integrations.oauth2_logins.custom/mctl_admin"

  # The copy's restored sites: the shared v14 bench and the v15 control
  # site. A site added here also needs the sso step in its bench's values.
  erpact_frappe_sites = toset([
    "erpact-11112025.mctl.ai",
    "erpact-25092026.mctl.ai",
    "erpact-bar2.mctl.ai",
    "erpact-01102026.mctl.ai",
    "erpact-control.mctl.ai",
  ])

  erpact_org_id = zitadel_org.tenant[local.erpact_tenant].id

  # The organizations whose users can sign in to the sites. Token actions run
  # in the user's own organization (measured on v4.19.2: an erpact action
  # does not run for an MCTL user), so the verified e-mail check below is
  # declared in each.
  erpact_frappe_user_orgs = {
    (local.erpact_tenant) = local.erpact_org_id
    "MCTL"                = local.mctl_org_id
  }

  # Platform admins (admins.tf) listed for the sites by a `frappe` field.
  erpact_frappe_admins = {
    for key, a in local.platform_admins : key => a if try(a.frappe, null) != null
  }
}

# Owned by the tenant organization. With has_project_check, ZITADEL issues a
# token for it only to users of an organization that owns or was granted the
# project: erpact owns it and only the MCTL organization is granted it (for
# its admins, below), so every other tenant's users are refused by ZITADEL
# itself.
resource "zitadel_project" "erpact_frappe" {
  org_id            = local.erpact_org_id
  name              = "ERPact"
  has_project_check = true
}

# Who of those organizations may sign in. Every erpact user holds it (the
# tenant's own people, as before), a platform admin only with a `frappe`
# field. It gates nothing until project_role_check is turned on, which is a
# separate change, so that the grants exist first.
resource "zitadel_project_role" "erpact_frappe" {
  org_id       = local.erpact_org_id
  project_id   = zitadel_project.erpact_frappe.id
  role_key     = "frappe"
  display_name = "Frappe sign-in"
}

# The MCTL organization may hand out the Frappe role, and only to admins.
resource "zitadel_project_grant" "erpact_frappe_mctl" {
  org_id         = local.erpact_org_id
  project_id     = zitadel_project.erpact_frappe.id
  granted_org_id = local.mctl_org_id
  role_keys      = [zitadel_project_role.erpact_frappe.role_key]
}

resource "zitadel_user_grant" "erpact_frappe_tenant" {
  for_each = { for key, u in local.users : key => u if u.tenant == local.erpact_tenant }

  org_id     = local.erpact_org_id
  user_id    = zitadel_human_user.tenant[each.key].id
  project_id = zitadel_project.erpact_frappe.id
  role_keys  = [zitadel_project_role.erpact_frappe.role_key]
}

resource "zitadel_user_grant" "erpact_frappe_admin" {
  for_each = local.erpact_frappe_admins

  org_id           = local.mctl_org_id
  user_id          = zitadel_human_user.platform_admin[each.key].id
  project_id       = zitadel_project.erpact_frappe.id
  project_grant_id = zitadel_project_grant.erpact_frappe_mctl.id
  role_keys        = [zitadel_project_role.erpact_frappe.role_key]
}

# One client for the five sites: they belong to one tenant, and a code is
# only ever delivered to a registered redirect URI. client_secret_post is
# what Frappe's OAuth client (rauth) sends. Frappe reads e-mail and name
# from the userinfo endpoint with the opaque access token.
resource "zitadel_application_oidc" "erpact_frappe" {
  org_id     = local.erpact_org_id
  project_id = zitadel_project.erpact_frappe.id
  name       = "erpact-frappe"

  app_type         = "OIDC_APP_TYPE_WEB"
  auth_method_type = "OIDC_AUTH_METHOD_TYPE_POST"
  grant_types      = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types   = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris = sort(flatten([
    for site in local.erpact_frappe_sites : [
      "https://${site}${local.erpact_frappe_callback}",
      "https://${site}${local.erpact_frappe_admin_callback}",
    ]
  ]))
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = false
}

# Frappe signs a user in by the `email` claim alone: it does not check
# email_verified and does not compare the `sub` it stored at the first
# sign-in. A user who set their own e-mail to a colleague's address (left
# unverified) would otherwise become that colleague in Frappe. So userinfo
# for this client is refused unless the e-mail is verified.
#
# Scoped to this client by client id, so other applications of the
# organization (Argo CD) are unaffected, even if the script itself fails.
# allowed_to_fail = false: a failure refuses the sign-in (fail closed).
# One per organization whose users can sign in (erpact_frappe_user_orgs):
# an action only runs for users of its own organization.
#
# UNVERIFIED AGAINST A REAL SIGN-IN: the context fields (v1.getUser().human.
# isEmailVerified, v1.application.getClientId()) are taken from the v4.19.2
# source (internal/api/oidc/userinfo.go, internal/actions/object/user.go).
# The owner's first sign-in checks both ways: a verified user gets in, an
# unverified one is refused (docs/runbooks/zitadel.md, "ERPact copy").
resource "zitadel_action" "erpact_verified_email" {
  for_each = local.erpact_frappe_user_orgs

  org_id          = each.value
  name            = "erpactVerifiedEmail"
  timeout         = "5s"
  allowed_to_fail = false
  script          = <<-EOT
    function erpactVerifiedEmail(ctx, api) {
      if (ctx.v1.application.getClientId() !== '${zitadel_application_oidc.erpact_frappe.client_id}') {
        return;
      }
      var user = ctx.v1.getUser();
      if (!user || !user.human || user.human.isEmailVerified !== true) {
        throw 'e-mail not verified';
      }
    }
  EOT
}

moved {
  from = zitadel_action.erpact_verified_email
  to   = zitadel_action.erpact_verified_email["erpact"]
}

resource "kubernetes_secret_v1_data" "erpact_oidc" {
  metadata {
    name      = "erpact-oidc-zitadel"
    namespace = "erpact"
  }

  # Read by the restore Jobs of git.mctl.ai/erpact/mctl-apps. org_id goes
  # into the `urn:zitadel:iam:org:id:` scope of the `mctl` key, which shows
  # the sign-in page of the erpact organization; admin_org_id into that of
  # the `mctl_admin` key, the MCTL organization's.
  data = {
    client_id     = zitadel_application_oidc.erpact_frappe.client_id
    client_secret = zitadel_application_oidc.erpact_frappe.client_secret
    org_id        = local.erpact_org_id
    admin_org_id  = local.mctl_org_id
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}

# Which tenant users each Frappe site of the copy must have, for the sign-in
# above to find them: Frappe refuses a ZITADEL user it has no User for
# (sign-up is off), and the copy's database comes from production, which
# does not know MCTL people. A user opts in with a `frappe` field in their
# Vault entry (secret/platform/zitadel/users/erpact, or for a platform admin
# secret/platform/zitadel/admins, who then signs in with the `mctl_admin`
# key under the MCTL account's e-mail):
#
#   "frappe": {"sites": ["erpact-control.mctl.ai"], "roles": ["System Manager"]}
#
# Only those users are written, as {version, users: [{email, first_name,
# last_name, sites, roles}]}: the namespace gets the e-mail of a listed user
# and of nobody else. The restore Jobs and the users CronJob of
# git.mctl.ai/erpact/mctl-apps create or update each listed User; the
# manifest grants roles and never revokes them.
locals {
  erpact_frappe_users = [
    for key, u in local.users : {
      user_name  = u.user_name
      email      = lower(u.email)
      first_name = u.first_name
      last_name  = u.last_name
      sites      = try(u.frappe.sites, null)
      roles      = try(u.frappe.roles, null)
    } if u.tenant == local.erpact_tenant && try(u.frappe, null) != null
  ]

  # Admins are named "admin:<key>" in error messages, so they cannot be
  # mistaken for a tenant user of the same name.
  erpact_frappe_admin_users = [
    for key, a in local.erpact_frappe_admins : {
      user_name  = "admin:${key}"
      email      = lower(a.email)
      first_name = a.first_name
      last_name  = a.last_name
      sites      = try(a.frappe.sites, null)
      roles      = try(a.frappe.roles, null)
    }
  ]

  erpact_frappe_all_users = concat(local.erpact_frappe_users, local.erpact_frappe_admin_users)

  # One person, one Frappe user: an e-mail in both lists would be written
  # twice with possibly different roles. Named by user name only.
  erpact_frappe_duplicate_emails = sort(distinct([
    for u in local.erpact_frappe_all_users : u.user_name
    if length([for v in local.erpact_frappe_all_users : v if v.email == u.email]) > 1
  ]))

  # A `frappe` field anywhere else is a mistake (no other tenant has Frappe
  # sites); refused rather than ignored.
  frappe_outside_erpact = sort([
    for key, u in local.users : key if u.tenant != local.erpact_tenant && try(u.frappe, null) != null
  ])
}

resource "kubernetes_secret_v1_data" "erpact_frappe_users" {
  metadata {
    name      = "erpact-frappe-users"
    namespace = "erpact"
  }

  # sensitive(): the provider does not mark `data` sensitive, and the Job
  # log must not print names or addresses (as for users in tenants.tf).
  data = {
    "users.json" = sensitive(jsonencode({
      version = 1
      users = [
        for u in local.erpact_frappe_all_users : {
          email      = u.email
          first_name = u.first_name
          last_name  = u.last_name
          # try(): a malformed list is reported by the preconditions below,
          # not by sort().
          sites = try(sort(u.sites), [])
          roles = try(sort(u.roles), [])
        }
      ]
    }))
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true

  lifecycle {
    # Error messages name users by user name only, never by e-mail.
    precondition {
      condition     = length(local.frappe_outside_erpact) == 0
      error_message = "A frappe field is only valid for tenant ${local.erpact_tenant}; found on: ${join(", ", local.frappe_outside_erpact)}."
    }
    precondition {
      condition = alltrue([
        for u in local.erpact_frappe_all_users :
        try(length(u.sites) > 0 && alltrue([for s in u.sites : contains(local.erpact_frappe_sites, s)]), false)
      ])
      error_message = "Every frappe.sites must be a non-empty list of the copy's sites (local.erpact_frappe_sites); check users: ${join(", ", [for u in local.erpact_frappe_all_users : u.user_name])}."
    }
    precondition {
      condition = alltrue([
        for u in local.erpact_frappe_all_users :
        try(length(u.roles) > 0 && alltrue([for r in u.roles : can(regex("^[A-Za-z]([A-Za-z0-9 _-]*[A-Za-z0-9_-])?$", r)) && !contains(["administrator", "guest", "all"], lower(r))]), false)
      ])
      error_message = "Every frappe.roles must be a non-empty list of Frappe role names, never Administrator, Guest or All; check users: ${join(", ", [for u in local.erpact_frappe_all_users : u.user_name])}."
    }
    precondition {
      condition     = length(local.erpact_frappe_duplicate_emails) == 0
      error_message = "One e-mail is listed for Frappe more than once (a tenant user and an admin, or two entries); check users: ${join(", ", local.erpact_frappe_duplicate_emails)}."
    }
  }
}
