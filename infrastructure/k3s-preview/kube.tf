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

# All secrets below migrated to Vault + ExternalSecrets
# See: platform-gitops/apps/templates/

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
      name                 = "worker-cx43-fsn1",
      server_type          = "cx43",
      location             = "fsn1",
      labels               = [],
      taints               = [],
      count                = 3,
      longhorn_volume_size = 20
    },
    {
      name                 = "worker-cx43-fsn1",
      server_type          = "cx43",
      location             = "fsn1",
      labels               = [],
      taints               = [],
      count                = 3,
      longhorn_volume_size = 20
    },
  ]

  # --- Load Balancer ---
  load_balancer_type     = "lb11"
  load_balancer_location = "fsn1"

  # --- Ingress: Traefik (default) ---
  # Matches ingress.className: traefik in helm-charts/base-service

  # --- Storage ---
  enable_longhorn = true
  longhorn_replica_count = 2  # HA: each volume on 2 of 3 nodes

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
  # TODO: enable after first apply (cycle with os_upgrade_toggle on initial change)
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
