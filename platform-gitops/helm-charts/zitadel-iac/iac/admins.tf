# Platform admins: the MCTL users who hold every platform admin grant, i.e.
# Argo CD `admins` (argocd.tf), Vault `admins` (vault.tf), Argo Workflows
# `admins` (workflows.tf) and Cloudflare Access `access`
# (cloudflare-access.tf). One list, so they cannot drift apart. The MCTL API project (mctl-api.tf) has no roles: any MCTL user
# obtains its token, and mctl-api grants nothing from ZITADEL yet.
#
# Two kinds of admin:
#   - mctl-admin, the instance's first user (FirstInstance in
#     bootstrap/templates/core-infra/zitadel.yaml), kept as break-glass. It
#     is not created here, so it is looked up by login name: the stored user
#     name may or may not carry the org domain, depending on the domain
#     policy at setup time. Its login name is in docs/runbooks/zitadel.md.
#   - personal accounts, one per human, created here from Vault
#     secret/platform/zitadel/admins (variable platform_admins). This
#     repository is public, so names and addresses live only there; every
#     personal attribute is marked sensitive, as for tenant users.
#
# Dropping mctl-admin from day-to-day grants, once a personal account has
# been proven, is a reviewed change to break_glass_admins (runbook).

locals {
  break_glass_admins = toset(["mctl-admin@mctl.auth.mctl.ai"])

  # { user_name => { email, first_name, last_name, preferred_language } }
  platform_admins = {
    for user_name, attrs in jsondecode(var.platform_admins) : user_name => jsondecode(attrs)
  }

  # { key => user id } for every platform admin: the login name for a
  # break-glass admin, the user name for a personal one. The keys stay
  # apart, since a user name carries no "@" (variable validation), and they
  # address the grants, so mctl-admin's grants keep their existing keys.
  platform_admin_user_ids = merge(
    { for login in local.break_glass_admins : login => one(data.zitadel_human_users.break_glass_admin[login].user_ids) },
    { for user_name, user in zitadel_human_user.platform_admin : user_name => user.id },
  )
}

data "zitadel_human_users" "break_glass_admin" {
  for_each = local.break_glass_admins

  org_id            = local.mctl_org_id
  login_name        = each.key
  login_name_method = "TEXT_QUERY_METHOD_EQUALS"

  lifecycle {
    postcondition {
      condition     = length(self.user_ids) == 1
      error_message = "Expected exactly one MCTL user with login name ${each.key}."
    }
  }
}

# Created like a tenant user (tenants.tf): no password and an unverified
# e-mail, so ZITADEL mails an invitation code. Redeeming it in Login V2
# enrols a passkey, and the instance login policy (login_policy.tf) makes a
# password alone useless.
resource "zitadel_human_user" "platform_admin" {
  for_each = local.platform_admins

  org_id     = local.mctl_org_id
  user_name  = each.key
  email      = sensitive(each.value.email)
  first_name = sensitive(each.value.first_name)
  last_name  = sensitive(each.value.last_name)
  # Set explicitly: left to the provider, it is computed from the names and
  # printed in clear in the plan.
  display_name       = sensitive("${each.value.first_name} ${each.value.last_name}")
  is_email_verified  = false
  preferred_language = try(each.value.preferred_language, "en")

  depends_on = [
    zitadel_email_provider_smtp.resend_2465,
    zitadel_default_verify_email_message_text.en,
    zitadel_default_verify_email_message_text.ru,
  ]

  lifecycle {
    ignore_changes = [is_email_verified]

    # org_id is optional on this resource: with no MCTL match one() yields
    # null, and the user would land in the instance's default organization.
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}
