# Logs in through auth/kubernetes as role vault-human-auth-iac, with the
# projected token of the Job's own ServiceAccount. The role and its policy
# (cluster-bootstrap/vault-config/vault-policy-vault-human-auth-iac.hcl) are
# applied once by the owner: they allow the auth/mctl mount, identity groups
# and human-tenant-* policies, and no secret data at all.
#
# auth_login_jwt, because the provider has no kubernetes login block, and
# auth/kubernetes/login takes the same {role, jwt} body. The jwt itself comes
# from TERRAFORM_VAULT_AUTH_JWT, which the pod sets from its projected
# ServiceAccount token (../templates/_pod.tpl), so validate needs no file.
# No child token: the login token lives ten minutes and has nothing a child
# token would narrow.
provider "vault" {
  address          = "http://vault.vault.svc.cluster.local:8200"
  skip_child_token = true

  auth_login_jwt {
    mount = "kubernetes"
    role  = "vault-human-auth-iac"
  }
}
