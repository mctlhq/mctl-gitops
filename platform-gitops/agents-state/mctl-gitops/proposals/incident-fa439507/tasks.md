# Tasks: incident-fa439507

1. [ ] Edit `platform-gitops/tenants/labs/values.yaml`: change `tenant.quotas.services` from `"20"` to `"26"`, adding a dated comment (see design.md) matching the existing history style in that block.
2. [ ] Verify the edited YAML still parses and the `services` key remains a quoted string, consistent with the other quota fields in the same block.
3. [ ] No dependent changes (image tags, other services) are needed — this is a quota-only change; ArgoCD will reconcile the ResourceQuota object on sync.
