# Declarative ZITADEL configuration (mctlhq/mctl-gitops#1520), applied by the
# in-cluster Job in ../templates/job.yaml. Runbook: docs/runbooks/zitadel.md.
terraform {
  required_version = "~> 1.13.0"

  required_providers {
    zitadel = {
      source  = "zitadel/zitadel"
      version = "3.8.7"
    }
  }

  # State lives next to ZITADEL, in the zitadel namespace: a Secret holds it
  # and a Lease locks it. Nothing leaves the cluster, and later outputs (OIDC
  # client secrets) stay in the same trust zone as the masterkey.
  backend "kubernetes" {
    secret_suffix     = "zitadel-iac"
    namespace         = "zitadel"
    in_cluster_config = true
  }
}
