# =============================================================================
# mctl.me — Preprod k3s Cluster on Hetzner Cloud
# =============================================================================
# Uses kube-hetzner module from Terraform Registry.
# Custom additions: cluster-bootstrap (ArgoCD), extra-manifests (ClusterIssuers).
# =============================================================================

terraform {
  # OpenTofu (#1534); terraform.yml pins the same version.
  required_version = "~> 1.13.0"
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

variable "ssh_public_key" {
  type        = string
  default     = ""
  description = "Public key of hcloud_ssh_key.k3s. Empty reads ~/.ssh/id_ed25519.pub (an operator's laptop); CI passes secrets.K3S_SSH_PUBLIC_KEY so it never replaces the key with its own."
}

variable "etcd_s3_access_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "R2 access key for etcd snapshot uploads (empty disables S3 snapshots, e.g. local plan without creds)"
}

variable "etcd_s3_secret_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "R2 secret key for etcd snapshot uploads"
}

# All secrets below migrated to Vault + ExternalSecrets
# See: platform-gitops/apps/templates/

# --- Kube-Hetzner Module ---

# Inputs of the module's own kustomization (terraform_data.kustomization).
# When any of them changes, the module re-runs `kubectl apply -k` on its
# bundled manifests, and those include a kured DaemonSet and a
# system-upgrade-controller Deployment, both WITHOUT resources.
# extra-manifests/kured.yaml.tpl and system-upgrade-controller.yaml.tpl own
# the real ones, but the module re-applies a user manifest only when that
# file's rendered content changes, so the base copy won the last write: on
# 2026-10-20 the #2035 apply dropped kured's requests and limits. Feeding a
# hash of these inputs into both templates changes their rendered content
# whenever the base layer is replaced, so the user layer re-applies in the
# same run, after the base (it depends_on it).
# Anything added here that feeds the module's kustomization triggers must also
# go into base_kustomization_inputs.
locals {
  install_k3s_version = "v1.33.13+k3s1"
  hetzner_ccm_version = "v1.33.0"
  hetzner_csi_version = "v2.21.2"
  kured_version       = "1.21.0"

  # The module's Traefik and cert-manager HelmCharts default to an unpinned
  # chart ("" and "*"), which resolves to the newest chart whenever
  # helm-controller re-runs the install job. A k3s minor upgrade always re-runs
  # it: the job's config hash covers its pod template, and the bundled
  # klipper-helm image changes (v0.11.1-build20260615 in v1.33.13+k3s1,
  # v0.13.3-build20260727 in v1.34.12+k3s1, the planned upgrade). Pinned to the charts running on
  # 2026-10-22 so the k3s upgrade does not also upgrade ingress and ACME.
  # Bump them here, deliberately, in their own change.
  traefik_version      = "42.0.0"
  cert_manager_version = "v1.20.3"

  # Equal to the module default; pinned here so a module upgrade cannot move
  # it without a matching change to extra-manifests/system-upgrade-controller.yaml.tpl.
  sys_upgrade_controller_version = "v0.18.0"

  hetzner_ccm_merge_values = <<-EOT
    resources:
      requests:
        cpu: 100m
        memory: 96Mi
      limits:
        memory: 192Mi
  EOT

  # Replaces the module's default CSI values wholesale, so the node affinity
  # below is the module default (locals.tf hetzner_csi_values, 2.19.1) copied
  # verbatim: keep the node plugin off the control plane and off Robot servers.
  # Requests are the 7-day peak working set on 2026-10-20 rounded up, limits
  # about twice that. No CPU limits: a throttled attacher or provisioner stalls
  # every volume attach in the cluster.
  hetzner_csi_values = <<-EOT
    controller:
      resources:
        csiAttacher:
          requests:
            cpu: 10m
            memory: 64Mi
          limits:
            memory: 128Mi
        csiResizer:
          requests:
            cpu: 10m
            memory: 96Mi
          limits:
            memory: 192Mi
        csiProvisioner:
          requests:
            cpu: 10m
            memory: 96Mi
          limits:
            memory: 192Mi
        livenessProbe:
          requests:
            cpu: 5m
            memory: 32Mi
          limits:
            memory: 64Mi
        hcloudCSIDriver:
          requests:
            cpu: 10m
            memory: 48Mi
          limits:
            memory: 128Mi
    node:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: "node-role.kubernetes.io/control-plane"
                    operator: DoesNotExist
                  - key: "instance.hetzner.cloud/provided-by"
                    operator: NotIn
                    values:
                      - robot
      resources:
        csiNodeDriverRegistrar:
          requests:
            cpu: 5m
            memory: 24Mi
          limits:
            memory: 48Mi
        livenessProbe:
          requests:
            cpu: 5m
            memory: 48Mi
          limits:
            memory: 96Mi
        hcloudCSIDriver:
          requests:
            cpu: 10m
            memory: 48Mi
          limits:
            memory: 128Mi
  EOT

  base_kustomization_inputs = sha1(jsonencode([
    local.install_k3s_version,
    local.hetzner_ccm_version,
    local.hetzner_csi_version,
    local.kured_version,
    local.sys_upgrade_controller_version,
    local.traefik_version,
    local.cert_manager_version,
    local.hetzner_ccm_merge_values,
    local.hetzner_csi_values,
  ]))
}

module "kube-hetzner" {
  providers = {
    hcloud = hcloud
  }
  hcloud_token = var.hcloud_token

  source  = "kube-hetzner/kube-hetzner/hcloud"
  version = "2.19.1"

  # SSH keys (#1534).
  #
  # ssh_public_key is the key hcloud_ssh_key.k3s was created from. Changing it
  # replaces that resource (public_key forces a new key), so CI must pass the
  # SAME key the operator's laptop does, not its own: the repository secret
  # K3S_SSH_PUBLIC_KEY holds it. The servers themselves ignore ssh_keys and
  # user_data (kube-hetzner 2.19.1 modules/host lifecycle), so no key change
  # here can replace a node -- only the Hetzner key object.
  #
  # ssh_private_key is whatever key the applier holds: the operator's own key
  # locally, the dedicated deploy key in CI (environment k3s-apply). Both are
  # in /root/.ssh/authorized_keys on every node; the deploy key was appended by
  # hand to the nodes that existed on 2026-10-04, and ssh_additional_public_keys
  # puts it into cloud-init for any node created later.
  #
  # The trailing newline is load-bearing: the key was created from file(),
  # which keeps the file's final "\n", and Hetzner stored that exact string.
  # A GitHub variable comes back without it, and the one-byte difference alone
  # plans a replacement of hcloud_ssh_key.k3s (measured 2026-10-04).
  ssh_public_key  = var.ssh_public_key != "" ? format("%s\n", trimspace(var.ssh_public_key)) : file("~/.ssh/id_ed25519.pub")
  ssh_private_key = file("~/.ssh/id_ed25519")
  ssh_additional_public_keys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIP3PUD3Oz7gszB+/jzbPCkjoPOthFavXv1dX3ig0GDsy k3s-preview-ci-deploy",
  ]

  # firewall_ssh_source and firewall_kube_api_source are deliberately left at
  # the module default (0.0.0.0/0, ::/0). Measured from outside the cluster on
  # 2026-08-14: 22 and 6443 answer publicly, 10250 (kubelet) does not — the
  # cloud firewall already refuses it, so there is nothing to close there.
  #
  # 6443 must stay open: it is the only path to the API server from operators'
  # machines and there is no VPN or bastion.
  #
  # 22 is an accepted risk rather than an oversight. Password authentication is
  # off (sshd offers publickey,keyboard-interactive; OpenSSH 10.2), so brute
  # force is not viable and the residual exposure is a future pre-auth OpenSSH
  # vulnerability. Narrowing it was considered and rejected: this module drives
  # node configuration over SSH, so an allowlist pins `terraform apply` to those
  # addresses, and the operator's address is dynamic — a silent lockout later
  # would be recoverable only through the Hetzner console. Revisit if a static
  # address or a bastion appears.
  #
  # 80/443 are absent from this reasoning because they are absent from the
  # nodes. kube-hetzner opens them on servers only when using_klipper_lb is
  # true; it is false here, so the nodes refuse them. Public HTTP arrives at
  # the Hetzner Cloud Load Balancer for svc/traefik instead — a different
  # object, which cloud firewalls cannot be attached to and to which the CCM
  # does not apply loadBalancerSourceRanges. The Cloudflare-only restriction
  # on that path therefore lives in Traefik, not here:
  # extra-manifests/cloudflare-origin-allowlist.yaml.tpl (#1119).
  #
  # Pods reaching a node's public IP bypass this firewall entirely; that path is
  # closed by tenant.networking.nodePublicCIDRs in the tenant chart.

  # Outbound is an allowlist: once a firewall has any outbound rule, Hetzner
  # drops everything else, and the module's own rules cover only DNS, NTP,
  # ICMP, HTTP and HTTPS. Anything else leaving the cluster needs a rule here.
  extra_firewall_rules = [
    {
      # ZITADEL's invitation and verification mail through Resend SMTP with
      # implicit TLS (mctl-gitops#1520 S3). 2465, not 465: Hetzner blocks
      # outgoing 25 and 465 for cloud servers independently of this firewall.
      # In-cluster, the zitadel NetworkPolicy narrows this port to the
      # ZITADEL API pod.
      description     = "Allow Outbound SMTP (Resend, implicit TLS) for ZITADEL"
      direction       = "out"
      protocol        = "tcp"
      port            = "2465"
      source_ips      = []
      destination_ips = ["0.0.0.0/0", "::/0"]
    },
  ]

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

  # --- etcd snapshots to R2 ---
  # With a single control-plane node, S3 snapshots are the only off-node copy
  # of cluster state. Every 12h, 28 kept = 14 days — still matches the CNPG
  # backup window (platform-gitops/infra-components/data/cnpg/shared/cluster.yaml,
  # retentionPolicy: 14d). Bucket must pre-exist in R2 (same account as
  # terraform-state); restore procedure: docs/runbooks/restore.md.
  #
  # Was 6h / 56 kept: the same 14 days at twice the objects. Halving the
  # schedule rather than the retention is what keeps the window at 14 days in
  # the steady state. The account holds ~13.6 GB against a 10 GB free
  # allowance, and this bucket alone was 5.14 GB in 57 objects on 2026-09-10,
  # growing ~0.4 GB a week at a flat object count — the snapshots themselves
  # are getting bigger, the rotation works. Expected reclaim ~2.5 GB.
  #
  # The steady state is not immediate. k3s retention is a count, not an age,
  # so the first snapshot after this applies prunes the bucket to the 28
  # newest — and those are still 6h apart, which is 7 days, not 14. The window
  # then grows back to 14 days over the following two weeks as 12h snapshots
  # replace them. Snapshots from days 8-14 are deleted at that moment and are
  # not recoverable. Accepted rather than staged behind a follow-up PR: an
  # etcd snapshot more than a week old is not something anyone restores — by
  # then the divergence is large enough that replaying GitOps onto a fresh
  # cluster is the better move — and staging it would hold the R2 overage open
  # for another two weeks to protect backups nobody would use.
  #
  # What this does cost is granularity: worst-case loss on an etcd restore
  # goes from 6h to 12h. Acceptable here because most cluster state is
  # reconstructible by replaying GitOps — the snapshot covers what is not,
  # and that changes on the scale of days rather than hours.
  etcd_s3_backup = var.etcd_s3_access_key == "" ? {} : {
    etcd-s3-endpoint            = "6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com"
    etcd-s3-access-key          = var.etcd_s3_access_key
    etcd-s3-secret-key          = var.etcd_s3_secret_key
    etcd-s3-bucket              = "mctl-etcd-snapshots"
    etcd-s3-region              = "auto"
    etcd-s3-folder              = "k3s-preview"
    etcd-snapshot-schedule-cron = "0 */12 * * *"
    etcd-snapshot-retention     = "28"
  }

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

  # Pin the add-ons to the versions running today. Left null, the module
  # resolves each one to the LATEST GitHub release at plan time (data.tf), but
  # only re-applies them when terraform_data.kustomization is replaced. The
  # live cluster therefore sat on the versions from the last replace, while
  # any values change here (CCM or CSI resources, for example) would have
  # silently upgraded all of them in the same apply. On 2026-10-20 that would
  # have been CCM v1.33.0 -> v1.39.0, CSI v2.21.2 -> v2.24.0 and kured
  # 1.21.0 -> 1.23.0. For a deliberate, reviewed upgrade bump the value in the
  # locals block at the top of this file, never the argument line here: the
  # locals feed base_kustomization_inputs, which keeps kured re-applying.
  hetzner_ccm_version            = local.hetzner_ccm_version
  hetzner_csi_version            = local.hetzner_csi_version
  kured_version                  = local.kured_version
  sys_upgrade_controller_version = local.sys_upgrade_controller_version
  traefik_version                = local.traefik_version
  cert_manager_version           = local.cert_manager_version

  # The chart default is requests 100m/50Mi with no limit. The 7-day peak
  # working set was 72Mi on 2026-10-19, above the request, and nothing bounded
  # it. No CPU limit: the CCM reconciles routes and load balancers and should
  # not be throttled.
  hetzner_ccm_merge_values = local.hetzner_ccm_merge_values

  # CSI controller and node plugin resources; see the locals block.
  hetzner_csi_values = local.hetzner_csi_values

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
  # nodes' current version stops the churn; for controlled future upgrades
  # bump local.install_k3s_version at the top of this file, not this line.
  # Matches the live `kubectl patch plan ... spec.version`
  # mitigation applied 2026-06-27.
  install_k3s_version = local.install_k3s_version

  # Re-applies extra-manifests/kured.yaml.tpl and
  # system-upgrade-controller.yaml.tpl whenever the module's own kustomization
  # is replaced (see base_kustomization_inputs above), and renders their image
  # tags from the same versions the module gets.
  # tests/test_k3s_kured_single_owner.py checks this wiring.
  extra_kustomize_parameters = {
    base_kustomization_inputs      = local.base_kustomization_inputs
    kured_version                  = local.kured_version
    sys_upgrade_controller_version = local.sys_upgrade_controller_version
  }

  # SOC F20: Kubernetes API audit. preinstall_exec writes the policy file
  # before k3s starts (from-zero rebuilds). control_planes_custom_config
  # replaces the empty kube-apiserver-arg list (authentication_config is
  # unset, so local.kube_apiserver_arg is []). On the live cluster the file
  # must exist at /var/lib/rancher/k3s/server/audit.yaml BEFORE a terraform
  # apply that ships these args, or the apiserver will refuse to start.
  # Policy: infrastructure/k3s-preview/audit-policy.yaml
  # (Metadata on secrets/tokenreviews; RequestResponse on authz reviews;
  # no secret values). See docs/runbooks/control-plane.md.
  preinstall_exec = [
    join("\n", [
      "install -d -m 0755 /var/lib/rancher/k3s/server/logs",
      "cat >/var/lib/rancher/k3s/server/audit.yaml <<'AUDIT_POLICY'",
      file("${path.module}/audit-policy.yaml"),
      "AUDIT_POLICY",
      "chmod 0600 /var/lib/rancher/k3s/server/audit.yaml",
    ])
  ]

  control_planes_custom_config = {
    kube-apiserver-arg = [
      "audit-policy-file=/var/lib/rancher/k3s/server/audit.yaml",
      "audit-log-path=/var/lib/rancher/k3s/server/logs/audit.log",
      "audit-log-maxage=30",
      "audit-log-maxbackup=10",
      "audit-log-maxsize=100",
      # kubectl sign-in through ZITADEL (#1881). The client is
      # zitadel_application_oidc.kubernetes (zitadel-iac kubernetes.tf); its
      # id is public and printed by
      #   kubectl -n zitadel get secret kubernetes-oidc -o jsonpath='{.data.clientID}' | base64 -d
      # Both prefixes keep OIDC identities apart from service accounts and
      # system:* groups: the tenant chart binds group `oidc:<tenant>`.
      # ZITADEL runs in this cluster, so after a restart the issuer is
      # unreachable for a while; the API server starts anyway and retries
      # discovery every 10s, and only OIDC tokens fail until it succeeds.
      "oidc-issuer-url=https://auth.mctl.ai",
      "oidc-client-id=395107286768486101",
      "oidc-username-claim=preferred_username",
      "oidc-username-prefix=oidc:",
      "oidc-groups-claim=groups",
      "oidc-groups-prefix=oidc:",
    ]
  }

  # --- Kubeconfig ---
  # No local files: the providers below read module.kube-hetzner.kubeconfig,
  # not a file, and a CI runner starts empty, so these two only showed up as
  # creates in every plan. Operators get a kubeconfig with
  # `tofu output --raw kubeconfig`.
  create_kubeconfig    = false
  create_kustomization = false
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
