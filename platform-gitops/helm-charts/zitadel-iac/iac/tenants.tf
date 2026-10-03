# One organization per platform tenant that has users, and its users
# (#1520 S3). The list lives in Vault (variable tenant_users); for_each keys
# are tenant and user names only, and every personal attribute is marked
# sensitive, so the plan in the Job log shows no names or addresses.
#
# A user is created without a password and with an unverified e-mail, so
# ZITADEL mails them an invitation code. Redeeming it in Login V2 lets them
# enrol a passkey; the login policy (login_policy.tf) makes a password alone
# useless anyway.

locals {
  # { tenant => { user_name => { email, first_name, last_name, ... } } }
  tenants = {
    for tenant, fields in jsondecode(var.tenant_users) : tenant => {
      for user_name, attrs in jsondecode(fields) : user_name => jsondecode(attrs)
    }
  }

  users = merge([
    for tenant, users in local.tenants : {
      for user_name, u in users : "${tenant}/${user_name}" => merge(u, {
        tenant    = tenant
        user_name = user_name
      })
    }
  ]...)
}

resource "zitadel_org" "tenant" {
  for_each = local.tenants

  name = each.key
}

resource "zitadel_human_user" "tenant" {
  for_each = local.users

  org_id     = zitadel_org.tenant[each.value.tenant].id
  user_name  = each.value.user_name
  email      = sensitive(each.value.email)
  first_name = sensitive(each.value.first_name)
  last_name  = sensitive(each.value.last_name)
  # Set explicitly: left to the provider, it is computed from the names and
  # printed in clear in the plan.
  display_name      = sensitive("${each.value.first_name} ${each.value.last_name}")
  is_email_verified = false
  # The language of the invitation mail and of Login V2 for this user.
  preferred_language = try(each.value.preferred_language, "en")

  # The invitation goes out when the user is created, so mail and its text
  # must be in place by then.
  depends_on = [
    zitadel_email_provider_smtp.resend,
    zitadel_default_verify_email_message_text.en,
    zitadel_default_verify_email_message_text.ru,
  ]

  lifecycle {
    # Set once at creation; the user verifies it by redeeming the invite,
    # which this resource must not then try to undo.
    ignore_changes = [is_email_verified]
  }
}
