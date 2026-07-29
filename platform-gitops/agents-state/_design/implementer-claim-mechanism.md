# Implementer parallelism — claim-based design

**Status:** WIP / tracking. Not implemented. PR #83 was the wrong shape (closed 2026-05-01).

## Goal

Allow N concurrent `mctl_trigger_implementer` invocations to run their heavy steps
(`clone-gitops`, `run-implementer` / Claude SDK) in parallel. Currently the
workflow-level `mctl-gitops-main-writes` mutex on `cwft-mctl-agents-implement`
serializes everything end-to-end (~5–10 min × N proposals).

## Why simple mutex narrowing fails

Codex P1 on PR #83: races on **proposal selection time**, not just Git push.

Two no-filter implement workflows can both observe a proposal as `accepted`,
both run-implementer, both push to `mctlhq/<service>:feat/agents-<slug>`, both
attempt `gh pr create` — duplicate Claude SDK spend, branch ref races, possibly
two PRs. Only commit-and-push serializing is too late; side effects in the
sibling repo already happened.

## Right design — durable per-proposal claim in `.status.yaml`

State machine: `accepted → implementing → implemented` (or `failed`).

`implementing` carries claim metadata:

```yaml
status: implementing
implementation:
  claim_id: <argo workflow uid>
  workflow: <argo workflow name>
  branch: mctl/implement/<service>/<slug>   # deterministic
  started_at: 2026-05-01T...
  expires_at: 2026-05-01T...                # started_at + 1h
```

CWFT becomes 4 steps:

| step              | mutex                       | duration   |
|-------------------|-----------------------------|------------|
| clone-gitops      | none                        | ~30s       |
| claim-proposal    | mctl-gitops-main-writes     | <30s       |
| run-implementer   | none                        | 5–10 min   |
| commit-and-push   | mctl-gitops-main-writes     | <30s       |

`claim-proposal` logic:

1. `git pull --rebase origin main` (fresh snapshot)
2. Re-check `.status.yaml`: `accepted` → claim. `implementing` non-expired by
   another workflow → refuse/skip. `implementing` expired → steal (force=true)
   or refuse (force=false). `implemented` → skip unless `force_steal`.
3. Write `.status.yaml` → `implementing` with claim metadata.
4. Commit + `git push origin HEAD:main` with rebase-on-conflict retry.

`run-implementer` then runs in parallel — every workflow owns a distinct claim,
no race on selection.

## Required changes

### mctl-agents (Python orchestrator)

- New helper `claim_proposal(service, slug, force, force_steal)` — reads,
  CAS-writes `.status.yaml`, pushes to main. Returns claim metadata or `None`
  (already claimed / not accepted).
- `run_implementer.py`:
  - Deterministic branch name `mctl/implement/<service>/<slug>`.
  - Before `gh pr create`: lookup existing PR by `--head`; update existing
    branch with new commits if found, don't open a duplicate.
  - Force semantics:
    - `force=false` (default): skip implementing/implemented, claim accepted only.
    - `force=true`: also steal **expired** implementing claims.
    - `force_steal=true` (new): also steal **active** implementing claims —
      operator escape hatch.

### mctl-gitops (CWFT)

- Add `claim-proposal` template between `clone-gitops` and `run-implementer`.
- Move mutex from workflow-level to template-level on `claim-proposal` AND
  `commit-and-push` only.
- `cwft-mctl-agents-run` keeps workflow-level mutex (cron, single instance,
  doesn't benefit from parallelism).

### Recovery / observability

- Stale claim detector: `now > expires_at` → recoverable via `force=true`.
- Surface claim metadata in `mctl_list_recent_agent_runs` output so operators
  see who holds what.

## Why Git-backed claim (not k8s Lease, not API mutex)

- Authoritative state already in Git (`.status.yaml`). k8s Lease creates
  split-brain (Lease locked + Git accepted, or Lease expired + Git
  implementing).
- API-level mutex breaks under: API restart, multi-replica API, manual
  `argo submit`, cron, future automation. Acceptable only as defense-in-depth.
- Separate `.lock` file in gitops repo = second state object that can drift
  from `.status.yaml`. Inline into the status file.

## Hidden risks

- Daily run + implement.claim must use same `mctl-gitops-main-writes` mutex
  name (already do via shared mutex). Keep that contract.
- Multiple Argo controllers (future) → switch to database-backed `synchronization`.
- Failure after claim without `expires_at` → proposal pinned forever. Always
  set `expires_at`.
- Force-with-lease push for branch updates so retry doesn't clobber another
  workflow's commits.

## Tracking

- PR #83 (closed 2026-05-01) was the wrong shape.
- This PR is a placeholder for the full work (mctl-agents code + CWFT changes
  + image tag bump). Will be split into reviewable commits when implementation
  starts.
- Until this lands: parallel batches of `mctl_trigger_implementer` **must**
  pass explicit `--service+--slug`. No-filter triggers must not run concurrently.
