# =============================================================================
# mctl.me — Preprod k3s Cluster on Hetzner Cloud
# =============================================================================
# Uses kube-hetzner module from Terraform Registry.
# Custom additions: cluster-bootstrap (ArgoCD), extra-manifests (ClusterIssuers).
# =============================================================================

terraform {
  required_version = ">= 1.14.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.60"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.1"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.1"
    }
  }
}

# --- Variables ---

variable "hcloud_token" {
  type        = string
  sensitive   = true
  description = "Hetzner Cloud API Token"
}

variable "cf_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Cloudflare API token for DNS-01 ACME challenge"
}

variable "bootstrap_argocd" {
  description = <<-EOT
    Gate for cluster-bootstrap's one-shot helm_release.argocd resource.
    Leave false for routine plan/apply. Only set true for a from-zero cluster
    rebuild — see infrastructure/k3s-preview/README.md "Disaster recovery".
  EOT
  type        = bool
  default     = false
}

# All secrets below migrated to Vault + ExternalSecrets
# See: platform-gitops/apps/templates/

# --- Kube-Hetzner Module ---

module "kube-hetzner" {
  providers = {
    hcloud = hcloud
  }
  hcloud_token = var.hcloud_token

  source  = "kube-hetzner/kube-hetzner/hcloud"
  version = "2.19.1"

  # SSH keys
  ssh_public_key  = file("~/.ssh/id_ed25519.pub")
  ssh_private_key = file("~/.ssh/id_ed25519")

  # Network
  network_region = "eu-central"

  # Cluster name
  cluster_name = "mctl-preprod"

  # --- Control Plane ---
  # Single node for preprod (non-HA). For prod use 3 nodes.
  # With 1 CP node, automatic OS upgrades must be disabled.
  control_plane_nodepools = [
    {
      name        = "control-plane-fsn1",
      server_type = "cx33",
      location    = "fsn1",
      labels      = [],
      taints      = [],
      count       = 1
    },
  ]

  # --- Agent (Worker) Nodes ---
  agent_nodepools = [
    {
      name        = "worker-cx43-fsn1",
      server_type = "cx43",
      location    = "fsn1",
      labels      = [],
      taints      = [],
      count       = 3
    },
  ]

  # --- Load Balancer ---
  load_balancer_type     = "lb11"
  load_balancer_location = "fsn1"

  # --- Ingress: Traefik (default) ---
  # Matches ingress.className: traefik in helm-charts/base-service

  # --- Storage ---
  enable_longhorn = false

  # --- Cert Manager ---
  # Enabled by default (enable_cert_manager = true)
  # ClusterIssuer is deployed via extra-manifests/

  # --- DNS ---
  dns_servers = [
    "1.1.1.1",
    "8.8.8.8",
    "2606:4700:4700::1111",
  ]

  # --- CCM ---
  hetzner_ccm_use_helm = true

  # --- Upgrades ---
  # Disabled: single control-plane node — draining it takes down the API server.
  # Re-enable only after adding a second CP node (or migrating to HA).
  automatically_upgrade_os = false
  system_upgrade_use_drain = true

  # Pin the k3s version instead of channel-tracking. With install_k3s_version
  # set, the module renders the system-upgrade Plans with `version:` instead of
  # `channel:` (templates/plans.yaml.tpl), so they no longer re-resolve against
  # update.k3s.io. That endpoint is intermittently unreachable
  # (ResolveFailed: connection timed out) and was transiently resolving to the
  # OLDER v1.33.12 while all nodes were already on v1.33.13 — the hash mismatch
  # spawned apply jobs that perpetually re-cordoned the un-drainable single
  # control-plane (NodeCordoned alert storm, 2026-06-27). Pinning to the
  # nodes' current version stops the churn; bump this line for controlled
  # future upgrades. Matches the live `kubectl patch plan ... spec.version`
  # mitigation applied 2026-06-27.
  install_k3s_version = "v1.33.13+k3s1"

  # --- Kubeconfig ---
  # Best practice: generate via `terraform output --raw kubeconfig > kubeconfig.yaml`
  # create_kubeconfig = false
}

# --- Cluster Bootstrap Module ---
# Deploys ArgoCD + root-app after cluster is ready
module "cluster-bootstrap" {
  providers = {
    helm       = helm
    kubernetes = kubernetes
  }
  source = "./cluster-bootstrap"

  bootstrap_argocd = var.bootstrap_argocd

  depends_on = [
    module.kube-hetzner
  ]
}

# --- Providers ---

provider "hcloud" {
  token = var.hcloud_token
}

provider "kubernetes" {
  host                   = yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.server
  client_certificate     = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-certificate-data)
  client_key             = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-key-data)
  cluster_ca_certificate = base64decode(yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.certificate-authority-data)
}

provider "helm" {
  kubernetes = {
    host                   = yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.server
    client_certificate     = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-certificate-data)
    client_key             = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-key-data)
    cluster_ca_certificate = base64decode(yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.certificate-authority-data)
  }
}

provider "kubectl" {
  host                   = yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.server
  client_certificate     = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-certificate-data)
  client_key             = base64decode(yamldecode(module.kube-hetzner.kubeconfig).users[0].user.client-key-data)
  cluster_ca_certificate = base64decode(yamldecode(module.kube-hetzner.kubeconfig).clusters[0].cluster.certificate-authority-data)
  load_config_file       = false
}

# --- Outputs ---

output "kubeconfig" {
  value     = module.kube-hetzner.kubeconfig
  sensitive = true
}
