# Declarative human sign-in to Vault through ZITADEL, applied by the
# in-cluster Job in ../templates/job.yaml. Runbook:
# docs/runbooks/vault-human-auth.md.
terraform {
  required_version = "~> 1.13.0"

  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "5.12.0"
    }
  }

  # State lives in this Job's own namespace: a Secret holds it and a Lease
  # locks it. It carries the OIDC client secret, which is already a Secret in
  # the same namespace (vault-oidc-zitadel), so nothing new is exposed.
  backend "kubernetes" {
    secret_suffix     = "vault-human-auth-iac"
    namespace         = "vault-human-auth-iac"
    in_cluster_config = true
  }
}
