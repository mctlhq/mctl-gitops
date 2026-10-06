# Argo CD (ops.mctl.ai) signs in through ZITADEL (#1500).
#
# Who may sign in, and as what, is decided here: Argo CD maps the `groups`
# claim through its RBAC (platform-gitops/argocd), and that claim carries
# exactly the roles a user holds on the project below. A user without a role
# on it gets no Argo CD token at all (project_role_check), so a tenant user
# is never let in by default.
#
# Argo CD's own project, not `zitadel_project.platform`: the role check
# applies to every application of a project, and Forgejo (forgejo.tf) must
# stay open to users who have no Argo CD role.

locals {
  argocd_url = "https://ops.mctl.ai"

  # Argo CD RBAC group for full access (`g, admins, role:admin` in
  # platform-gitops/argocd/values.yaml). Tenants map to their own group,
  # named like the tenant (argocd/rbac/tenants/<tenant>.csv).
  argocd_admin_group = "admins"

  # Every organization whose users can hold an Argo CD role: the MCTL
  # organization and each tenant organization (tenants.tf). The groups claim
  # action runs in the user's own organization, so it is declared in each.
  argocd_claim_orgs = merge(
    { "MCTL" = local.mctl_org_id },
    { for tenant, org in zitadel_org.tenant : tenant => org.id },
  )
}

resource "zitadel_project" "argocd" {
  org_id = local.mctl_org_id
  name   = "Argo CD"

  # Only users with a role on this project may obtain a token for it, and
  # only users of organizations that own it or were granted it.
  project_role_check = true
  has_project_check  = true
  # Load-bearing although Argo CD never reads ZITADEL's own role claim: it is
  # what loads the user's grants into the token flow at all. Without it
  # ctx.v1.user.grants is null in the groups action below (measured on
  # v4.19.2), the claim is never set, and nobody gets an Argo CD group.
  project_role_assertion = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "argocd_admin" {
  org_id       = local.mctl_org_id
  project_id   = zitadel_project.argocd.id
  role_key     = local.argocd_admin_group
  display_name = "Argo CD admin"
}

resource "zitadel_project_role" "argocd_tenant" {
  for_each = local.tenants

  org_id       = local.mctl_org_id
  project_id   = zitadel_project.argocd.id
  role_key     = each.key
  display_name = "Argo CD tenant ${each.key}"

  lifecycle {
    # A tenant named like the admin group would hand role:admin to every
    # opted-in user of that tenant. Admins are MCTL users, listed in
    # platform_admin_user_ids (admins.tf); a tenant can never be one.
    precondition {
      condition     = each.key != local.argocd_admin_group
      error_message = "Tenant \"${each.key}\" collides with the Argo CD admin group; admins are granted through platform_admin_user_ids only."
    }
  }
}

# A tenant organization may hand out its own tenant role, and no other.
resource "zitadel_project_grant" "argocd_tenant" {
  for_each = local.tenants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.argocd.id
  granted_org_id = zitadel_org.tenant[each.key].id
  role_keys      = [zitadel_project_role.argocd_tenant[each.key].role_key]
}

# Opt-in: only a tenant user whose Vault entry carries "argocd": true holds
# their tenant's role (owner decision on #1500). Membership of a tenant
# organization alone grants no Argo CD access; with no flag, ZITADEL refuses
# the sign-in (project_role_check above). Granting is a Vault-only change,
# like adding the user.
resource "zitadel_user_grant" "argocd_tenant" {
  for_each = { for key, user in local.users : key => user if try(user.argocd, false) == true }

  org_id           = zitadel_org.tenant[each.value.tenant].id
  user_id          = zitadel_human_user.tenant[each.key].id
  project_id       = zitadel_project.argocd.id
  project_grant_id = zitadel_project_grant.argocd_tenant[each.value.tenant].id
  role_keys        = [zitadel_project_role.argocd_tenant[each.value.tenant].role_key]
}

# The platform admins (admins.tf).
resource "zitadel_user_grant" "argocd_admin" {
  for_each = local.platform_admin_user_ids

  org_id     = local.mctl_org_id
  user_id    = each.value
  project_id = zitadel_project.argocd.id
  role_keys  = [zitadel_project_role.argocd_admin.role_key]
}

# Argo CD reads groups from a flat list of strings; ZITADEL's own role claim
# is a map, which Argo CD ignores. This action copies the user's roles on the
# Argo CD project, the Vault project (vault.tf), the Argo Workflows project
# (workflows.tf) and the Grafana project (grafana.tf), and only those, into
# `groups`. allowed_to_fail: a failure leaves the claim out, which grants
# nothing, rather than breaking sign-in to every other application of the
# organization.
#
# One action for all, because a trigger holds one list of actions and each
# would set the same claim. They never mix in one token: ctx.v1.user.grants
# is not every grant the user holds. It is built from the same query as the
# token's own role claim (runUserinfoActions passes qu.UserGrants, which
# GetOIDCUserInfo loads for the role audience prepareRoles computes, i.e. the
# requesting client's project; internal/api/oidc/userinfo.go, v4.19.2).
# Measured on a local v4.19.2 with a user holding `t1` on an Argo CD-shaped
# project and `admins` on a Vault-shaped one, both accepted by this filter:
# the Argo CD token carries ["t1"], the Vault token ["admins"], and adding
# the other project's audience scope to the Argo CD request still yields
# ["t1"]. The project filter below stays as defence in depth.
resource "zitadel_action" "argocd_groups" {
  for_each = local.argocd_claim_orgs

  org_id          = each.value
  name            = "argocdGroups"
  timeout         = "5s"
  allowed_to_fail = true
  script          = <<-EOT
    function argocdGroups(ctx, api) {
      var grants = ctx.v1.user.grants;
      if (!grants || !grants.grants) {
        return;
      }
      var projects = [
        '${zitadel_project.argocd.id}',
        '${zitadel_project.vault.id}',
        '${zitadel_project.workflows.id}',
        '${zitadel_project.grafana.id}'
      ];
      var groups = [];
      grants.grants.forEach(function (grant) {
        if (projects.indexOf(grant.projectId) < 0) {
          return;
        }
        (grant.roles || []).forEach(function (role) {
          groups.push(role);
        });
      });
      if (groups.length > 0) {
        api.v1.claims.setClaim('groups', groups);
      }
    }
  EOT
}

# Userinfo, and with id_token_userinfo_assertion the ID token Argo CD reads.
# One trigger per organization and flow holds every action of it, so the
# triggers of the organizations whose users can sign in to the Frappe sites
# (erpact and MCTL, erpact.tf) also run their verified e-mail check; that
# action returns at once for any other client. action_ids is a set, so the
# order is not ours to choose, and need not be: an action that may not fail
# aborts userinfo wherever it runs (runUserinfoActionFlows, v4.19.2). The
# GitHub login claim (github-login.tf) runs in every organization; it returns
# at once for any client not in local.github_login_clients (portal.tf).
resource "zitadel_trigger_actions" "argocd_groups" {
  for_each = local.argocd_claim_orgs

  org_id       = each.value
  flow_type    = "FLOW_TYPE_CUSTOMISE_TOKEN"
  trigger_type = "TRIGGER_TYPE_PRE_USERINFO_CREATION"
  action_ids = concat(
    contains(keys(local.erpact_frappe_user_orgs), each.key) ? [zitadel_action.erpact_verified_email[each.key].id] : [],
    [zitadel_action.argocd_groups[each.key].id],
    [zitadel_action.github_login[each.key].id],
  )
}

resource "zitadel_application_oidc" "argocd" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.argocd.id
  name       = "argocd"

  app_type                  = "OIDC_APP_TYPE_WEB"
  auth_method_type          = "OIDC_AUTH_METHOD_TYPE_BASIC"
  grant_types               = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types            = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris             = ["${local.argocd_url}/auth/callback"]
  post_logout_redirect_uris = ["${local.argocd_url}/"]
  access_token_type         = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                  = false
  # Argo CD reads groups, e-mail and name from the ID token.
  id_token_userinfo_assertion = true
}

# `argocd login --sso`: a public client with PKCE, since a CLI cannot keep a
# secret. Argo CD accepts tokens for both client IDs (cliClientID).
resource "zitadel_application_oidc" "argocd_cli" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.argocd.id
  name       = "argocd-cli"

  app_type                    = "OIDC_APP_TYPE_NATIVE"
  auth_method_type            = "OIDC_AUTH_METHOD_TYPE_NONE"
  grant_types                 = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]
  response_types              = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris               = ["http://localhost:8085/auth/callback"]
  access_token_type           = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode                    = false
  id_token_userinfo_assertion = true
}

resource "kubernetes_secret_v1_data" "argocd_oidc" {
  metadata {
    name      = "argocd-oidc-zitadel"
    namespace = "argocd"
  }

  # Referenced from argocd-cm oidc.config as $argocd-oidc-zitadel:<key>.
  data = {
    clientID     = zitadel_application_oidc.argocd.client_id
    clientSecret = zitadel_application_oidc.argocd.client_secret
    cliClientID  = zitadel_application_oidc.argocd_cli.client_id
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}
