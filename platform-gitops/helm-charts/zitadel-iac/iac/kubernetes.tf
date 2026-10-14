# kubectl signs in humans through ZITADEL (mctlhq/mctl-gitops#1881): the
# API server of k3s-preview trusts this project's client as an OIDC issuer
# audience (infrastructure/k3s-preview/kube.tf), and the tenant chart binds
# group `oidc:<tenant>` to a namespaced read + pod-delete Role.
#
# Like Vault (vault.tf): a project of its own, one role per tenant, and
# project_role_check, so a tenant user without the opt-in gets no token at
# all. The shared groups action (argocd.tf) puts the user's roles on all of
# its projects into `groups`, not this project's alone, so the token also
# carries the user's Argo CD tenant role. That names the same tenant: a
# tenant user lives in the tenant's organization, whose project grants hand
# out that tenant's role and no other. No `admins` role, and no MCTL user is
# granted one here, so a platform admin's `admins` from Argo CD never reaches
# the API server: they keep the cluster's certificate kubeconfig, and an
# OIDC path to cluster-admin would be a second, weaker door to the same room.
#
# Its own project because ZITADEL puts the client ids of every application
# of a project into `aud`: sharing one would let another application's
# tokens carry the API server's audience.

resource "zitadel_project" "kubernetes" {
  org_id = local.mctl_org_id
  name   = "Kubernetes"

  project_role_check = true
  has_project_check  = true
  # Loads the user's grants into the token flow; without it the groups action
  # sees no grants (see zitadel_project.argocd).
  project_role_assertion = true

  lifecycle {
    precondition {
      condition     = length(data.zitadel_orgs.mctl.ids) == 1
      error_message = "Expected exactly one ZITADEL organization named \"MCTL\"."
    }
  }
}

resource "zitadel_project_role" "kubernetes_tenant" {
  for_each = local.tenants

  org_id       = local.mctl_org_id
  project_id   = zitadel_project.kubernetes.id
  role_key     = each.key
  display_name = "kubectl tenant ${each.key}"
}

# A tenant organization may hand out its own tenant role, and no other.
resource "zitadel_project_grant" "kubernetes_tenant" {
  for_each = local.tenants

  org_id         = local.mctl_org_id
  project_id     = zitadel_project.kubernetes.id
  granted_org_id = zitadel_org.tenant[each.key].id
  role_keys      = [zitadel_project_role.kubernetes_tenant[each.key].role_key]
}

# Opt-in: only a tenant user whose entry carries "kubectl": true holds their
# tenant's role. Membership of a tenant organization alone grants nothing.
resource "zitadel_user_grant" "kubernetes_tenant" {
  for_each = { for key, user in local.users : key => user if try(user.kubectl, false) == true }

  org_id           = zitadel_org.tenant[each.value.tenant].id
  user_id          = zitadel_human_user.tenant[each.key].id
  project_id       = zitadel_project.kubernetes.id
  project_grant_id = zitadel_project_grant.kubernetes_tenant[each.value.tenant].id
  role_keys        = [zitadel_project_role.kubernetes_tenant[each.value.tenant].role_key]
}

# kubelogin (`kubectl oidc-login`): a public client with PKCE, since a CLI
# cannot keep a secret. Its loopback redirects are kubelogin's defaults
# (8000, then 18000 when 8000 is taken). The refresh token lets kubelogin
# renew the ID token without a browser round trip until the session ends.
resource "zitadel_application_oidc" "kubernetes" {
  org_id     = local.mctl_org_id
  project_id = zitadel_project.kubernetes.id
  name       = "kubectl"

  app_type         = "OIDC_APP_TYPE_NATIVE"
  auth_method_type = "OIDC_AUTH_METHOD_TYPE_NONE"
  grant_types      = ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"]
  response_types   = ["OIDC_RESPONSE_TYPE_CODE"]
  redirect_uris = [
    "http://localhost:8000",
    "http://localhost:18000",
  ]
  access_token_type = "OIDC_TOKEN_TYPE_BEARER"
  dev_mode          = false
  # The API server reads `groups` and `preferred_username` from the ID token.
  id_token_userinfo_assertion = true
}

# The client id is public (kube.tf's --oidc-client-id and every user's
# kubeconfig carry it), but the provider marks it sensitive, so like
# cloudflare-access.tf it is published where an operator reads it:
#   kubectl -n zitadel get secret kubernetes-oidc \
#     -o jsonpath='{.data.clientID}' | base64 -d
resource "kubernetes_secret_v1" "kubernetes_oidc" {
  metadata {
    name      = "kubernetes-oidc"
    namespace = "zitadel"
    labels = {
      "app.kubernetes.io/name"       = "zitadel-iac"
      "app.kubernetes.io/managed-by" = "zitadel-iac"
    }
  }

  data = {
    clientID = zitadel_application_oidc.kubernetes.client_id
  }
}
