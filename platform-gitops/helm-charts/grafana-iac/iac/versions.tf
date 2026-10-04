# Declarative Grafana configuration (grafana.mctl.ai), applied by the
# in-cluster Job in ../templates/job.yaml. Design: mctlhq/mctl-gitops#1601.
terraform {
  required_version = "~> 1.13.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "4.47.0"
    }
  }

  # State lives in this Job's own namespace: a Secret holds it and a Lease
  # locks it. It holds no credential: the provider's auth is not in state.
  backend "kubernetes" {
    secret_suffix     = "grafana-iac"
    namespace         = "grafana-iac"
    in_cluster_config = true
  }
}
