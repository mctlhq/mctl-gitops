# All secrets migrated to Vault + ExternalSecrets
# No variables needed in cluster-bootstrap module

variable "bootstrap_argocd" {
  description = <<-EOT
    Gate for the one-shot helm_release.argocd bootstrap resource (see argocd.tf).
    Leave false for routine plan/apply — ArgoCD self-manages via GitOps after
    initial bootstrap. Only set true for a from-zero cluster rebuild, then run
    `terraform state rm module.cluster-bootstrap.helm_release.argocd[0]` once
    ArgoCD reports Healthy/Synced to detach it again.
  EOT
  type        = bool
  default     = false
}
