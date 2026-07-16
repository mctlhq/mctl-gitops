# Tasks: incident-17841555

1. [ ] Locate the `mctl-agents-incidents` CronWorkflow/WorkflowTemplate manifest in this
       repo and inspect its `synchronization` block for a reference to
       `mctl-gitops-main-writes` (or an equivalent shared mutex used for gitops writes).
2. [ ] If the mutex is present, add a `retryStrategy` (retries: 2-3, with backoff) to the
       step/template that acquires it, so transient contention on
       `mctl-gitops-main-writes` retries instead of failing the whole run.
3. [ ] Find the Loki/promtail scrape config (or pod annotations) responsible for shipping
       mctl-agents workflow pod logs, and confirm/fix the `team=admins`,
       `app=mctl-agents` labeling so `mctl_get_service_logs` can retrieve them for any
       future failure of this or sibling mctl-agents workflows.
4. [ ] Check the Argo Workflows archive/audit retention setting and increase it if
       same-day completed/failed workflows are already expiring out of the audit log
       (confirmed unqueryable for a same-day run during this diagnosis).
5. [ ] Verify all changes look correct: manifest/config only, no image tag bump expected.
6. [ ] If, after inspecting the manifest, the incidents workflow does not use the
       `mctl-gitops-main-writes` mutex at all, skip task 2 and apply only tasks 3-4
       (observability). Do not add speculative application-logic changes with no
       supporting log/trace evidence — note that in the merge description instead.
