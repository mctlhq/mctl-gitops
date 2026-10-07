# The GitHub login of a ZITADEL user, for the applications that still know
# people by it (#1500 phase 1): the portal and its OIDC provider resolve a
# catalog User and tenant membership from `github_login`. The admin declares
# it in Vault, next to the user's other attributes:
#
#   secret/platform/zitadel/users/<tenant>   {..., "github_login": "<login>"}
#   secret/platform/zitadel/admins           {..., "github_login": "<login>"}
#
# It is never derived from the user's e-mail, and never taken from anything
# the user can write. This Job stores it as user metadata, and the action
# below copies it into the claim `mctl:github_login`, for the clients in
# local.github_login_clients only (portal.tf).
#
# Who can write user metadata (ZITADEL v4.19.2):
#   - not the user: the auth API has only ListMyMetadata and GetMyMetadata,
#     and user v2 SetUserMetadata checks user.write with self-management off
#     (internal/api/grpc/user/v2/metadata.go, NewPermissionCheckUserWrite(ctx,
#     false)); management v1 SetUserMetadata requires user.write;
#   - holders of user.write on the user's organization (IAM_OWNER, and
#     ORG_OWNER / ORG_USER_MANAGER members, of which this root declares none);
#   - Actions v1 of the user's organization (api.v1.user.setMetadata, and the
#     login flows' appendMetadata), all of which this root declares.
# The action still trusts the metadata only for the users this root manages
# it for: their IDs are in the script, so a key someone else sets on any
# other user is ignored, and a value changed out of band on a managed user is
# put back by the next run (the hourly CronJob).

locals {
  github_login_metadata_key = "github_login"
  github_login_claim        = "mctl:github_login"

  # { "<tenant>/<user_name>" => login } and { admin key => login }. Absent
  # means no claim; a present value is validated on the variables.
  tenant_github_logins = {
    for key, user in local.users : key => user.github_login if try(user.github_login, null) != null
  }
  admin_github_logins = {
    for key, admin in local.platform_admins : key => admin.github_login if try(admin.github_login, null) != null
  }

  # GitHub logins are case-insensitive: one login, one ZITADEL user, or the
  # portal could not tell two people apart.
  github_logins_unique = length(distinct([
    for login in concat(values(local.tenant_github_logins), values(local.admin_github_logins)) : lower(login)
  ])) == length(local.tenant_github_logins) + length(local.admin_github_logins)

  # { organization (as in argocd_claim_orgs) => [user id] }: the users of
  # each organization whose login this root manages.
  github_login_user_ids = merge(
    { "MCTL" = [for key in keys(local.admin_github_logins) : zitadel_human_user.platform_admin[key].id] },
    {
      for tenant in keys(local.tenants) : tenant => [
        for key in keys(local.tenant_github_logins) : zitadel_human_user.tenant[key].id if local.users[key].tenant == tenant
      ]
    },
  )
}

# The value is the login as a JSON string: Actions v1 parse a metadata value
# that is valid JSON, so a bare all-digit login would reach the script as a
# number.
resource "zitadel_user_metadata" "github_login_tenant" {
  for_each = local.tenant_github_logins

  org_id  = zitadel_org.tenant[local.users[each.key].tenant].id
  user_id = zitadel_human_user.tenant[each.key].id
  key     = local.github_login_metadata_key
  value   = sensitive(jsonencode(each.value))

  lifecycle {
    precondition {
      condition     = local.github_logins_unique
      error_message = "Two users in secret/platform/zitadel/users/* or secret/platform/zitadel/admins declare the same github_login (case-insensitive)."
    }
  }
}

resource "zitadel_user_metadata" "github_login_admin" {
  for_each = local.admin_github_logins

  org_id  = local.mctl_org_id
  user_id = zitadel_human_user.platform_admin[each.key].id
  key     = local.github_login_metadata_key
  value   = sensitive(jsonencode(each.value))

  lifecycle {
    precondition {
      condition     = local.github_logins_unique
      error_message = "Two users in secret/platform/zitadel/users/* or secret/platform/zitadel/admins declare the same github_login (case-insensitive)."
    }
  }
}

# Runs in the user's organization, like argocdGroups (argocd.tf), and is
# listed in the same trigger: one trigger per organization and flow holds
# every action of it. For a client that is not in
# local.github_login_clients it returns at once. allowed_to_fail: a failure
# leaves the claim out, which the portal must treat as "not mapped", rather
# than breaking sign-in to every other application of the organization. The
# login is checked again here, so a malformed value never becomes a claim.
resource "zitadel_action" "github_login" {
  for_each = local.argocd_claim_orgs

  org_id          = each.value
  name            = "mctlGithubLogin"
  timeout         = "5s"
  allowed_to_fail = true
  script          = <<-EOT
    function mctlGithubLogin(ctx, api) {
      var clients = ${jsonencode(local.github_login_clients)};
      if (clients.indexOf(ctx.v1.application.getClientId()) < 0) {
        return;
      }
      var users = ${jsonencode(local.github_login_user_ids[each.key])};
      var user = ctx.v1.getUser();
      if (!user || users.indexOf(user.id) < 0) {
        return;
      }
      var metadata = ctx.v1.user.getMetadata();
      var login = null;
      ((metadata && metadata.metadata) || []).forEach(function (entry) {
        if (entry.key === '${local.github_login_metadata_key}') {
          login = entry.value;
        }
      });
      if (typeof login !== 'string' || login.length > 39 || !/^[A-Za-z0-9]+(-[A-Za-z0-9]+)*$/.test(login)) {
        return;
      }
      api.v1.claims.setClaim('${local.github_login_claim}', login);
    }
  EOT
}
