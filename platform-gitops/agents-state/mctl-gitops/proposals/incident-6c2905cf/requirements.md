# Requirements: incident-6c2905cf

## Incident
- ID: 8fde2aa5-72ea-4a53-9ea4-06886c2905cf
- Tenant: labs
- Service: labs-agent-worker-preview-base-service
- Alert: KubeDeploymentRolloutStuck
- Created: 2026-09-19T13:49:45.344694Z

### Summary
```
Deployment rollout is not progressing.
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
status: escalated
confidence: LOW
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=KubeDeploymentRolloutStuck). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

Related incident 18b0c978-abb1-4664-a479-dcae3a73ead4 (ArgoCDApplicationDegraded,
same underlying workload `labs-agent-worker-preview`) fired 15 minutes after
this one and shares the same root cause described in design.md -- both are
symptoms of the same stuck rollout.

### Log Snippet
Pod `labs-agent-worker-preview-base-service-657bd68fd5-5w7xp` logs, most
recent first, showing the currently-running pod healthy and processing jobs
continuously both before and after the incident window (proving the existing
pod never went down -- the rollout-stuck state comes from an inability to
schedule a *new* pod, not a crash of the current one):
```
{"time":"2026-09-19T15:03:04.369677124Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6126,"outcome":"completed"}
{"time":"2026-09-19T14:46:01.167448181Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6125,"outcome":"completed"}
{"time":"2026-09-19T14:30:01.848310628Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6124,"outcome":"completed"}
{"time":"2026-09-19T13:58:10.494561186Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6123,"outcome":"completed"}
{"time":"2026-09-19T13:55:22.253219119Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6122,"outcome":"completed"}
{"time":"2026-09-19T13:54:08.271642555Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6120,"outcome":"completed"}
{"time":"2026-09-19T13:22:11.702567934Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":16000000000}
{"time":"2026-09-19T13:22:03.694373964Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":8000000000}
{"time":"2026-09-19T13:21:59.69125162Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":4000000000}
{"time":"2026-09-19T13:21:57.687200909Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": EOF","retry_in":2000000000}
{"time":"2026-09-19T13:16:59.959590664Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6113,"outcome":"completed"}
```
The brief connection-refused window at 13:21-13:22 coincides with an
unrelated restart of the downstream `mctl-telegram-preview` pod it polls,
and self-resolved by 13:24 -- it is a red herring, not the cause of the
rollout-stuck alert, which fired afterward and stayed active.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
