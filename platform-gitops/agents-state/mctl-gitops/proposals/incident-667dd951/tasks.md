# Tasks: incident-667dd951

1. [ ] Re-check current `labs` tenant ResourceQuota usage (e.g. via
       `mctl_get_resource_usage` or `kubectl describe resourcequota -n team-labs`)
       to confirm `limits.cpu` is still near its `12` cap before applying.
2. [ ] Edit `platform-gitops/tenants/labs/values.yaml`: change
       `tenant.quotas.limits.cpu` from `"12"` to `"14"`, adding a dated
       comment line above it documenting the reason (KubeQuotaAlmostFull,
       incident d25dd4fd-1f11-4dbd-8d69-59f8667dd951), matching the existing
       comment style for prior bumps in that file.
3. [ ] Verify the edited YAML is still valid (indentation matches the
       surrounding `quotas:` block) and that no other field was touched.
4. [ ] No image tag bump or dependent service change is needed — this is a
       tenant-level ResourceQuota value only; ArgoCD will reconcile the
       namespace's ResourceQuota object once the GitOps change merges.
