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

variable "github_oauth_client_id" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client ID for ArgoCD Dex"
}

variable "github_oauth_client_secret" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client Secret for ArgoCD Dex"
}

variable "github_repo_pat" {
  type        = string
  sensitive   = true
  description = "GitHub PAT for ArgoCD to access private repos"
}

variable "backstage_github_client_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub OAuth Client ID for Backstage auth"
}

variable "backstage_github_client_secret" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub OAuth Client Secret for Backstage auth"
}

variable "monteexchange_bot_token" {
  type        = string
  sensitive   = true
  description = "Telegram Bot Token for monteexchange"
}

variable "monteexchange_wise_token" {
  type        = string
  sensitive   = true
  description = "Wise API Token for monteexchange"
}

variable "monteexchange_balance_id" {
  type        = string
  description = "Wise Balance ID for monteexchange"
}

variable "monteexchange_profile_id" {
  type        = string
  description = "Wise Profile ID for monteexchange"
}

variable "monteexchange_exchange_fee" {
  type        = string
  default     = "1.75"
  description = "Exchange fee percentage for monteexchange"
}

variable "monteexchange_withdrawal_fee" {
  type        = string
  default     = "0"
  description = "Withdrawal fee for monteexchange"
}

variable "monteexchange_wise_host" {
  type        = string
  default     = "https://api.transferwise.com"
  description = "Wise API host for monteexchange"
}

# --- Kube-Hetzner Module ---

module "kube-hetzner" {
  providers = {
    hcloud = hcloud
  }
  hcloud_token = var.hcloud_token

  source = "kube-hetzner/kube-hetzner/hcloud"
  # Pin to a specific version for reproducibility
  # version = "2.19.1"

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
      name        = "worker-fsn1",
      server_type = "cx33",
      location    = "fsn1",
      labels      = [],
      taints      = [],
      count       = 2
    },
  ]

  # --- Load Balancer ---
  load_balancer_type     = "lb11"
  load_balancer_location = "fsn1"

  # --- Ingress: Traefik (default) ---
  # Matches ingress.className: traefik in helm-charts/base-service

  # --- Storage ---
  enable_longhorn = true
  longhorn_replica_count = 1  # For preprod, 1 replica is sufficient

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
  # Non-HA (1 CP): disable automatic OS upgrades
  automatically_upgrade_os = false
  system_upgrade_use_drain = true

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

  github_oauth_client_id     = var.github_oauth_client_id
  github_oauth_client_secret = var.github_oauth_client_secret
  github_repo_pat            = var.github_repo_pat

  backstage_github_client_id     = var.backstage_github_client_id
  backstage_github_client_secret = var.backstage_github_client_secret

  monteexchange_bot_token      = var.monteexchange_bot_token
  monteexchange_wise_token     = var.monteexchange_wise_token
  monteexchange_balance_id     = var.monteexchange_balance_id
  monteexchange_profile_id     = var.monteexchange_profile_id
  monteexchange_exchange_fee   = var.monteexchange_exchange_fee
  monteexchange_withdrawal_fee = var.monteexchange_withdrawal_fee
  monteexchange_wise_host      = var.monteexchange_wise_host

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
