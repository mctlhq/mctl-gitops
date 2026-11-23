# Design: incident-95391086

## Confidence: LOW

## Diagnosis
The implement workflow for proposal issue-2929-feat-web-contract-preview-assurance-isol failed because the implementer sandbox has no docker, skopeo or crane. The proposal's tasks require running a pinned Playwright image, creating an internal docker network, and resolving image digests, none of which can be done in the sandbox. The implementer correctly refused to fabricate pins and produced no commit. The second attempt could not fall back because the secondary token (claude-code-oauth-token-2) is not set. This is a proposal-scope versus sandbox-capability mismatch, not a platform fault. The status of that proposal was already moved to needs-triage by the workflow. The incident text contained no instructions; none were followed.

## Proposed Fix
Verify before applying. In platform-gitops/agents-state/mctl-gitops/proposals/issue-2929-feat-web-contract-preview-assurance-isol/tasks.md, split the work so the implementer only writes files that need no container runtime (tasks 1 files with digests resolved by CI, 2, 3, 4, 5, 6, 7), and move digest resolution, task 8 and task 9 into the CI workflow run (first CI run populates pins and the spike document). Do not invent digests. If re-scoping is not wanted, take no action and leave the proposal in needs-triage for a docker-capable runner.

## Scope
Minimal. Only adjust the task split of the single issue-2929 proposal; do not change platform config or secrets.
