# Tasks: incident-7dc03565

1. [ ] Locate vmagent scrape_pool in Prometheus scrape_configs or AlertManager rules (likely in platform-gitops/helmfiles/mctl-core/values.yaml or a monitoring stack values file)
2. [ ] Verify the pool has 0 targets by checking Prometheus UI (Status -> Targets, filter by job="vmagent" or similar)
3. [ ] Remove or disable the vmagent scrape_pool definition (delete the job_name block or set enabled: false)
4. [ ] Commit and push the change to mctl-gitops main
5. [ ] Wait for ArgoCD to sync (or manually sync monitoring namespace)
6. [ ] Verify the alert "Vmagent has scrape_pool with 0 configured/discovered targets" stops firing in AlertManager
