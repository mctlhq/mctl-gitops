# Tasks: incident-1784173500

1. [ ] Confirm the live symptom still reproduces before changing anything:
       `GET https://workflows.mctl.ai/api/v1/workflows/argo-workflows?listOptions.limit=3`
       (or via `argo list -n argo-workflows` if using the CLI with cluster
       access). Expect HTTP 500 / `relation "argo_workflows" does not exist`.

2. [ ] (Requires a human operator with `shared-pg` Postgres credentials —
       this agent could not do this step, it only has a read-only
       `argo-workflow-sa` Kubernetes token.) Connect to the `argo-workflows`
       database on `shared-pg-rw.platform-db.svc` and locate the migration
       schema-version tracking table used by the Argo Workflows controller.
       Identify the row for the migration step that creates the
       `argo_workflows` offload table, and rewind/delete it so the
       controller's built-in migrate runner will recreate the table.

3. [ ] Restart the `argo-workflows-workflow-controller` deployment
       (`kubectl rollout restart deployment/argo-workflows-workflow-controller
       -n argo-workflows`) so it re-runs its migration check on startup, and
       confirm in the controller logs that the migration ran (no more
       `relation "argo_workflows" does not exist` on startup).

4. [ ] Re-run step 1's `GET .../api/v1/workflows/argo-workflows` and confirm
       it now returns HTTP 200 instead of HTTP 500.

5. [ ] Edit `platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml`
       to replace the misleading "the error path is gone" comment with the
       corrected text in design.md's Fix B, and commit to mctl-gitops main
       (ArgoCD self-heal will reconcile; this is a comment-only change with
       no functional diff, so no rollout is triggered by it alone).

6. [ ] Trigger a fresh incident-responder run (`mctl_trigger_incident_responder`
       or wait for the next 15/45-minute cron tick) and confirm the
       `mctl-agents-run incident-responder` Argo Workflow either succeeds, or
       fails with a materially different error than the previous
       "exit code 1 after ~11-14s on both run and run-fallback" signature.

7. [ ] If step 6 still reproduces the same fast dual-token failure after the
       DB fix, re-open investigation — the shared dependency is something
       other than the Argo Workflows List API, and pod-level stdout/stderr
       capture (e.g. temporarily raising `ttlStrategy.secondsAfterFailure` or
       pulling the archived `main.log` artifact from the
       `argo-workflows-logs` R2 bucket with real credentials) will be
       required to get a definitive answer.
