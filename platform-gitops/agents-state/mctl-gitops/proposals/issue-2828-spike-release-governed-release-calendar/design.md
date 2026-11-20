# Design: issue-2828-spike-release-governed-release-calendar

Revision 3 (2026-11-20). Revision 2 answered the independent review
([#2828 comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218):
4 P1, 5 P2, 2 P3). Revision 3 adds the owner's "Sync-broker integration design
request" and "Revision 3 instruction". It makes the **MCTL Governed Sync
Broker** a first-class alternative and compares it with E1 (GitOps carve-out),
E2 (RBAC-restricted `manualSync`), D (no runtime exception, break-glass only)
and native or plugin mechanisms. **E1 is no longer the preferred
candidate.** The scope is still **S0 only**: research, read-only inventory,
inert local experiments and a decision memo. Running S0 itself needs a
separate owner GO (requirements R-B5). Sections 5-9 describe what S0 must
*evaluate*; none of it is authorized to be built.

## Current state

Clone read at `main` = `467d6de920c1d69bd4fae6f2adce26f262d46482`
(2026-11-20 16:12 UTC). Repo citations are at this SHA. Revision 2 cited
`5bdf00a0`. The lines it relied on were re-read at `467d6de` and were
unchanged: `mctl-api.yaml:19,827-829,893-895`, `argocd/values.yaml:42-48,163-173`
and `argocd/rbac/tenants/*.csv`. Upstream Argo CD citations are at tag
`v3.3.8` (commit `7ae7d2cc723f5408b080a31263e705198af08613`, read 2026-11-20).
mctl-api citations are at `main` = `2a8de33ae4494f214ddb798d4cf880de24251160`
(committed 2026-11-19).

### Version governance that exists (no temporal policy)

- `platform-gitops/release-gates.yaml` has `version_holds` and `gates`. It has
  no time, window or freeze field, and no `syncWindows` exist anywhere in the
  repo.
- `scripts/release-gate.py` (`check`/`verify`/`diff`/`pr-identity`): exit 6
  means refused, exit 7 means could not observe. It reads the policy from a git
  revision.
- `scripts/release-ledger-shadow.py` `judge_ledger` is a **pure read**. It
  does not reserve or consume anything (review P1-2).
- mctl-api `internal/workitems/action_approvals.go` (header lines 18-50) is
  the existing single-use approval store, with states `pending -> approved |
  denied`, `approved -> consumed` (`ConsumeActionApproval`, line 912, one
  CAS guarded by state, `intent_hash`, `expires_at` and `fresh_until`),
  `consumed -> executed` (`MarkActionApprovalExecuted`, line 968) and
  `consumed -> in_flight -> executed | consumed` (`ReserveActionApproval`
  line 1056, `SettleActionApproval` line 1123, mctl-api#772). A failed
  settle returns `in_flight` to `consumed` "so a failed call does not burn the
  human approval". Requests are idempotent per `(requested_by,
  idempotency_key)`. Self-decision is refused (`ErrApprovalSelfDecision`).
- mctl-api `internal/workitems/release_approvals.go` defines the dedicated
  kind `release.grant` (mctl-api#1022, mctl-gitops#2528). It binds
  `execution_id` = tag commit, `target` = `<repo>@<version>` and
  `artifact_hash` = image digest, and the server builds the intent itself
  ("nothing in it comes from a request body"). `deploy_approvals.go:54-61`:
  `release.*`, `deploy.*` and `glovo.*` are **dedicated kinds** that every
  generic create, decide, consume, reserve or settle route refuses
  (`dedicatedKindPredicate`). Decisions are made on the MFA page
  (`release_decisions.go`, `release_approval_page.go`).
- `platform-gitops/argo-workflows/scripts/release-gate-guard.sh` guards gated
  groups only. It is called by `tpl-git-commit`, `tpl-validate-tenant`,
  `wft-add/remove-custom-domain`, `wft-deploy-service`,
  `wft-promote-deployment`, `wft-provision-database`, `wft-rollback-revision`
  and `wft-rollback-service`.
- `.github/workflows/release-gate-watch.yml` detects after the write.
  `.github/workflows/argocd-freshness.yml` checks resolution after push and
  is "Not a merge gate".

### Argo CD identities and RBAC today (desired state)

- `platform-gitops/argocd/values.yaml:163-173`: `policy.default: ""` and
  `scopes: "[groups]"`. `role:admin` has `applications, *, */*`,
  `projects, *`, `repositories, *` and `exec, create`, and is bound to group
  `admins`. `:30-31` names the break-glass path, `argocd --core` against the
  cluster kubeconfig.
- Local accounts `mctl-api` and `ci-freshness` (`apiKey` only, `:42-48`)
  have `applications, get, */*` only. No account has `sync`.
- `platform-gitops/argocd/rbac/tenants/{labs,mctl,karabu,namax66,redloop,erpact,commerce-proof}.csv`:
  every tenant role has `applications, sync, apps/<tenant>-*, allow` (erpact
  also has `erpact/*`), plus `action/apps/Deployment/restart` and
  `action/apps/StatefulSet/restart`.
  `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml:1093-1097`
  **generates** these lines for every new tenant.
- `application.sync.requireOverridePrivilegeForRevisionSync` is **not set**
  in `argocd/values.yaml`. At v3.3.8, `util/settings/settings.go:1525` reads
  it as `== "true"`, so it is effectively `false`. No principal holds
  `applications, override`, except `role:admin` through `applications, *`.
- `bootstrap/templates/projects/project-apps.yaml` defines no `roles:`, so no
  project-scoped JWT tokens exist, and no `syncWindows`.

### Application shape (relevant to an exact pin)

- `bootstrap/templates/bootstrap/applicationset-apps.yaml:34-61`: every
  `apps` Application is **multi-source**. Source 1 is the
  `helm-charts/base-service` path and source 2 is a `ref: values` source. Both
  are at `targetRevision` `main`. `syncPolicy.automated` has `prune: true` and
  `selfHeal: true`, and the options include `ApplyOutOfSyncOnly`. The
  ApplicationSet controller owns the Application spec.
  `manifest-generate-paths` limits refreshes to `/<svc path>` and
  `/platform-gitops/helm-charts/base-service`.
- `bootstrap/templates/mctl-platform/mctl-api.yaml`: source 1 is mctl-api
  `helm/` pinned at `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361` (`:19`),
  source 2 is mctl-gitops `infra-components/mctl-platform/mctl-api` at
  `main` (`:827-829`), and automated sync has prune and selfHeal
  (`:893-895`), in project `platform`.

### Argo CD v3.3.8 facts relevant to a broker (read from source at the tag)

- `server/application/application.go` `Sync` (around line 2020):
  1. It loads the Application and project with `get`, then evaluates
     `proj.Spec.SyncWindows.Matches(a).CanSync(true)`. Manual syncs are
     blocked by an active deny unless every active deny has `manualSync`.
  2. It then enforces `applications, sync`. Local `Manifests` need
     `applications, override` and are refused under auto-sync.
  3. `resolveSourceRevisions` (line 2136): a requested revision that differs
     from the source's `targetRevision` needs `override` **only when**
     `requireOverridePrivilegeForRevisionSync` is true. It is **always
     refused with FailedPrecondition when automated sync is enabled**
     ("Cannot sync to %s: auto-sync currently set to %s"). The same applies
     per source for multi-source Applications.
  4. Without a revision, `resolveRevision` resolves `targetRevision`
     (`main`) through the repo server **at request time** and stores the
     resolved SHA(s) in `Operation.Sync.Revision`/`Revisions`. It also stores
     `InitiatedBy.Username` and the caller's `Infos` key/values on the
     operation (lines 2091-2107).
  5. `argo.SetAppOperation` refuses if an operation is already running, so
     Argo serializes one operation per Application natively.
- **Consequence:** on v3.3.8, an auto-synced Application cannot be
  manual-synced to an exact, non-`targetRevision` SHA without mutating its
  spec (disabling automation or changing `targetRevision`). The API resolves
  `main` at call time, so a sync "to the approved SHA" holds only if `main`
  still renders the same manifests for that Application. For the `apps`
  Applications this spec is owned by the ApplicationSet. A live mutation is
  reverted by the AppSet controller unless it ignores those fields, and a
  GitOps mutation is itself a production-governance write.
- `Rollback` (history id) is refused when auto-sync is enabled ("rollback cannot be initiated
  when auto-sync is enabled", the `Rollback` function right after
  `resolveSourceRevisions`).
  `TerminateOperation` needs only `applications, sync` (line 2445), so a
  tenant can terminate a broker operation. That is a denial of service, not a
  bypass.
- `docs/user-guide/sync_windows.md` (v3.3.8) line 40: an active deny overrides
  an active allow. `manualSync: true` opens manual syncs for every principal
  that has `sync`. There is no per-role or per-request override. Upstream
  argoproj/argo-cd#29558 ("Allow specific RBAC roles to override an active
  deny sync window") was OPEN at the 2026-11-20 read (created 2026-09-04,
  last updated 2026-09-07). No native hook, admission plugin or sync-window
  webhook exists at v3.3.8 to authorize a single sync by request id. **Not
  found, and therefore treated as nonexistent.**
- From revision 2, re-confirmed: v3.3.8 `SyncWindow` has no `syncOverrun`
  (it exists only on upstream master). The `timeZone` offset is taken at
  `time.Now()`. Auto-sync and selfHeal are gated by `CanSync(false)`. An
  operation running when a deny window opens stays `Running` ("Sync operation
  blocked by sync window") and resumes after the window ends. A deny window
  **suspends** auto-sync for matching Applications while active. It does not
  change `syncPolicy`, and auto-sync resumes at window end with whatever
  `main` holds then.
- `docs/operator-manual/rbac.md` (v3.3.8) lines 207-221: `override` lets a
  caller sync arbitrary manifests or, with the flag, arbitrary revisions. The
  flag defaults to `false` "to prevent breaking changes".

### Table A: production effect paths, labelled for a window policy

Labels: `enforced`, `detected-after-write`, `not-covered`, `unknown`.

| # | Path | Changes | Pre-effect hook | Label for a future window check | Evidence |
|---|---|---|---|---|---|
| P1 | `release-deploy.yaml` (`preflight`, `ledger-gate`, `bump`, `publish-direct` env `gitops-bump`, `publish-pr`, `enqueue-bump`) | image tag/digest | in workflow, before push | candidate `enforced` at write; effect gap (section 3) | workflow file |
| P2 | `gitops-bump.yaml` (same job structure) | image tag/digest | yes | as P1 | workflow file |
| P3 | Human PR through merge queue | anything | PR + `merge_group` checks | `not-covered` at effect (section 3); check runs candidate code (section 4) | ruleset 18465404; `validate-manifests.yml` |
| P4 | `claude/*` auto-merge | anything not in `protected_re` | `validate` | as P3 | `auto-merge.yml` |
| P4b | `release-bump/*` enqueued by `scripts/release-bump-enqueue-wait.sh` | image | guard before enqueue | `not-covered` at merge/sync without an Argo layer | script header |
| P5a | CWFTs pushing to `main` (`wft-deploy-service`, `wft-rollback-*`, `wft-promote-deployment`, `tpl-git-commit`) | values incl. image | in template | candidate `enforced` after a hook exists | `grep -l "git push"` |
| P5c | Non-image CWFTs (`wft-create-tenant`, `wft-delete-tenant-safe`, `wft-retire-service`, `wft-add/remove-custom-domain`, `wft-provision-database`, `wft-platform-skill-*`) | namespaces, ingress, DB, removals, **tenant RBAC lines** | same | `not-covered` in an image-bump MVP | same grep; `wft-create-tenant.yaml:1093-1097` |
| P5b/P6 | Write deploy key outside template code; mctl-agents `commit-and-push` | any path | none | `unknown`: ruleset `bypass_actors` unreadable; #2543 OPEN (updated 2026-11-13) | `gh api` ruleset; runbook |
| P7a | `admins-mctl-api` source 1, mctl-api `helm/` pinned `c5e5d6f9...` | chart | pin moves only by GitOps PR | as P3 | `mctl-api.yaml:10-20` |
| P7b | `admins-mctl-api` source 2, `infra-components/mctl-platform/mctl-api` at `main` | manifests | none beyond P3 | as P3 | `mctl-api.yaml:827-829` |
| P7c | All `apps`/`tenants`/root Applications at `main` | everything under `platform-gitops/` | none beyond P3 | as P3 | `applicationset-apps.yaml`, `root-app.yaml` |
| P8a | Tenant manual sync (`applications, sync` on `apps/<tenant>-*`) | applies current `main` | Sync Windows (no `manualSync`) | `not-covered` today (no windows); `enforced` at sync start only with a deny window and no `manualSync` | tenant CSVs |
| P8b | `role:admin` sync, Application spec edit, `projects, *` (edit or delete windows), `override` | anything | none Argo can enforce against admin | `not-covered` (break-glass residual) | `argocd/values.yaml:167-172` |
| P8c | `kubectl` / `argocd --core` with cluster kubeconfig | anything | none | `not-covered` (break-glass residual) | `values.yaml:30-31` |
| P8d | Tenant resource actions (`Deployment/restart`) | restarts pods | not a sync; window effect unknown | `unknown` until the harness tests it (T93) | tenant CSVs |
| P9/P10 | Vault values, optional Secrets | runtime config | none in git | `not-covered` | runbook |
| P12 | Required contexts bound to integration 15368 | merge-gate trust | none | `unknown` / spoofable by a same-named job | ruleset read |
| P14 | `cloudflare-apply.yml` | edge/DNS/WAF | env reviewer | `not-covered` | workflow file |
| P15 | Merged before freeze, applied during freeze | as committed | Argo deny only | `not-covered` today | section 3 |

### Table B: non-image GitOps writes

`helm-charts/base-service/**` (every `apps` Application), `helm-charts/tenant/**`
(every `tenant-*`), non-`image` keys in `services/<team>/<svc>/values.yaml`,
`bootstrap/templates/**` (Applications, AppProjects, ApplicationSets),
`argocd/**` (RBAC CSVs, `argocd-cm`), `argo-workflows/**`,
`infra-components/**`. `release-gate.py` parses none of them. The MVP name
therefore stays **"image-bump window policy (partial coverage)"**. A
broker-protected Application changes this only at the point of sync and only
for that Application (section 6).

### Table C: GitOps path to Application to AppProject (hand-read; S0 task 4 regenerates it from a render)

| GitOps path | Application | AppProject | Destination ns |
|---|---|---|---|
| `services/<team>/<svc>/` + `helm-charts/base-service/` | `<team>-<svc>` (multi-source, auto-sync) | `apps` | `<team>` |
| `tenants/<t>/` + `helm-charts/tenant/` | `tenant-<t>` | `platform` | tenant chart |
| `bootstrap/templates/mctl-platform/mctl-api.yaml` + `infra-components/mctl-platform/mctl-api` | `admins-mctl-api` | `platform` | admins |
| `bootstrap/templates/erpact/applications.yaml` | `erpact-*` | `erpact` | erpact |
| `bootstrap/**` (incl. AppProjects) | `root-app` | `default` | argocd |
| `argocd/**` | `argocd-self-managed` | `default` | argocd |

Observations: hyphen-joined `<team>-<svc>` names make wildcards unsafe, so
only exact names are used (R-M2). AppProjects are rendered by `root-app` in
project `default`, so a window never blocks the commit that edits it (R-A9).
There is no production/preview project split (`project-prod.yaml` is a
commented TODO).

### Timing

- #970 (closed 2026-09-02) reported about 7 min. A push webhook,
  `--revision-cache-expiration=30s` and a 180 s poll have been added since.
  No latency distribution exists, so the figure is stale until measured.
- Merge queue (ruleset 18465404): `check_response_timeout_minutes: 120`,
  build and merge 1 entry, method `MERGE`.
- `main` receives frequent bot commits under `agents-state/` (10-20 per hour,
  per the comment in `applicationset-apps.yaml:28-32`). An approved
  **GitOps SHA is therefore almost never `main` HEAD** by the time a sync
  runs (section 6.3).

Deployed state checked:
- `git log -1` on the clone: `467d6de9...` (2026-11-20 16:12 UTC).
- `$MCTL_GITOPS_ROOT/services/*` and `tenants/*` were listed. This is desired
  state only. Tenants with services: admins, karabu, labs, namax66, redloop.
- `mctl_whoami` (re-run 2026-11-20): `agent:issue-investigator`, Admin false,
  Teams [], no namespaces.
- `mctl_get_service_status admins/mctl-api` (re-run): "ArgoCD application not
  found: admins-mctl-api". Recorded as **no access, not absence**. Live Argo
  CD version, live AppProjects, live `argocd-cm` (including
  `requireOverridePrivilegeForRevisionSync`) and live RBAC are `unknown`.
- `gh issue view 2543`: OPEN, updated 2026-11-13. argoproj/argo-cd#29558:
  OPEN, updated 2026-09-07.
- Upstream Argo CD v3.3.8 read: `server/application/application.go`,
  `util/settings/settings.go`, `docs/operator-manual/rbac.md`,
  `docs/operator-manual/argocd-cm.yaml`, `docs/user-guide/sync_windows.md`.
- mctl-api at `2a8de33`: `internal/workitems/action_approvals.go`,
  `release_approvals.go`, `deploy_approvals.go:54-61`.
- From revision 2, not re-run: ruleset 18465404 read (`bypass_actors` null);
  `argocd-freshness.yml` run listing; vendor docs (section 9).

## Proposed solution

S0 produces evidence, an offline model and a local inert harness. It does
**not** produce a running system. Sections 1-4 carry revision 2 forward.
Sections 5-8 are new or rewritten for the broker.

### 1. S0 deliverables and exit gate

1. `docs/spikes/2828-release-calendar/inventory.md`: tables A-C re-verified,
   plus the live Argo version, `argocd-cm` and RBAC, read by the owner
   (read-only), or `unknown`.
2. `tests/research/release_calendar_s0/model.py`: the pure policy function
   (section 2), run only by hand with `python3 -I`.
3. `tests/research/release_calendar_s0/argo-inert/`: a kind/k3d harness with
   Argo CD **v3.3.8** (chart `argo-cd` 9.5.9), a local git server and dummy
   Applications shaped like MCTL's (multi-source, auto-sync, AppSet-generated,
   two AppProjects, tenant CSVs copied from `rbac/tenants/labs.csv`).
4. `tests/research/release_calendar_s0/broker-model/`: an **inert broker
   prototype** (section 6). It talks only to the harness Argo CD and to a
   local Postgres that holds a copy of the `action_approval_requests` schema
   and CAS statements from mctl-api `2a8de33`. It is not a deployable
   service: no Dockerfile, chart or CI references.
5. `docs/spikes/2828-release-calendar/decision.md`: the matrix in section 8
   refreshed with results, one recommended outcome, residual risks and
   follow-ups mapped to existing issues.
6. Exit gate: independent review of the memo, then an owner decision on
   #2828. S1 needs a new proposal. Any Argo RBAC, AppProject, window, secret,
   account, flag or production change needs a separate owner **security** GO.

### 2. Policy model (illustrative schema, fixtures only)

```yaml
# tests/fixtures/release-calendar-s0/policy-example.yaml (illustrative; not a real freeze)
version: 1
default: allow
max_window: 21d
margins: {sync_start: 5m}       # placeholder until S0 task 3 measures it
scopes:
  platform-api: {applications: [admins-mctl-api]}
  labs-bot:     {applications: [labs-mctl-telegram]}
windows:
  - name: example-weekend-freeze
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    zone: Europe/Berlin
    recur: {freq: weekly, byday: [FR]}
    start_local: "16:00"
    end_local: {day_offset: 3, time: "08:00"}
    exception_path: broker           # broker | none (S0 compares e1/e2 only in fixtures)
  - name: example-year-end
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    start_utc: "2026-12-24T00:00:00Z"
    end_utc:   "2027-01-02T00:00:00Z"
    exception_path: none
```

Truth table (per Application, interval `I = [t_check, t_effect_max]`, first
matching row wins). It is unchanged from revision 2 and is identical to
`CanSync(false)` except that row 0 returns `UNKNOWN`:

| # | Condition | Result | Argo 3.3.8 `CanSync(false)` |
|---|---|---|---|
| 0 | policy unreadable/invalid | `UNKNOWN` | error → blocked |
| 1 | no window matches | `default` (`ALLOW`) | allow |
| 2 | a matching deny active in `I` | `DENY` | deny |
| 3 | allows match and `I` lies inside them | `ALLOW` | allow |
| 4 | allows match, otherwise | `DENY` | deny |
| 5 | only denies match, none active | `ALLOW` | allow |

Time semantics (unchanged): wall-clock local occurrences in an IANA zone with
`zoneinfo`; absolute `duration` only for `UTC` windows or UTC one-offs;
half-open `[start, end)`. A spring-forward gap moves to the first existing
instant. A fall-back ambiguity widens deny windows and narrows allow windows.
Fri 16:00 to Mon 08:00 Europe/Berlin is 64 h normally, 65 h across fall-back
and 63 h across spring-forward. Recurrence subset: daily, weekly or monthly,
with `byday` (no ordinals) and `bymonthday`, and no `COUNT`/`UNTIL`; anything
else is `UNKNOWN`.

### 3. Merge queue and point of effect

Four instants: `t_check`, `t_merge`, `t_sync_start`, `t_sync_end`.
Direct-push writers can re-check seconds before the push. Queued PRs can merge
up to 120 min after their check, so **no PR or queue path is `enforced` at the
point of effect** without an Argo deny window on the target Application. With
a deny window and no `manualSync`, a commit merged before the freeze is applied
at window end ("pending changes apply when the freeze ends"). A multi-wave
sync that is in flight when the window opens pauses partially applied
(v3.3.8). Fixtures T20-T25 are unchanged from revision 2.

### 4. Trust boundary

`validate-manifests.yml` runs `scripts/release-gate.py` from the PR merge-ref
checkout and reads only the policy from `HEAD^1`. Any evaluator must take code
and policy from the base commit and run with `python3 -I` from a directory that
holds no candidate files. Integration-15368 contexts are not trusted
enforcement (P12). `protected_re` is not a trust boundary. The same rule
applies to the broker: it reads policy, Application map and approved intent
from mctl-api and from a pinned base revision, **never from a payload, an
agent worktree or a PR head** (R-G10). Fixtures T70-T74 are unchanged.

### 5. Grant lifecycle (shared by every exception path)

Authority stays with a human on the existing mctl-api MFA decide page. The
calendar, the broker and agents add no approver.

**Reused from mctl-api (no new authority):** the `action_approval_requests`
table and its CAS discipline (`ConsumeActionApproval`); the
dedicated-kind namespace mechanism (`release.*` is already dedicated, so
`release.freeze_exception` would be refused by every generic route); the
server-built intent pattern from `release.grant` (intent from what the server
reads, never from a request body); `fresh_until`, `expires_at`, refusal of
self-decision, idempotency per `(requested_by, idempotency_key)`; the MFA
release decide page.

**New (would need its own proposal and mctl-api owner GO):** a dedicated kind
`release.freeze_exception` with its own create, decide and spend paths. The
spend path must **not** reuse `SettleActionApproval(succeeded=false)`, which
returns `in_flight -> consumed` and makes a grant reusable. Once an Argo
operation may have been created, the grant must never become spendable again
(R-G6). Proposed dedicated states: `approved -> claimed(broker_op_id) ->
executed | spent_failed | spent_unknown`. Only `claimed -> executed` and the
two `spent_*` states are terminal, and none returns to `approved` or
`consumed`.

**Intent (server-built).** The fields are kind, AppProject, Application name
and namespace, tenant and environment, approved GitOps SHA, **every** source's
resolved revision (for `apps`: base-service chart source and values source;
for `admins-mctl-api`: the mctl-api chart pin and the `infra-components`
source), the SHA-256 of the rendered manifests for that Application at those
revisions (canonical JSON of the repo-server `GetManifests` output, sorted),
a digest of the live Application spec that the render assumes (sources,
destination, `syncPolicy`, `syncOptions`), image repository and `sha256`
digest(s), the diff against the live state, the reason class (`hotfix` or
`rollback` plus the target `dep_` id), requester, `not_after` and a single-use
nonce. mctl-api computes the intent from its own reads (or from the broker's
trusted render, see 6.2). A client field that is not reproduced by that read
is refused (T86).

**Logical AND.** A version hold, gate group, ledger requirement or `min_tag`
still refuses even with a valid exception. A separate `release.grant` is
still required wherever it is required today (R-X8).

### 6. MCTL Governed Sync Broker (first-class alternative; S0 builds an inert prototype only)

#### 6.1 Shape

A small trusted process, **separate from agent pods and agent worktrees**,
that owns the only non-break-glass Argo CD identity allowed to sync a frozen
pilot Application. In S0 it exists only as `broker-model/` against the
harness. For an eventual production boundary (not authorized here), the memo
compares two placements:

- **(i) Separate Deployment in `admins`** with its own ServiceAccount, its
  Argo token delivered by ExternalSecret from a Vault path that no agent role
  reads, and a NetworkPolicy that allows only mctl-api → broker and
  broker → `argocd-server`. The broker pulls grants by id from mctl-api and
  accepts no manifest, revision or Application spec from callers.
- **(ii) Inside mctl-api.** This removes a hop, but puts the sync token in a
  process that agents reach through MCP and widens mctl-api's Argo account
  beyond today's `applications, get`. S0 records why (i) is the default
  candidate. This is not decided.

Argo identity options, compared in the harness: a local account
`release-broker` (`apiKey` only, no `login`) with
`p, release-broker, applications, sync, <project>/<exact app>, allow` and
`get`; **or** a project-scoped role on the pilot AppProject with a JWT token.
Both have no `override`, no `update`, no `projects` and no wildcard. Under
both, `requireOverridePrivilegeForRevisionSync` would be set to `"true"`, so
that no one without `override` can sync a non-`targetRevision` revision
(defence in depth; on auto-sync Applications it is refused anyway).

#### 6.2 Flow (one grant, one sync)

1. **Intent.** After the hotfix or rollback commit is on `main` (merged
   through the normal guarded path; during a deny window the write may land,
   because the Argo window holds the effect), a requester (operator or agent)
   asks mctl-api for a `release.freeze_exception`. mctl-api asks the broker
   (trusted render, base-pinned) to compute the intent fields in section 5 at
   the named SHA. The request is pending.
2. **Decision.** A human approves it on the MFA decide page. A separate
   `release.grant` is still required where one applies.
3. **Preflight (no side effect).** The broker re-reads: the live AppProject
   (windows active, deny with `manualSync: true` on exactly the pilot
   Applications, no allow-overrides); the live Application spec digest; `main`
   resolved by the repo server for every source; the rendered manifest hash
   for the Application at those revisions; the image digest(s); release-gates
   and holds at the base; no operation running. Any mismatch → refuse; the
   grant stays `approved` (nothing has been claimed).
4. **Claim (atomic, durable).** The broker writes a journal row
   `(aar_id UNIQUE, request_id, app, expected_revisions, manifest_hash,
   state=claiming)` and then runs the dedicated CAS `approved ->
   claimed(request_id)` with the intent hash. One of two concurrent brokers or
   requests wins. The loser gets a refusal and never calls Argo (T80).
5. **Sync.** The broker calls `ApplicationService.Sync` once, with **no
   revision** (a revision is refused on auto-sync Applications, section
   Current state), fixed `prune`/`syncOptions`/`strategy` equal to the
   Application's own, no `resources` subset, no `manifests`, and
   `infos: [{name: mctl-release-exception, value: <aar_id>/<request_id>}]`.
6. **Bind the operation.** The response carries `operation.sync.revisions`,
   which the API server resolved. If they differ from the expected revisions
   **and** the rendered manifest hash at them differs, the broker immediately
   calls `TerminateOperation` and moves the grant to `spent_failed`. Some
   resources may already have been applied, which is recorded as a residual
   (T85). If the revisions differ but the manifest hash is equal (an unrelated
   commit such as an `agents-state/` bot commit), the sync is accepted and the
   journal records both SHAs (section 6.3).
7. **Observe and reconcile.** The broker polls `status.operationState` until
   `Succeeded`, `Failed` or `Error`, matches it by `info` `aar_id`, records the
   synced revisions, the live image digest and health, and moves the grant to
   `executed` or `spent_failed`. If it crashes, times out or loses Argo, the
   journal holds `claimed`. On restart the broker **only observes**: it looks
   up the operation by `info` and `initiatedBy`. It never issues a second sync
   for that grant. Unknown after a bound → `spent_unknown`, and an alert asks a
   human. A new sync needs a new grant (T88, T89).
8. **Window unchanged.** At no step does the broker edit the AppProject, the
   Application spec or RBAC. The deny window keeps blocking auto-sync and
   selfHeal before and after the exception.

#### 6.3 What "sync the approved SHA" can and cannot mean on v3.3.8

- **Exact pin by SHA is not available** for auto-synced Applications without
  mutating their spec. The broker therefore binds **content, not HEAD**: the
  sync is accepted if the revisions Argo resolves render the same manifest hash
  for that Application as the approved SHA, and the diff from approved SHA to
  resolved SHA touches none of the Application's `manifest-generate-paths` or
  source paths (for `apps`: `/<svc path>` and
  `/platform-gitops/helm-charts/base-service`).
- A non-HEAD approved SHA is the normal case (bot commits). If `main` changed
  the Application's render after approval (another hotfix, a shared-chart
  change, an AppSet template change), the broker refuses in step 3 or
  terminates in step 6. The grant cannot be reused, and a new grant binds the
  new content.
- **Race after approval, before sync:** writes between steps 3 and 5 are the
  TOCTOU gap. It is narrowed by step 6 (post-resolution check plus
  terminate). It is closed for a protected Application only if GitOps write
  guards also refuse writes to its paths during the window, which is an
  image-bump-only guard today (Table B). S0 measures the gap on the harness
  (T84, T85) and states it as residual.
- **Live Application spec changes** (AppSet regeneration, admin edit) change
  what a sync applies without any git diff on the service path. Step 3
  compares the spec digest, and step 6 re-reads it.
- **Multi-source Applications**: every source's resolved revision is bound.
  A source pinned to a SHA (mctl-api chart `c5e5d6f9`) is bound as-is. A
  multi-source Application whose sources resolve to repos the broker cannot
  render is `REFUSE` (unsupported).
- **Rollback**: a "previously healthy rollback" is a **forward commit** that
  restores the values of a `dep_` deployment recorded as healthy (the
  `wft-rollback-revision` path), followed by a broker sync under its own
  grant. Argo's history `Rollback` API is refused under auto-sync and is not
  used.

#### 6.4 RBAC and token isolation for frozen Applications

- With `deny` and `manualSync: true` on a pilot Application, **every**
  principal with `applications, sync` can sync it. For a pilot in project
  `apps`, the owning tenant's role (`apps/<tenant>-*`) must therefore lose
  `sync` on that exact Application, through an explicit RBAC `deny` line for
  that Application or by narrowing the tenant pattern. `wft-create-tenant`
  must stop regenerating the broad line for it. The harness tests both forms
  (T90). Outside a freeze, the tenant loses manual sync on that Application
  permanently, which is a UX cost. Auto-sync is unaffected outside the window.
- `role:admin` (group `admins`) keeps `applications, *` and `projects, *`, so
  it can sync, edit windows or override. `kubectl` and `argocd --core` bypass
  Argo RBAC entirely. These are **explicit break-glass residuals** and are
  never claimed as covered. S0 records evidence only: Argo audit events of
  `initiatedBy` and `kubectl` audit availability (unknown).
- Token exfiltration boundary: the broker token is scoped to `sync`/`get` on
  the exact pilot Applications. Stolen, it lets an attacker sync current `main`
  of those Applications during a freeze, not arbitrary manifests or revisions
  (no `override`). This is the residual blast radius. Mitigations to evaluate:
  short-lived project-role JWT, rotation, Vault path not readable by agent
  roles, NetworkPolicy, and a detector that alerts on any sync of a pilot
  Application whose `info` lacks a journaled `aar_id` (T91).

#### 6.5 Default deny and recoverability

No grant, mctl-api unreachable, policy unreadable, changed manifest, changed
spec, unknown operation outcome, broker down or Argo down → **no new
unauthorized sync**. The window stays deny and nothing is opened (fail
closed). Recovery when the broker is down is the documented break-glass
(admin, out of band, reviewed afterwards), never a window edit by automation.
No persistent bypass is created, because the broker never changes the window,
RBAC or Application spec.

### 7. Other exception paths (compared, not preferred)

- **E1, GitOps carve-out.** After an approval, a commit regenerates the
  AppProject without the Application in the deny window, auto-sync applies
  `main`, and a second commit restores the window. This **fails open**: a
  failed or late restore leaves the Application unprotected, and during the
  carve-out every tenant sync and every new commit to its paths is applied.
  It applies whatever `main` holds, with no content binding at effect. Its
  AppProject writes during a freeze ride `root-app` (project `default`).
  Retained only as a comparison baseline (T97).
- **E2, RBAC-restricted `manualSync`.** Deny with `manualSync: true` plus
  tenant `sync` removed for the frozen Application, and a human with a
  dedicated role syncs by hand. This is fail-closed at Argo, but it has no
  digest or grant binding: any holder of the role can sync any `main` content.
  **The Broker is E2 plus a grant-bound, journaled, single-use caller.** If
  the broker is rejected, E2 with a human-held role is the fallback, but it
  is not "exactly one MFA-authorized release".
- **B (issue), temporary per-Application window exception.** This is the same
  mechanism as E1, with a TTL and generated cleanup. It inherits E1's
  fail-open restore and its unbound content. Rejected unless S0 proves
  otherwise.
- **C (issue), upstream, fork or proxy.** No v3.3.8 hook exists, and #29558 is
  open. A fork means owning Argo upgrades. A proxy in front of
  `argocd-server` does not stop UI, CLI or admin paths that do not go through
  it. Recorded with cost only, not prototyped.
- **D, no runtime exception.** Immutable deny with `manualSync: false`. A
  hotfix needs an admin break-glass (remove window, or `argocd --core`) with an
  incident record. This is simplest and fully fail-closed for non-admins, but
  every hotfix is an admin action with a manual, unbound audit.

### 8. S0 decision / coverage / threat / cost matrix (current evidence; refreshed at S0 exit)

| Criterion | Broker | E1 carve-out | E2 manualSync + RBAC | D break-glass only | Native/plugin (C) |
|---|---|---|---|---|---|
| Exactly one approved release | yes, grant CAS + journal + content check | no (applies `main`) | no (role holder, any time) | no (admin) | n/a (none at v3.3.8) |
| Fail mode | closed | **open** on failed restore | closed | closed | n/a |
| Content binding at effect | manifest hash + revisions, post-resolution check; TOCTOU residual | none | none | none | n/a |
| Tenant manual-sync bypass | blocked (tenant `sync` removed) | open during carve-out | blocked | blocked (no `manualSync`) | n/a |
| Admin / kubectl bypass | residual | residual | residual | residual (is the path) | residual |
| Second approval authority | no (mctl-api ledger) | no | **human role is de facto authority** | admin is | n/a |
| New trusted component and state | broker process, Argo token, journal, dedicated kind | generator + detector | role + token | none | fork |
| Tenant UX cost | loses manual sync on pilot app | none | loses manual sync on frozen app | none | n/a |
| Implementation burden | high | medium | low | none | very high |
| Recovery when component down | break-glass (D) | must restore window | role holder | n/a | n/a |

Falsifiable S0 outcome. The memo must pick exactly one:
- `BROKER_PILOT_CANDIDATE`: T80-T96 pass on the harness, the TOCTOU residual
  is measured and bounded, and the dedicated-kind spend semantics are
  acceptable to the mctl-api owner.
- `E2_HUMAN_ROLE_ONLY`: the broker fails a fail-closed or single-use test
  that cannot be fixed without an Argo change, but RBAC isolation (T90) holds.
- `D_BREAKGLASS_ONLY`: neither the broker nor E2 isolates tenants on v3.3.8.
- `NEITHER_SAFE_YET` (equivalently `DEFER_UNTIL_GATES_CLOSED`): blocking
  unknowns remain (#2543, P12, live RBAC/argocd-cm unreadable).

The calendar decision outcome (`REUSE_EXISTING_ONLY` / `BOUNDED_CALENDAR_MVP`
/ `ADOPT_ARGO_SYNC_WINDOWS` / `HYBRID` / `DEFER_UNTIL_GATES_CLOSED`) is
recorded alongside it. The working hypothesis is `HYBRID`, with Sync Windows
as the secondary point-of-sync safeguard and the broker as the exception
path, both under investigation.

### 9. Translation matrix and product comparison (from revision 2, unchanged)

Translation to v3.3.8 `syncWindows`: weekly, daily and `bymonthday` UTC →
translatable. Recurring windows in DST zones → UTC cron widened for deny and
narrowed for allow, or `not-translatable`. One-offs, including cross-year
`0 0 24 12 *` + `216h` → translatable-with-lifecycle (emit near start,
remove after end, drift check). Ordinal weekday, `COUNT` or `UNTIL` →
not-translatable, so the Argo layer is `incomplete` and the generator exits
non-zero with no partial projection. `timeZone` is not used. The broker
needs only that the deny window exists with `manualSync: true` on exactly the
pilot Applications; it adds no translation constructs.

Products (primary docs read 2026-11-20):
[GitLab deploy freezes](https://docs.gitlab.com/user/project/releases/) set
an advisory `$CI_DEPLOY_FREEZE`.
[Octopus deployment freezes](https://octopus.com/docs/deployments/deployment-freezes)
have project, environment and tenant scope and an override-with-reason
permission; multi-project freezes are enterprise-only from 2025.2.7631.
[Harness deployment freeze](https://developer.harness.io/docs/continuous-delivery/manage-deployments/deployment-freeze/)
is beta behind a flag, "Account admins will always be able to bypass", and a
running pipeline finishes its stage. None governs MCTL's GitOps writes or Argo
syncs, all are reference only, and prices are `unknown`.

## Alternatives

- **E1 as the default exception path (revision 2's leaning).** Dropped as the
  default: it fails open and applies unbound `main` content (section 7). Kept
  as a test baseline.
- **Global `manualSync: true`.** Rejected: every tenant and admin sync becomes
  a bypass while the tenant CSVs grant `sync`.
- **ADOPT_ARGO_SYNC_WINDOWS alone as the authorizer.** Dropped: Argo cannot
  see MFA grants or digests. Sync Windows stay the secondary safeguard.
- **External CD product (Octopus, Harness, GitLab).** Dropped as an engine
  (second authority, governs only its own pipelines).
- **Mutating the Application spec to pin a SHA (disable auto-sync or set
  `targetRevision` per exception).** Dropped: the AppSet owns the spec, the
  mutation is itself an unbound production write, and the revert is a
  fail-open step similar to E1.
- **A "production deployment freeze" claim.** Dropped: Table A/B paths have no
  pre-effect hook.

## Platform impact

- Migrations: none. S0 adds documentation, inert fixtures, a local harness
  and an inert broker prototype. Workflows, charts, CWFTs and services
  reference none of them.
- Backward compatibility: no behaviour change. Release holds, ledger mode,
  merge queue, Argo settings, RBAC, AppProjects and mctl-api are untouched.
- Resources: a local kind/k3d cluster and a local Postgres on the researcher's
  machine only.
- Eventual production boundary (not authorized; recorded for the security
  GO): it would require an Argo account or project role, an `argocd-cm` flag,
  RBAC deny lines for pilot Applications, a narrower `wft-create-tenant`
  template, a deny window on one pilot AppProject, a Vault path and
  ExternalSecret, a broker Deployment and NetworkPolicy, and a mctl-api
  dedicated kind. Every one is a separate reviewed change, reversible by
  revert, with the broker removable without touching the window (fail-closed
  remove).
- Risks and mitigations: S0 output mistaken for a GO (stage table, R-B4);
  the harness touching production (the scripts refuse any kube context but
  their own and use no mctl credentials); stale evidence (every claim pinned
  to a SHA, tag or dated read; unreadable means `unknown`); broker becoming a
  second authority (it only spends ledger grants and cannot create or decide
  them).
