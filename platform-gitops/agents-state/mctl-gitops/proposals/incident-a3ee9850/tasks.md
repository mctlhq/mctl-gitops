# Tasks: incident-a3ee9850

1. [ ] Check current resource quota and usage: kubectl describe resourcequota -n labs-tenant
2. [ ] Check pod events for quota or scheduling errors: kubectl get events -n labs-tenant --sort-by='.lastTimestamp'
3. [ ] Choose fix:
   - [ ] Option A: Increase tenant quota in platform-gitops/tenants/labs/kustomization.yaml
   - [ ] Option B: Reduce service requests in platform-gitops/tenants/labs/agent-worker-preview/values.yaml
4. [ ] Apply change and verify pods become Ready: kubectl get pods -n labs-tenant -l app=agent-worker-preview
5. [ ] Verify ArgoCD app health changes to Healthy within 2 minutes
