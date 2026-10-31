# Requirements: deploy-analyze-and-plan
version-status: verified (tools exposed by live MCP server); commits ee7aaca, 48a4b69, 2400c1f in mctl-api

## Acceptance criteria (EARS)
- THE tools reference SHALL document `mctl_deploy_analyze`, `mctl_get_repo_binding`, `mctl_deploy_plan`, `mctl_get_deploy_plan`.
- WHEN `mctl_deploy_analyze` is described, THE page SHALL state `revision` must be a full 40-hex commit SHA, only tenant-bound repos readable by mctl's GitHub credential are analyzed, and nothing is cloned, built or run.
- THE page SHALL describe the three outcomes: `draft_intent`, `needs_input` (runtime.port, runtime.healthPath, metadata.service), `supported=false` with reason.
- THE page SHALL state `mctl_deploy_plan` only plans `environment=preview`, writes no gitops file, redacts secret references, and is deterministic (same intent, same digest); `idempotency_key` replays.
- THE guide `docs/guides/services.md` SHALL link to the analyze → plan flow.
