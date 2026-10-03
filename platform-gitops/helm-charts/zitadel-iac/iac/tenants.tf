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
  tenants = {
    for tenant, users in jsondecode(var.tenant_users) : tenant => jsondecode(users)
  }

  users = merge([
    for tenant, users in local.tenants : {
      for u in users : "${tenant}/${u.user_name}" => merge(u, { tenant = tenant })
    }
  ]...)
}

resource "zitadel_org" "tenant" {
  for_each = local.tenants

  name = each.key
}

resource "zitadel_human_user" "tenant" {
  for_each = local.users

  org_id            = zitadel_org.tenant[each.value.tenant].id
  user_name         = each.value.user_name
  email             = sensitive(each.value.email)
  first_name        = sensitive(each.value.first_name)
  last_name         = sensitive(each.value.last_name)
  is_email_verified = false

  # The invitation goes out when the user is created, so mail must work by
  # then.
  depends_on = [zitadel_email_provider_smtp.resend]

  lifecycle {
    # Set once at creation; the user verifies it by redeeming the invite,
    # which this resource must not then try to undo.
    ignore_changes = [is_email_verified]
  }
}
