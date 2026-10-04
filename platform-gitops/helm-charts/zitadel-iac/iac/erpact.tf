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
# organization (has_project_check), and in Frappe, only users the site
# already has, matched by e-mail; sign-up of unknown users is disabled there.

locals {
  erpact_tenant = "erpact"

  # Frappe's callback for a Social Login Key of provider type Custom named
  # `mctl` (frappe.integrations.oauth2_logins.custom). Must match the key
  # name the restore Jobs create.
  erpact_frappe_callback = "/api/method/frappe.integrations.oauth2_logins.custom/mctl"

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
}

# Owned by the tenant organization. With has_project_check, ZITADEL issues a
# token for it only to users of an organization that owns or was granted the
# project: erpact owns it and nobody is granted it, so MCTL users and every
# other tenant's users are refused by ZITADEL itself.
resource "zitadel_project" "erpact_frappe" {
  org_id            = local.erpact_org_id
  name              = "ERPact"
  has_project_check = true
}

# One client for the five sites: they belong to one tenant, and a code is
# only ever delivered to a registered redirect URI. client_secret_post is
# what Frappe's OAuth client (rauth) sends. Frappe reads e-mail and name
# from the userinfo endpoint with the opaque access token.
resource "zitadel_application_oidc" "erpact_frappe" {
  org_id     = local.erpact_org_id
  project_id = zitadel_project.erpact_frappe.id
  name       = "erpact-frappe"

  app_type                    = "OIDC_APP_TYPE_WEB"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_POST"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = sort([for site in local.erpact_frappe_sites : "https://${site}${local.erpact_frappe_callback}"])
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
#
# UNVERIFIED AGAINST A REAL SIGN-IN: the context fields (v1.getUser().human.
# isEmailVerified, v1.application.getClientId()) are taken from the v4.19.2
# source (internal/api/oidc/userinfo.go, internal/actions/object/user.go).
# The owner's first sign-in checks both ways: a verified user gets in, an
# unverified one is refused (docs/runbooks/zitadel.md, "ERPact copy").
resource "zitadel_action" "erpact_verified_email" {
  org_id          = local.erpact_org_id
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

resource "kubernetes_secret_v1_data" "erpact_oidc" {
  metadata {
    name      = "erpact-oidc-zitadel"
    namespace = "erpact"
  }

  # Read by the restore Jobs of git.mctl.ai/erpact/mctl-apps. org_id goes
  # into the `urn:zitadel:iam:org:id:` scope, which shows the sign-in page
  # of the erpact organization.
  data = {
    client_id     = zitadel_application_oidc.erpact_frappe.client_id
    client_secret = zitadel_application_oidc.erpact_frappe.client_secret
    org_id        = local.erpact_org_id
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
