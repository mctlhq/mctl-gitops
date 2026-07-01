# One-shot bootstrap only — NOT part of routine plan/apply.
#
# This resource installs ArgoCD and (via extraObjects in helm-values/argocd.yaml)
# seeds the argocd-self-managed and root-app Applications. Once those exist and
# ArgoCD's own reconciler takes over (source: platform-gitops/argocd, a separate
# local chart with its own, actively-maintained values.yaml), THIS resource
# becomes redundant: it is intentionally removed from Terraform state after
# every bootstrap (see infrastructure/k3s-preview/README.md "Disaster recovery"),
# so it never shows up in routine `terraform plan` and never fights ArgoCD's own
# sync loop for ownership of the same release.
#
# 2026-07-01: had gone untracked/unapplied for ~85 days (Terraform's state
# was frozen at revision 28 from 2026-04-06 while ArgoCD's self-managed loop
# kept the live cluster current); re-running `terraform apply` against it
# required manually re-labelling argocd-self-managed/root-app with Helm
# ownership metadata (ArgoCD's own reconciliation had stripped it). Removing
# this from state going forward avoids that recurring conflict entirely.
#
# To use for a real from-zero rebuild: set bootstrap_argocd = true, apply,
# wait for ArgoCD to report both Applications Healthy/Synced, then run
# `terraform state rm module.cluster-bootstrap.helm_release.argocd[0]`
# to detach it again.
resource "helm_release" "argocd" {
  count = var.bootstrap_argocd ? 1 : 0

  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "9.4.1"
  namespace        = "argocd"
  create_namespace = true
  wait             = true
  wait_for_jobs    = true
  values = [
    file("${path.module}/helm-values/argocd.yaml"),
  ]

  # All secrets now managed by ExternalSecrets:
  # - argocd-github-oauth: OAuth credentials
  # - argocd-repo-credentials: GitHub PAT for repo access
  # No set_sensitive needed!
}
