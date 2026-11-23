# Tasks: issue-2931-ci-gitops-agents-state-direct-pushes-sta

- [ ] 1. Add `scripts/merge-queue-starvation.py` (merge queue GraphQL read, merge_group run rebuild count, direct-push count, threshold decision, exit 0/1/2) — DoD: pure functions unit-testable without network; exit 2 with "unknown" on any read error.
- [ ] 2. Add `.github/workflows/merge-queue-starvation-watch.yml` (schedule `*/10 * * * *` + workflow_dispatch, `GITHUB_TOKEN` read-only, no environment/secrets) (depends on 1) — DoD: run is red with an `::error::` naming head PR, wait, rebuild count and direct-push count when thresholds trip; green when the queue is empty or healthy.
- [ ] 3. Add `tests/test_merge_queue_starvation.py` and a step in `validate-manifests.yml` running it (depends on 1) — DoD: tests pass in CI.
- [ ] 4. Add `platform-gitops/argo-workflows/scripts/merge-queue-quiet-wait.sh` implementing off/shadow/enforce, release-on-head-change, time limit and fail-open — DoD: POSIX sh, shellcheck-clean, every exit path exits 0, and every decision logs one structured line (`mq-gate mode=... decision=... head=... waited_s=...`).
- [ ] 5. Add an `await-merge-queue-quiet` template (no mutex, own deadline, `github-token-file`, egress proxy env, pinned curl+jq image, `continueOn`) to investigate, implement, shepherd, run and reconcile, placed immediately before `commit-and-push`, with workflow parameter `merge_queue_gate` default `shadow` (depends on 4) — DoD: `helm`/kubeconform validation green; `commit-and-push` runs whatever the gate's result; approve is untouched.
- [ ] 6. Register the new template as a token consumer in the agent credential inventory (see `docs/runbooks/agent-credential-delivery.md`) (depends on 5) — DoD: the inventory CI validator passes.
- [ ] 7. Add a test `tests/test_cwft_merge_queue_gate.py` pinning: the gate is present before `commit-and-push` in the five CWFTs, absent from approve, has no `synchronization`, has `continueOn`, defaults to `shadow`, and `commit-and-push` pathspecs/mutex are unchanged (depends on 5) — DoD: wired into `validate-manifests.yml` and green.
- [ ] 8. Document the gate, switches, thresholds and the watch (runbook section linked from `CLAUDE.md`; P6 row note in `docs/runbooks/mctl-api-release-hold.md`) (depends on 2, 5) — DoD: runbook explains how to switch modes and read the logs.
- [ ] 9. After one week of shadow logs, a separate PR flips `merge_queue_gate` to `enforce` (depends on 5, 8) — DoD: shadow logs show expected decisions; PR references this proposal.
- [ ] 10. File a follow-up issue for option 2 (agents-state off `main`), linked to #2543 and this issue — DoD: issue exists with the readers listed in design.md.

## Tests
- [ ] T1. Unit: starvation decision for an empty queue (pass), head age over threshold (fail), rebuilds >= 3 (fail), API error (exit 2).
- [ ] T2. Unit (shell, with a stub `curl` on PATH): the gate exits immediately when no entry is AWAITING_CHECKS; waits, then releases when the head PR disappears; releases at the time limit with WARN; fails open on HTTP 5xx / malformed JSON / missing token; never sleeps in shadow mode; is a no-op when off.
- [ ] T3. Static: `tests/test_cwft_merge_queue_gate.py` (task 7).
- [ ] T4. Live shadow check: trigger one `mctl_trigger_reconcile dry_run=true` while a PR is queued and confirm the `mq-gate` log line in the workflow logs.
- [ ] T5. After enforce: during the next DevLoop burst, the watch stays green and queue heads merge within one validate cycle plus the gate limit.

## Rollback
- Gate: set the workflow parameter `merge_queue_gate` to `off` (or revert the default) in the CWFTs with one PR. After Argo CD sync (~3 min), new runs skip the gate. Reverting the template PR removes it completely. `commit-and-push` was never modified, so pushes behave exactly as before.
- Watch: disable the workflow (`gh workflow disable merge-queue-starvation-watch.yml`) or revert its PR. It holds no secrets and writes nothing.
