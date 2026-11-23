# Design: issue-2828-spike-release-governed-release-calendar

Revision 5 (2026-11-21). It answers the independent review of revision 4
([comment 7064106704](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7064106704):
1 P1 / 2 P2). What changed in revision 5:

- **Bootstrap self-lockout (P1; sections 3.2, 6.7, 8.2, 8.3).** Revision 4
  claimed that a window never blocks its own removal. That is false for a
  deny in AppProject `default` that matches `root-app`, which applies every
  AppProject. The MVP now refuses every window in `default`, and refuses any
  window whose **rendered** match set reaches the recovery chain
  (`root-app`, `argocd-self-managed`). A live self-lockout is a distinct
  state, `self-locked`, with a harness-only break-glass walk.
- **Single-pilot pin migration (P2; section 6.3.1).** The shared
  `.Values.spec.source.targetRevision` cannot pin one pilot. Three
  per-Application mechanisms (M1 merge generator, M2 git files generator,
  M3 isolation) are specified as S0 feasibility tests with byte-equal and
  no-deletion proofs, plus a reverse migration.
- **Deny-only MVP (P2; sections 2.1, 8.2).** `kind: allow` is refused on
  every write path. Allow stays in the offline model only.

Revision 4 (2026-11-21). Revision 2 answered the first review
([comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218)).
Revision 3 made the **MCTL Governed Sync Broker** a first-class alternative
to E1 (GitOps carve-out), E2 (RBAC-restricted `manualSync`), D (break-glass
only) and native or plugin mechanisms. Revision 4 answers the independent
re-review of revision 3 (#2828, 2026-11-21: 4 P1 / 3 P2 / 1 P3). The
finding-to-section map is in requirements.md, "Finding index".

What changed in revision 4:

- **Guarantee classes (section 6.0).** The revision 3 claim "exactly one
  approved release: yes" is withdrawn. A broker that syncs an Application
  tracking `main` gets G2 at best: it detects after the operation is created
  and then terminates.
- **A G0 candidate, read from v3.3.8 source (section 6.3).** A broker can
  `Sync` with the exact SHA-pinned `targetRevision` of every source.
- **An observed window activation lifecycle (section 3.1).**
- **A token-compromise boundary (section 6.6).**
- **A safe transition order (section 6.7).**
- **A single-transaction journal and claim with a crash matrix (section 6.5).**
- **MCP PR-authoring tools and a status contract (section 8).** Both are
  design only.

The scope is still **S0 only**. Running S0 needs a separate owner GO
(R-B5). Sections 5-9 describe what S0 must *evaluate*. None of it is
authorized to be built.

## Current state

Revision 5 re-read the bootstrap files at `main` =
`f27a075d3ed4ca9d70fe409af7805851aa24892c` (2026-11-21 14:30 UTC): blobs
`root-app.yaml` `8f1057cc0229`, `project-default.yaml` `4c380348bd77`,
`applicationset-apps.yaml` `4b17775eedbc`. The other citations below were
read for revision 4 at `main` = `a1e22940d2d7a89a8f640f6a90b2a80b490ab658`
(2026-11-21 10:14 UTC; the re-review observed the same HEAD). The clone is
shallow, so the cited lines were re-read at this SHA. Line numbers moved
since revision 3 (`467d6de`), and the citations below are the corrected
ones: `argocd/values.yaml` RBAC block `:174-184`, accounts `:53,59`;
`mctl-api.yaml` source 2 `:824`, automated `:889-891`;
`wft-create-tenant.yaml:1095`. Upstream Argo CD citations are at tag
`v3.3.8` (commit `7ae7d2cc723f5408b080a31263e705198af08613`). They were
re-read on 2026-11-21 via `gh api repos/argoproj/argo-cd/contents/server/application/application.go?ref=v3.3.8`.
mctl-api citations are at `main` = `2a8de33ae4494f214ddb798d4cf880de24251160`
(read for revision 3 and not re-read).

### Version governance that exists (no temporal policy)

- `platform-gitops/release-gates.yaml` has `version_holds` and `gates`. It
  has no time, window or freeze field. No `syncWindows` exist anywhere in
  `platform-gitops/bootstrap` or `platform-gitops/argocd` (re-grepped at
  `a1e2294`).
- `scripts/release-gate.py` (`check`/`verify`/`diff`/`pr-identity`): exit 6
  means refused and exit 7 means could not observe. It reads the policy from
  a git revision.
- `scripts/release-ledger-shadow.py` `judge_ledger` is a **pure read**. It
  neither reserves nor consumes anything.
- mctl-api `internal/workitems/action_approvals.go` is the existing
  single-use approval store. Its transitions:
  - `pending -> approved | denied`;
  - `approved -> consumed` (`ConsumeActionApproval`): one CAS guarded by
    state, `intent_hash`, `expires_at` and `fresh_until`;
  - `consumed -> executed`;
  - `consumed -> in_flight -> executed | consumed` (`ReserveActionApproval`
    / `SettleActionApproval`, mctl-api#772). A failed settle returns the
    grant to `consumed`.

  Requests are idempotent per `(requested_by, idempotency_key)`.
  Self-decision is refused.
- mctl-api `release_approvals.go` defines the dedicated kind `release.grant`
  (mctl-api#1022, mctl-gitops#2528), whose intent the server builds itself.
  `deploy_approvals.go:54-61`: `release.*`, `deploy.*` and `glovo.*` are
  dedicated kinds that every generic route refuses. Decisions are made on
  the MFA page (`release_decisions.go`, `release_approval_page.go`).
- `platform-gitops/argo-workflows/scripts/release-gate-guard.sh` guards gated
  groups only. It is called by `tpl-git-commit`, `tpl-validate-tenant`,
  `wft-add/remove-custom-domain`, `wft-deploy-service`,
  `wft-promote-deployment`, `wft-provision-database`,
  `wft-rollback-revision` and `wft-rollback-service`.
- `.github/workflows/release-gate-watch.yml` detects after the write.
  `.github/workflows/argocd-freshness.yml` checks resolution after a push and
  is "Not a merge gate".

### Argo CD identities and RBAC today (desired state)

- `platform-gitops/argocd/values.yaml:174-184`: `policy.default: ""` and
  `scopes: "[groups]"`. `role:admin` has `applications, *, */*`,
  `projects, *`, `repositories, *` and `exec, create`, and is bound to group
  `admins`. The break-glass path is `argocd --core` against the cluster
  kubeconfig.
- The local accounts `mctl-api` (`:53`) and `ci-freshness` (`:59`) are
  `apiKey` only, with `applications, get` and no `sync`.
- `platform-gitops/argocd/rbac/tenants/{commerce-proof,erpact,karabu,labs,mctl,namax66,redloop}.csv`
  each have `applications, sync, apps/<tenant>-*, allow` at line 4.
  `erpact.csv:12` also has `erpact/*`. Every tenant also has the restart
  actions.
  `platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml:1093-1099`
  **generates** these lines for every new tenant; the `sync` line is at
  `:1095`.
- `application.sync.requireOverridePrivilegeForRevisionSync` is **not set**
  in `argocd/values.yaml`, so at v3.3.8 it is effectively `false`. No
  principal holds `override` except `role:admin`.
- `bootstrap/templates/projects/project-apps.yaml` defines no `roles:` and no
  `syncWindows`. `project-prod.yaml` exists, but its content is the TODO noted
  in revision 3 (no production/preview split).

### Application shape (relevant to an exact pin)

- `bootstrap/templates/bootstrap/applicationset-apps.yaml`: every `apps`
  Application is **multi-source**. Source 1 is the chart
  `helm-charts/base-service` (`targetRevision` at `:38`); source 2 is a
  `ref: values` source (`:50`). Both take `.Values.spec.source.targetRevision`,
  which is `main`. `syncPolicy.automated` (`:56-58`) has prune and selfHeal.
  The ApplicationSet owns the Application spec. **No `apps` Application is
  SHA-pinned.**
- `bootstrap/templates/mctl-platform/mctl-api.yaml`: source 1 is the mctl-api
  `helm/` chart, pinned to `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361` (`:19`,
  with the #2528 rationale at `:11-18`). Source 2 is
  `infra-components/mctl-platform/mctl-api` at `main` (`:824`). Automated
  sync has prune and selfHeal (`:889-891`). The Application is in project
  `platform`. It is **partially pinned**, so it is not a G0 pilot as
  deployed.
- `bootstrap/templates/bootstrap/root-app.yaml`: project `default`, source
  `platform-gitops/bootstrap`, automated with prune and selfHeal, and a
  resource-level `Prune=false`. root-app renders every AppProject and every
  Application spec, so a pin move or a window edit takes effect only when
  root-app syncs.
- The `apps` ApplicationSet's git directory generator reads
  `platform-gitops/services/*/*` at `revision:
  {{ .Values.spec.source.targetRevision }}` (`applicationset-apps.yaml:14`),
  the same value as both sources (`:38`, `:50`). It sets
  `goTemplateOptions: ["missingkey=error"]` (`:8`) and
  `syncPolicy.preserveResourcesOnDeletion: false` (`:10`). There is no
  per-Application revision parameter. `bootstrap/values.yaml:4` sets the
  shared value to `main`.

### Bootstrap recovery chain (revision 4 review P1-1)

- `root-app` is in AppProject `default` (`root-app.yaml`, `spec.project`).
  It applies every AppProject in `bootstrap/templates/projects/`
  (`project-default`, `project-apps`, `project-platform`, `project-prod`),
  both live ApplicationSets and every bootstrap Application.
- `argocd-self-managed` (`argocd/templates/argocd-self-managed.yaml:4-11`)
  is in `default`, tracks `main` with automated selfHeal and prune `false`,
  and applies the `argocd` chart: `argocd-rbac-cm` (assembled from
  `argocd/rbac/tenants/*.csv`) and `argocd-cm`. It is not rendered by
  root-app; it manages itself.
- At `f27a075`, 26 bootstrap template files besides `root-app.yaml` set
  `project: default` (for example `core-infra/vault.yaml`,
  `core-infra/zitadel.yaml`, `core-infra/external-secrets.yaml`,
  `observability/monitoring.yaml`, `mctl-platform/mctl-portal.yaml`). Four
  files set `project: platform` (including the `tenants` ApplicationSet),
  and the `apps` ApplicationSet sets `project: apps`.
- Argo evaluates a window only against Applications of the AppProject that
  holds it (`proj.Spec.SyncWindows.Matches(a)`, `application.go:2027`). A
  window in `apps` or `platform` therefore cannot match root-app or
  argocd-self-managed **unless** one of them is moved into that project. A
  window in `default` can match them, through `applications: ["*"]`,
  `namespaces: ["argocd"]`, `clusters: ["*"]` or an exact name.
- **Consequence.** A `default` deny that matches root-app blocks root-app's
  auto-sync. A PR that removes the window can merge, but root-app cannot
  apply it until the window ends. Manual sync of root-app is also refused
  unless the deny has `manualSync: true`, and the v3.3.8 window check in
  `Sync` has no role exemption (expected; T166 verifies). The comment at
  `project-default.yaml:46-48` ("root-app can always sync a revert of this
  file") is true only while no window in `default` matches root-app. A
  `default` deny that matches argocd-self-managed similarly blocks RBAC
  changes, including the RBAC steps of the section 6.7 rollback.
- No `syncWindows` exist in the repository today (re-grepped at
  `f27a075`), so no self-lockout exists now. This is desired state only;
  the live AppProjects are `unknown` (no access).

### Argo CD v3.3.8 facts relevant to a broker (read from source at the tag)

- `server/application/application.go` `Sync` (`:2019`):
  1. It loads the Application and project, then evaluates
     `proj.Spec.SyncWindows.Matches(a).CanSync(true)` (`:2027`). A manual
     sync is blocked by an active deny unless every active deny has
     `manualSync`.
  2. It enforces `applications, sync`. Local `manifests` need `override`
     and are refused under auto-sync.
  3. `resolveSourceRevisions` (`:2136-2200`, re-read 2026-11-21). For each
     source, if the requested revision is non-empty **and differs from**
     `targetRevision` (or `HEAD`), then `override` is enforced when the flag
     is true, and on an auto-synced Application the request is refused with
     `FailedPrecondition`: "Cannot sync source %s to %s: auto-sync currently
     set to %s" for multi-source (in the loop starting `:2155`), and "Cannot
     sync to %s: auto-sync currently set to %s" for single-source (`:2191`). A requested revision **equal to**
     `targetRevision` passes. `resolveRevision` then resolves it. For a
     commit SHA, this yields that SHA.
  4. Without a revision, `targetRevision` (`main`) is resolved **at request
     time**, and the result is stored in `Operation.Sync.Revision(s)`
     together with `InitiatedBy` and the caller's `Infos`.
  5. `argo.SetAppOperation` (`:2115`) refuses if an operation is already
     running. Argo serializes one operation per Application.
- `TerminateOperation` (`:2442`) needs only `applications, sync`. A tenant
  that keeps `sync` can therefore terminate a broker operation: a denial of
  service, not a bypass.
- `GetApplicationSyncWindows` (`:2808-2831`) needs only `applications, get`.
  It returns `AssignedWindows`, `ActiveWindows` and `CanSync`, and
  **`CanSync` is `CanSync(true)`, the manual-sync answer**. With an active
  deny that has `manualSync: true`, it reports `canSync: true` even though
  auto-sync is blocked. Activation logic must read `activeWindows`, not
  `canSync` alone (R-V3).
- `Rollback` by history id is refused when auto-sync is enabled.
- `docs/user-guide/sync_windows.md` (v3.3.8): an active deny overrides an
  active allow. `manualSync: true` opens manual sync to **every** principal
  that has `sync`. There is no per-role override. argoproj/argo-cd#29558 was
  **OPEN** at the 2026-11-21 read (`gh api`, `updated_at`
  2026-09-07T21:21:04Z). No v3.3.8 hook authorizes a single sync by request
  id.
- Re-confirmed from revision 2:
  - v3.3.8 has no `syncOverrun`.
  - The `timeZone` offset is taken at `time.Now()`.
  - Auto-sync and selfHeal are gated by `CanSync(false)`.
  - An operation that is in flight when a deny opens stays `Running`
    ("Sync operation blocked by sync window").
  - A deny **suspends** auto-sync for matching Applications while it is
    active. It does not change `syncPolicy`, and auto-sync resumes at window
    end with whatever `main` holds then.
- The controller (`controller/sync.go` `SyncAppState`) renders and applies
  the operation's revisions independently of the API server. The re-review
  cross-checked this. **Consequence:** once `Sync` returns, the apply may
  already be under way. A broker check made after `Sync` returns cannot
  prevent the first apply (re-review P1-1).

### Table A: production effect paths, labelled for a window policy

Labels: `enforced`, `detected-after-write`, `not-covered`, `unknown`.

| # | Path | Changes | Pre-effect hook | Label for a future window check | Evidence |
|---|---|---|---|---|---|
| P1 | `release-deploy.yaml` (`preflight`, `ledger-gate`, `bump`, `publish-direct` env `gitops-bump`, `publish-pr`, `enqueue-bump`) | image tag/digest | in workflow, before push | candidate `enforced` at write; effect gap (section 3) | workflow file |
| P2 | `gitops-bump.yaml` | image tag/digest | yes | as P1 | workflow file |
| P3 | Human PR through the merge queue | anything | PR and `merge_group` checks | `not-covered` at effect; the check runs candidate code (section 4) | ruleset 18465404; `validate-manifests.yml` |
| P4 | `claude/*` auto-merge | anything not in `protected_re` | `validate` | as P3 | `auto-merge.yml` |
| P4b | `release-bump/*` enqueued by `scripts/release-bump-enqueue-wait.sh` | image | guard before enqueue | `not-covered` at merge/sync without an `effective` Argo deny | script header |
| P5a | CWFTs that push to `main` (`wft-deploy-service`, `wft-rollback-*`, `wft-promote-deployment`, `tpl-git-commit`) | values, including image | in template | candidate `enforced` once a hook exists | `grep -l "git push"` |
| P5c | Non-image CWFTs (`wft-create-tenant`, `wft-delete-tenant-safe`, `wft-retire-service`, `wft-add/remove-custom-domain`, `wft-provision-database`, `wft-platform-skill-*`) | namespaces, ingress, DB, removals, **tenant RBAC lines** | same | `not-covered` in an image-bump MVP | same grep; `wft-create-tenant.yaml:1095` |
| P5b/P6 | Write deploy key outside template code; mctl-agents `commit-and-push` | any path | none | `unknown`: ruleset `bypass_actors` unreadable; #2543 OPEN | ruleset read; runbook |
| P7a | `admins-mctl-api` source 1, pinned `c5e5d6f9...` | chart | the pin moves only by GitOps PR | as P3 | `mctl-api.yaml:19` |
| P7b | `admins-mctl-api` source 2 at `main` | manifests | none beyond P3 | as P3 | `mctl-api.yaml:824` |
| P7c | All `apps`/`tenants`/root Applications at `main` | everything under `platform-gitops/` | none beyond P3 | as P3 | `applicationset-apps.yaml`, `root-app.yaml` |
| P8a | Tenant manual sync | applies the current spec | Sync Windows (no `manualSync`) | `not-covered` today; `enforced` at sync start only while a deny without `manualSync` is `effective` | tenant CSVs |
| P8b | `role:admin` sync, spec edit, `projects, *`, `override` | anything | none | `not-covered` (break-glass residual) | `argocd/values.yaml:178-184` |
| P8c | `kubectl` / `argocd --core` | anything | none | `not-covered` (break-glass residual) | `argocd/values.yaml` comments |
| P8d | Tenant resource actions (`Deployment/restart`) | restarts pods | not a sync | `unknown` until T93 | tenant CSVs |
| P9/P10 | Vault values, optional Secrets | runtime config | none in git | `not-covered` | runbook |
| P12 | Required contexts bound to integration 15368 | merge-gate trust | none | `unknown`; spoofable by a same-named job | ruleset read |
| P14 | `cloudflare-apply.yml` | edge/DNS/WAF | env reviewer | `not-covered` | workflow file |
| P15 | Merged before a freeze, applied during it | as committed | Argo deny only | `not-covered` today | section 3 |
| P16 | Window merged but not yet `effective` (new) | any | none | `not-covered` for `[start, t_effective)` | section 3.1 |
| P17 | Direct `Sync` with an exfiltrated broker token (new) | the pilot app's current spec | none pre-effect | `not-covered` (detected after the fact) | section 6.6 |

### Table B: non-image GitOps writes

- `helm-charts/base-service/**`: feeds every `apps` Application.
- `helm-charts/tenant/**`: feeds every `tenant-*` Application.
- Non-`image` keys in `services/<team>/<svc>/values.yaml`.
- `bootstrap/templates/**`: Applications, AppProjects and ApplicationSets,
  including pins.
- `argocd/**`: the RBAC CSVs and `argocd-cm`.
- `argo-workflows/**`.
- `infra-components/**`.

`release-gate.py` parses none of these. The MVP name therefore stays
**"image-bump window policy (partial coverage)"**.

### Table C: GitOps path to Application to AppProject (hand-read; S0 task 4 regenerates it from a render)

| GitOps path | Application | AppProject | Destination ns | Pinned? |
|---|---|---|---|---|
| `services/<team>/<svc>/` + `helm-charts/base-service/` | `<team>-<svc>` (multi-source, auto-sync) | `apps` | `<team>` | no (both `main`) |
| `tenants/<t>/` + `helm-charts/tenant/` | `tenant-<t>` | `platform` | tenant chart | no |
| `bootstrap/templates/mctl-platform/mctl-api.yaml` + `infra-components/mctl-platform/mctl-api` | `admins-mctl-api` | `platform` | admins | source 1 only |
| `bootstrap/templates/erpact/applications.yaml` | `erpact-*` | `erpact` | erpact | not re-read |
| `bootstrap/**` (including AppProjects) | `root-app` (recovery chain) | `default` | argocd | no |
| `argocd/**` | `argocd-self-managed` (recovery chain) | `default` | argocd | no |
| `bootstrap/templates/{core-infra,data,observability,mctl-platform,system}/*` (26 files) | platform Applications | `default` | various | mixed; not re-read per file |

Application names are hyphen-joined (`<team>-<svc>`), so wildcards are
unsafe and only exact names are used (R-M2). AppProjects and RBAC are applied
by two different Applications (`root-app` and `argocd-self-managed`), so
their effect order is independent of commit order (R-R4).

### Timing

- #970 (closed 2026-09-02) reported about 7 min. A push webhook,
  `--revision-cache-expiration=30s` and a 180 s poll have been added since.
  The figure is stale until measured.
- Merge queue: `check_response_timeout_minutes: 120`, one entry per build
  and merge, method `MERGE`.
- `main` receives frequent bot commits under `agents-state/` and image
  bumps; the HEAD commit is itself a bump (`a1e2294 chore: bump
  labs/agent-worker-managed-preview`). An approved GitOps SHA is therefore
  almost never `main` HEAD by the time a sync runs.

Deployed state checked:
- Revision 5: `git log -1` on the clone: `f27a075d...` (2026-11-21 14:30
  UTC, an image bump). Re-read `root-app.yaml`, `project-default.yaml`,
  `applicationset-apps.yaml`, `applicationset-tenants.yaml`,
  `project-apps.yaml`, `argocd/templates/argocd-self-managed.yaml` and
  `bootstrap/values.yaml`. `grep -rln "project: default"
  platform-gitops/bootstrap/templates` gave 27 files including root-app.
  `grep -rn syncWindows platform-gitops`: no hits.
- Revision 5: `mctl_whoami` re-run 2026-11-21: `agent:issue-investigator`,
  Admin false, Teams [], no namespaces. Live AppProjects, live Applications
  in `default` and the live Argo version remain `unknown`.
- Revision 5: `gh api .../issues/comments/7064106704` (the revision 4
  review) was read in full and is the input for revision 5.
- Revision 4: `git log -1` on the clone: `a1e22940...` (2026-11-21 10:14 UTC). The clone
  is shallow, so `467d6de` cannot be resolved for a diff, and the cited
  lines were re-read directly instead.
- `grep syncWindows|freeze` over `platform-gitops/bootstrap`,
  `platform-gitops/argocd` and `release-gates.yaml`: no `syncWindows`. The
  only "freeze" hits are an unrelated SLO merge-freeze comment
  (`observability/monitoring.yaml:27,32,862`) and a `release-gates.yaml:28`
  comment.
- `$MCTL_GITOPS_ROOT/services/*` and `tenants/*` were listed for revision 3.
  This is desired state only. Tenants with services: admins, karabu, labs,
  namax66, redloop.
- `mctl_whoami` (revision 3, 2026-11-20): `agent:issue-investigator`, Admin
  false, Teams [], no namespaces. Not re-run; still assumed non-admin.
- `mctl_get_service_status admins/mctl-api` (revision 3): "ArgoCD
  application not found". Recorded as **no access, not absence**. The live
  Argo CD version, AppProjects, `argocd-cm` and RBAC are `unknown`.
- `gh issue view 2828` comments: the 2026-11-21 re-review was read in full
  and is the input for revision 4.
- `gh api` argoproj/argo-cd#29558: open, `updated_at` 2026-09-07T21:21:04Z.
- Upstream v3.3.8 `server/application/application.go` was re-read
  (`Sync`, `resolveSourceRevisions`, `TerminateOperation`,
  `GetApplicationSyncWindows`). `controller/sync.go` was not re-read by this
  investigator; it is taken from the re-review and marked for S0 task 6
  re-verification.
- From revision 3, not re-run: the mctl-api `2a8de33` files, the ruleset
  18465404 read, vendor docs.

## Proposed solution

S0 produces evidence, an offline model, a local inert harness and inert
prototypes. It does **not** produce a running system.

### 1. S0 deliverables and exit gate

1. `docs/spikes/2828-release-calendar/inventory.md`: tables A-C
   re-verified, plus the live Argo version, `argocd-cm` and RBAC, read
   read-only by the owner, or `unknown`.
2. `tests/research/release_calendar_s0/model.py`: the pure policy function
   (section 2) and the activation-state function (section 3.1). Run only by
   hand, with `python3 -I`.
3. `tests/research/release_calendar_s0/argo-inert/`: a kind/k3d harness with
   Argo CD **v3.3.8** (chart `argo-cd` 9.5.9) and a local git server. It
   holds dummy Applications shaped like MCTL's: multi-source,
   AppSet-generated, tracking `main`. It adds **one fully SHA-pinned
   multi-source pilot** for the G0 tests (reached through each pin
   mechanism of 6.3.1 in turn), a root-app-like parent Application **in its
   own `default`-like AppProject** that renders AppProjects and Application
   specs, a self-managed RBAC Application in the same project, and RBAC
   copied from `rbac/tenants/labs.csv`. The ApplicationSet is a copy of
   `applicationset-apps.yaml` with `preserveResourcesOnDeletion: false`
   kept, so that the deletion risk of 6.3.1 is real in the harness.
4. `tests/research/release_calendar_s0/broker-model/`: an inert broker
   prototype (section 6). It talks only to the harness Argo CD and to a local
   Postgres holding a copy of the `action_approval_requests` schema, the
   proposed `release_exception_ops` table and the CAS statements.
5. `tests/research/release_calendar_s0/mcp-model/`: an offline model of the
   two PR-authoring operations (section 8) against a throwaway local git
   repo. It never runs against GitHub.
6. `docs/spikes/2828-release-calendar/decision.md`: the section 9 matrix
   refreshed with results, one calendar outcome, one exception-path outcome,
   residual risks, and follow-ups mapped to existing issues.
7. Exit gate: an independent review of the memo, then an owner decision on
   #2828. S1 needs a new proposal. Any Argo RBAC, AppProject, window, pin,
   secret, account, flag, MCP tool or production change needs a separate
   owner **security** GO.

### 2. Policy model (illustrative schema, fixtures only)

```yaml
# tests/fixtures/release-calendar-s0/policy-example.yaml (illustrative; not a real freeze)
version: 1
default: allow
max_window: 21d
margins: {sync_start: 5m}                 # placeholder until S0 task 3 measures it
activation: {lead: 30m, max_read_age: 60s} # placeholders (section 3.1)
scopes:
  platform-api: {applications: [admins-mctl-api]}
  labs-bot:     {applications: [labs-mctl-telegram]}
windows:
  - id: w-7f3a9c                         # derived: sha256(scope|kind|schedule|zone)[:6]
    name: example-weekend-freeze
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    zone: Europe/Berlin
    recur: {freq: weekly, byday: [FR]}
    start_local: "16:00"
    end_local: {day_offset: 3, time: "08:00"}
    exception_path: none                 # broker only if S0 concludes BROKER_PINNED_PILOT_CANDIDATE
  - id: w-1c04de
    name: example-year-end
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    start_utc: "2026-12-24T00:00:00Z"
    end_utc:   "2027-01-02T00:00:00Z"
    exception_path: none
```

Truth table (per Application, interval `I = [t_check, t_effect_max]`, the
first matching row wins). It is unchanged from revision 2 and equals
`CanSync(false)` except for row 0:

| # | Condition | Result | Argo 3.3.8 `CanSync(false)` |
|---|---|---|---|
| 0 | policy unreadable or invalid | `UNKNOWN` | error → blocked |
| 1 | no window matches | `default` (`ALLOW`) | allow |
| 2 | a matching deny is active in `I` | `DENY` | deny |
| 3 | allows match and `I` lies inside them | `ALLOW` | allow |
| 4 | allows match, otherwise | `DENY` | deny |
| 5 | only denies match, none active | `ALLOW` | allow |

Time semantics (unchanged):

- Occurrences are wall-clock local times in an IANA zone, computed with
  `zoneinfo`.
- An absolute `duration` is allowed only for `UTC` windows and UTC
  one-offs.
- Windows are half-open: `[start, end)`.
- A spring-forward gap moves to the first instant after it.
- A fall-back ambiguity widens deny windows and narrows allow windows.
- Example: Fri 16:00 to Mon 08:00 Europe/Berlin is 64 h normally, 65 h
  across fall-back and 63 h across spring-forward.
- Recurrence subset: daily, weekly or monthly, with `byday` (no ordinals)
  and `bymonthday`, and no `COUNT` or `UNTIL`. Anything else is `UNKNOWN`.

#### 2.1 Deny-only MVP (revision 4 review P2-3)

The truth table keeps rows 3 and 4 so that the model mirrors Argo
`CanSync(false)` and can classify a hand-written allow. The MVP **emits and
accepts no allow window** (R-N1):

- the canonical policy validator refuses `kind: allow` (T183);
- the projection generator has no allow output;
- `mctl_propose_release_window` accepts `kind: deny` only (section 8.2);
- the rendered-AppProject scan (section 3.2) refuses a `kind: allow` that a
  human PR writes directly into `bootstrap/templates/projects/*.yaml`
  (T184).

Why allow is not "just another window": on v3.3.8, once **any** allow
matches an Application, that Application is denied at every instant at
which no matching allow is active (row 4). Adding an allow that is inactive
now freezes the matched Applications now. An allow whose selector drifts
to an extra Application freezes that one too. Those effects are outside the
interval the author wrote, and the deny-weakening checks of revision 4
(R-I5, T145) do not see them.

A later proposal that re-admits allow must bring, separately from deny
(R-N4):

1. An **effective-policy diff**. The S0 simulator
   (`model.py effective-diff`, offline) evaluates base and candidate per
   matched Application over a horizon (default 35 days) and lists every
   boundary instant where the decision changes, inside and outside the
   allow interval.
2. A **blast radius** from the rendered match set (section 3.2), not from
   the intended scope.
3. A recovery-chain check (R-L3).
4. An owner approval.
5. Negative fixtures: an inactive allow, allow plus deny, a drifted
   selector and a cross-midnight allow.

S0 measures on the harness, in the target AppProject (T180-T182): an
inactive allow alone blocks auto-sync immediately; a concurrent allow plus
deny gives deny; a drifted allow selector freezes the extra Application.
Each result is compared with the model.

### 3. Merge queue and point of effect

There are four instants: `t_check`, `t_merge`, `t_sync_start` and
`t_sync_end`.

- Direct-push writers can re-check seconds before the push.
- Queued PRs can merge up to 120 min after their check. So **no PR or queue
  path is `enforced` at the point of effect** unless an `effective` Argo
  deny covers the target Application.
- With an `effective` deny and no `manualSync`, a commit merged before the
  freeze is applied at window end.
- A multi-wave sync that is in flight when the window opens pauses,
  partially applied.

Fixtures T20-T25 are unchanged from revision 2.

#### 3.1 Window activation lifecycle (re-review P1-2)

A merged window is desired state. Argo enforces only the live AppProject that
root-app has applied. Activation is therefore an **observed** state, computed
per (window, intended Application):

| State | Required evidence (all fresh, each read within `max_read_age`) |
|---|---|
| `proposed` | The PR is open and adds the window (base-pinned validator passed) |
| `merged` | The window is in the policy at `main` SHA S |
| `reconciling` | root-app `status.sync.revision` does not yet contain S, **or** the live AppProject `spec.syncWindows` hash differs from the projection rendered at S |
| `armed` | The live AppProject window hash equals the projection at S; `GetApplicationSyncWindows(app).assignedWindows` contains the window for every intended Application and for no unintended one (an exact match test against Table C); time is before `start` |
| `effective` | `armed`, and `start <= now < end`, and `activeWindows` contains the deny. For an exception design, `canSync` (manual) also equals the intended `manualSync` |
| `expired` | `now >= end`, and the projection has been removed (or never recurs) |
| `drifted` | Live and desired disagree after `reconciling` exceeded its SLA; or a yearly-cron projection of a one-off is still present after `end`; or an unintended Application is matched |
| `self-locked` | A live window matches a recovery-chain Application (section 3.2). It takes precedence over `drifted` and `reconciling`, and is reported as "not recoverable via GitOps" |
| `unknown` | Any read returned 403, a timeout or an error, or is older than `max_read_age` |

Rules:

- `unknown` never reports `effective`.
- The coverage gap `[start, t_effective)` is reported `not-covered` for the
  affected Applications (P16).
- If a window is not `armed` at `start - activation.lead`, an **activation
  SLA missed** alert fires.

Operator instructions when the activation SLA is missed (design only):

1. Announce that the freeze is **not in force**.
2. Hold human-initiated deploy writes by the existing release-gate holds
   where they apply.
3. Escalate to an admin to inspect root-app sync. The admin action is
   break-glass and recorded.
4. Never treat the merge as a successful emergency freeze.

Observation needs `applications, get` for `GetApplicationSyncWindows`, which
mctl-api's account already has. A live AppProject read may need
`projects, get`. That is `unknown`, and any new permission is S3.

Cases S0 fixtures cover (T110-T117):

- A window merged at T-1m, with root-app syncing at T+4m, so `effective`
  starts at T+4m and `[T, T+4m)` is `not-covered`.
- A pre-scheduled window whose start passes while root-app is degraded.
- Removal of an expired one-off, and a missing removal producing `drifted`
  on next year's recurrence.
- An Argo application-controller restart while a window is active (the
  window is still enforced on the next reconcile; recorded).
- A changed selector that drops an intended Application, or adds an
  unintended one.
- A 403 or stale read giving `unknown`.

#### 3.2 Bootstrap self-lockout guard and recoverability (revision 4 review P1-1)

Invariant (replaces revision 4's R-A9): **no sync window, from any author,
may match an Application in the recovery chain**. The chain has two
required members, `root-app` and `argocd-self-managed`; S0 task 4
enumerates further dependencies. The MVP rule is stricter and simpler:
**no window at all in AppProject `default`** (R-L2). That covers both
members and every other platform Application in `default`, without having
to prove the chain complete first.

The check is a **rendered match**, not a reading of the policy's intended
scope (R-L3):

1. Render `platform-gitops/bootstrap` with `bootstrap/values.yaml` at the
   candidate commit (as `scripts/validate-argocd-project-scope.py` already
   renders this chart and the argocd chart for project scope).
2. Add `argocd-self-managed` from the argocd chart render.
3. Expand the ApplicationSet generators offline: the `apps` directory
   generator over `services/*/*` and the `tenants` generator, both at the
   candidate tree.
4. For every AppProject in the render and every window in it, compute the
   match set with v3.3.8 semantics: glob over `applications`, `namespaces`
   and `clusters`; OR across them by default, AND with `andOperator`;
   evaluated only against Applications whose `spec.project` is that
   AppProject.
5. Refuse when the window is in `default` (R-L2), when the match set
   intersects the recovery chain (R-L3), or when the window has
   `kind: allow` (R-N1).
6. Run the same computation on base and candidate, so that a change that
   **moves** an Application (a `project` edit, an AppProject rename, a new
   Application in `default`, a widened selector) is refused even when no
   window text changed (R-L4).

Where it runs (all from the base, R-T1): the canonical policy validator;
the projection generator; the `mctl_propose_release_window` model
(section 8.2); and a scan of rendered AppProjects for **hand-written**
`syncWindows`, so that a human PR to `project-*.yaml` is caught too
(R-L5). In S0 all four are offline fixtures. Wiring any of them into CI is
S1.

Positive control (R-L8, T162). With an `effective` deny in `apps` that
matches a pilot, root-app is not matched (a different project), so it
still applies a reviewed revert of the window. argocd-self-managed still
applies a reviewed RBAC change. Both are measured on the harness.

Existing self-lockout (R-L6, T165). If the live state shows a window that
matches a recovery-chain Application (injected on the harness, for example
by an admin `kubectl edit` of the `default` AppProject), the status is
`self-locked`: "not recoverable via GitOps". It is not `drifted` or
`reconciling`, because waiting for reconciliation cannot fix it. An alert
fires.

Break-glass recovery, walked on the harness only (R-L7, T166-T167):

1. Declare an incident and record who acts.
2. Merge the revert of the window to `main` through the normal reviewed
   path. root-app cannot apply it yet.
3. As admin, try `argocd app sync root-app` and record the result. The
   expected result is a refusal by the window (no role exemption), unless
   the deny has `manualSync: true`.
4. As cluster admin, `kubectl edit appproject default` and delete the
   window from the live object only.
5. root-app's auto-sync resumes and applies `main`, which no longer holds
   the window. **The order matters.** If step 4 runs before step 2,
   root-app's selfHeal re-applies the window from `main` and locks itself
   again (T167, a negative case).
6. Verify that the activation state is no longer `self-locked`, and attach
   the audit trail (the Kubernetes audit entry for the edit, the admin
   identity, the PR, the root-app sync revision) to the incident.

The `project-default.yaml:46-48` comment is accurate only while this
invariant holds. Correcting it is a follow-up (R-L9).

### 4. Trust boundary

`validate-manifests.yml` runs `scripts/release-gate.py` from the PR
merge-ref checkout, and reads only the policy from `HEAD^1`. Any evaluator,
including the MCP PR validator (section 8), must take its code and policy
from the base commit, and run with `python3 -I` from a directory that holds
no candidate files. Integration-15368 contexts are not trusted enforcement
(P12), and `protected_re` is not a trust boundary. The broker reads its
policy, Application map and intent from mctl-api and from a pinned base
revision only (R-G10). Fixtures T70-T74 are unchanged.

### 5. Grant lifecycle (shared by every exception path)

Authority stays with a human on the existing mctl-api MFA decide page.

**Reused from mctl-api, adding no new authority:**

- the `action_approval_requests` table and its CAS discipline;
- the dedicated-kind namespace (`release.*` is already dedicated);
- the server-built intent pattern of `release.grant`;
- `fresh_until` and `expires_at`;
- the refusal of self-decision;
- idempotency per `(requested_by, idempotency_key)`;
- the MFA release decide page.

**New, needing its own proposal and an mctl-api owner GO:**

- the dedicated kind `release.freeze_exception`, with the states
  `approved -> claimed -> sync_requested -> executed | spent_failed |
  spent_unknown`. None of them returns to `approved` or `consumed`. The kind
  does **not** reuse `SettleActionApproval(succeeded=false)`.
- the table `release_exception_ops`, written in the same transaction as the
  CAS (section 6.5).

**Intent (server-built).** The intent binds:

- kind, AppProject, Application name and namespace, tenant and environment;
- the approved GitOps SHA;
- every source's revision (for a G0 pilot, the pinned SHAs);
- the SHA-256 of the rendered manifests at those revisions;
- the live Application spec digest;
- the image repository and `sha256` digest(s);
- the diff against live;
- the reason class (`hotfix`, or `rollback` with the `dep_` id);
- the requester, `not_after` and a nonce.

A client field that the server's own read does not reproduce is refused
(T86). A version hold, gate group, ledger requirement or `min_tag` still
refuses (R-X8).

### 6. MCTL Governed Sync Broker (first-class alternative; S0 builds an inert prototype only)

#### 6.0 Guarantee classes (re-review P1-1)

| Class | Meaning | Where it can come from on v3.3.8 |
|---|---|---|
| G0 | Before any apply, Argo refuses any revision other than the approved immutable SHAs | Broker `Sync` with `revisions` equal to every source's **SHA-pinned** `targetRevision` (`resolveSourceRevisions` `:2155-2166`) |
| G1 | Checked before the request; content can still diverge before the effect | Preflight only, with no pin |
| G2 | Divergence detected after the operation exists, then terminated; partial unauthorized apply is possible | Broker on an Application tracking `main`: post-`Sync` revision/hash check plus `TerminateOperation` |
| none | No check | E1, a tenant sync under `manualSync: true` |

The revision 3 broker on `apps` Applications is **G2**. Its "exactly one
approved release: yes" is withdrawn. T104 is the adversarial schedule that
demonstrates it: approved hash A → preflight A → `main` moves to B → `Sync`
resolves B → the controller applies B → the broker terminates. The expected
outcome is partial or full apply of B before terminate, **recorded as a
failure of single-release semantics**.

#### 6.1 Shape

The broker is a small trusted process, **separate from agent pods and agent
worktrees**. It owns the only non-break-glass Argo identity allowed to sync a
frozen pilot Application. In S0 it exists only as `broker-model/` against the
harness. For an eventual production boundary (not authorized), the memo
compares two placements:

- **(i) a separate Deployment in `admins`** (the default candidate). It has
  its own ServiceAccount; its token is delivered by ExternalSecret from a
  Vault path that no agent role reads; and a NetworkPolicy allows only
  mctl-api → broker and broker → `argocd-server`. The broker accepts only a
  grant id from callers.
- **(ii) inside mctl-api.** This puts the sync token in a process that
  agents reach through MCP, which widens the blast radius.

Argo identity options, compared on the harness:

- a project-scoped role on the pilot AppProject, with a short-TTL JWT;
- a local `apiKey` account.

In both cases the grant is `applications, sync` and `get` on
`<project>/<exact app>` only. Both are evaluated with
`requireOverridePrivilegeForRevisionSync: "true"` as defence in depth.

#### 6.2 Flow (one grant, one sync)

1. **Intent.** The hotfix or rollback lands on `main` through the normal
   guarded path. For a G0 pilot, the reviewed PR **moves the pin(s)** to the
   approved SHA(s), and root-app applies the new spec. The deny window still
   holds auto-sync. A requester asks mctl-api for a
   `release.freeze_exception`. mctl-api, using the broker's trusted render at
   the named SHA, builds the intent.
2. **Decision.** A human approves on the MFA decide page. A separate
   `release.grant` is still required where one applies.
3. **Preflight (no side effect).** The broker re-reads:
   - the window activation state (it must be `effective`, section 3.1);
   - the live Application spec digest, and for G0 that every source's
     `targetRevision` equals the bound SHA;
   - the rendered manifest hash;
   - the image digests;
   - holds;
   - that no operation is running.

   Any mismatch → refuse. The grant stays `approved`.
4. **Claim (one transaction, section 6.5).** `approved → claimed` together
   with the insert into `release_exception_ops`.
5. **Commit intent to call.** `claimed → sync_requested(op_id, epoch,
   deadline)` is committed durably.
6. **Sync, at most once.** For a G0 pilot, `Sync(revisions=[pinned SHAs],
   sourcePositions=[1..n], prune/options = the Application's own, infos=
   [mctl-release-exception=<aar_id>/<op_id>])`. If root-app moved a pin in
   the meantime, Argo refuses with `FailedPrecondition` **before any
   apply**, and the grant becomes `spent_failed` with no effect. For a
   main-tracking Application (G2), the call is made without revisions.
7. **Observe (G2 detection also for G0).** The broker reads
   `operation.sync.revisions` and compares them with the bound revisions and
   manifest hash. On a mismatch it calls `TerminateOperation`, records the
   grant as `spent_failed` and records any partial apply. For G0, a
   mismatch here is a protocol violation that S0 must never observe (T101).
8. **Reconcile.** The broker polls `status.operationState` and matches it by
   `initiatedBy` (the broker account) and `info`. It ends in `executed` or
   `spent_failed`, or after the deadline in `spent_unknown` (R-J7).
9. **Window unchanged.** The broker never edits the AppProject, the
   Application spec or RBAC.

#### 6.3 G0 versus G2, and what S0 must prove

- **G0 requires every source to be SHA-pinned.** No MCTL Application meets
  that today (Table C). A pilot would need a later, separately approved S3
  change that pins its sources. Its normal deployment flow would then become
  "move the pin by PR", like `admins-mctl-api` source 1 today. S0 tests this
  only on the harness pilot.
- **What G0 closes.** Under G0, a pin move between preflight and `Sync` is
  refused by Argo itself (T100). A `main` commit to the pilot's paths does
  not change what a pinned source resolves to (T102).
- **What G0 does not close.** v3.3.8 `Sync` reads the Application and then
  calls `SetAppOperation`. A concurrent root-app update of non-revision spec
  fields (path, helm parameters, `syncOptions`) could reach the controller
  together with the approved revisions. This is `unknown` until T103
  measures it. If T103 shows that such a change can be applied, G0 is
  downgraded to G1 for spec fields, and the memo must say so.
- **Pin mechanism.** See 6.3.1. The shared value cannot be used.
- **Shared charts and AppSet updates.** For a G0 pilot, a shared-chart change
  takes effect only through a reviewed pin move. For main-tracking `apps`
  Applications, a `helm-charts/base-service` change re-renders every
  Application (R-M4) and is a G2 divergence.
- **Non-HEAD revisions.** For G0, syncing a non-HEAD commit is the normal
  case: the pin names a commit, and `main` HEAD is irrelevant. For G2, the
  broker binds content (the manifest hash at the resolved revisions), and an
  unrelated commit with an equal hash is accepted (T87).
- **Rollback.** A pin move (G0), or a forward restore commit (G2), to a
  `dep_` recorded as healthy, under its own grant. The history `Rollback` API
  is not used.
- **Diff basis.** The intent diff is computed between the reviewed base
  render and the **current destination live state**, not between two git
  commits. Drift in live state therefore appears in the approved diff.

#### 6.3.1 Per-Application pin migration for the deployed ApplicationSet (revision 4 review P2-2)

Today every `apps` Application gets both `targetRevision` values from
`.Values.spec.source.targetRevision`, and the generator reads directories at
the same value (`applicationset-apps.yaml:14,38,50`). **Changing that value
is forbidden as a pilot pin** (R-PM1). It would pin the generator, every
`apps` Application, root-app, the `tenants` ApplicationSet and every
bootstrap Application to one commit, and it would stop all deploys.

S0 evaluates three per-Application mechanisms on the harness. It renders
them offline against a copy of the deployed ApplicationSet and applies none
of them to the repository:

| Mechanism | Shape | Ownership | Main risk to test |
|---|---|---|---|
| M1 merge generator | `merge` of the existing directory generator with a `list` (or git files) generator keyed on `path.path`, which carries `chartRevision`/`valuesRevision` for the pilot only. The template uses an explicit default (for example `{{ dig "chartRevision" "<shared>" . }}`) because of `missingkey=error` | `apps` ApplicationSet, unchanged | The generator of **every** `apps` Application changes. Non-pilot output must be byte-equal (T170). The generator `revision` must stay `main` (T172) |
| M2 git files generator | Replace the directory generator by a git files generator over `services/*/*/release-pin.yaml` (or an optional key), with the same `path` parameters | `apps` ApplicationSet | Parameter names change (`path` vs `path.path` segments); a mis-mapped name renames an Application, which is a delete plus a create under `preserveResourcesOnDeletion: false` (T171) |
| M3 isolation | Exclude the pilot directory from the `apps` generator (`exclude: true`) and declare a standalone Application in `bootstrap/templates/` with SHA-pinned sources, like `mctl-platform/mctl-api.yaml` | root-app (a new single owner) | Excluding the directory makes the ApplicationSet **delete** the generated Application, and with `preserveResourcesOnDeletion: false` its resources go too. A safe handoff needs one of: the standalone Application lands first under the same name, and the ApplicationSet controller is shown not to delete an Application it no longer owns; or a temporary `applicationsSync: create-update` policy. Both are `unknown` until T173 |

For each mechanism S0 shows (T170-T177):

1. Every non-pilot generated Application is byte-equal after normalization
   (drop `status`, `metadata.resourceVersion`, `generation` and
   `managedFields`) to its pre-migration spec: name, project, sources,
   paths, `helm.valueFiles`, annotations (including
   `manifest-generate-paths`), `syncPolicy` and `ignoreDifferences`.
2. No Application `metadata.uid` changes, and no pilot resource uid
   changes: nothing is pruned or recreated.
3. The pilot differs only in its two `targetRevision` values. The
   generator `revision` stays `main`.
4. The reverse migration restores the pre-migration output byte-equal,
   again with no deletion.
5. A mutation test that "pins" by editing the shared value makes check 1
   fail for every Application, which proves the check detects it.

If no mechanism passes, the memo records "no safe per-Application pin", G0
is unavailable, and `BROKER_PINNED_PILOT_CANDIDATE` cannot be concluded
(R-PM7). For any passing mechanism the memo records the cost: the pilot's
image bumps from `release-deploy.yaml`/`gitops-bump.yaml` change the
values file on `main` but take effect only after a reviewed pin move,
which is a `bootstrap/**` write (Table B). The pin move itself goes through
root-app, which is why the recovery-chain invariant (3.2) is a precondition
of G0 too.

#### 6.4 RBAC isolation for frozen Applications

- With `deny` and `manualSync: true`, every principal holding `sync` can sync
  the Application. The owning tenant's role must lose `sync` on that exact
  Application, through an explicit RBAC deny line or a narrowed pattern.
  `wft-create-tenant.yaml:1095` must stop regenerating the broad line for it
  (a later S3 change). The harness tests both forms (T90).
- A tenant that keeps `sync` can also `TerminateOperation` a broker sync
  (`:2442`). If tenant `sync` is revoked, that denial of service goes away
  too.
- `role:admin` and `kubectl`/`argocd --core` are **explicit break-glass
  residuals** (T99).

#### 6.5 Journal and claim protocol (re-review P2-7)

There is one authoritative store, the mctl-api database. Any broker-local
file is a cache only.

```
approved --[TX1: CAS state+intent_hash+expiry+fresh_until; INSERT release_exception_ops(aar_id UNIQUE, op_id, epoch)]--> claimed
claimed  --[TX2: UPDATE ... WHERE epoch=$mine AND state='claimed' SET state='sync_requested', deadline]--> sync_requested
sync_requested --(single Sync call by the TX2 writer, only if now < deadline)--> observe
observe  --> executed | spent_failed | spent_unknown   (all terminal; never back to approved/consumed)
```

The broker takes a lease row (`broker_lease(epoch)`) with a TTL. A takeover
increments the epoch, and every transition is conditional on the epoch.
After a takeover, the new instance may continue an op in state `claimed`
(the same `op_id`). It may **only observe** an op in state
`sync_requested`. A stale instance that resumes after losing its lease fails
its next conditional write. It may still issue its one `Sync` if it had
already committed TX2. That is still only one call, because no other
instance ever calls for that grant. The `deadline` check bounds how late
that call can be.

Crash matrix (T120-T129):

| Crash or failure point | Durable state | Recovery | End state |
|---|---|---|---|
| Before TX1 commits | `approved` | none needed | grant reusable by the same request only (nothing claimed) |
| TX1 serialization conflict (two writers) | one `claimed` | the loser is refused | the winner continues |
| After TX1, before TX2 | `claimed` | new epoch, same `op_id`, re-preflight | proceeds or `spent_failed` (never `approved`) |
| After TX2, before the `Sync` call is sent | `sync_requested` | observe only; no operation found by the deadline | `spent_unknown` with evidence (R-J7) |
| `Sync` sent, response lost or timeout | `sync_requested` | observe by `initiatedBy` + `info` | `executed` / `spent_failed` / `spent_unknown` |
| `Sync` refused by Argo (`FailedPrecondition`, window, RBAC) | `sync_requested` | the refusal is recorded | `spent_failed`, no effect |
| Operation found, result `Failed`/`Error` | `sync_requested` | recorded | `spent_failed` |
| Two operations carrying the same `info`, or an operation with `info` and no row | any | alert | `spent_unknown`, human review |
| Stale instance writes after a takeover | any | the conditional write fails | no change |
| mctl-api DB unavailable | unchanged | the broker refuses to start any step | no sync |

The `info` value is correlation only: anyone with `sync` can set any
`info`. Authorization is the claimed row plus the broker account in
`initiatedBy`.

#### 6.6 Token-compromise boundary (re-review P1-3)

A holder of the broker's Argo token can call `Sync` directly. While a
`manualSync: true` deny is active, Argo accepts the call with **no grant**,
because Argo knows nothing about the ledger. This is an **unenforced
boundary** (P17):

- For a G0 pilot, the attacker can apply the currently pinned revisions.
  Those are reviewed commits, but they reach production unapproved for the
  freeze.
- For G2, the attacker can apply the current `main` render.
- `override`, arbitrary revisions, spec edits and non-pilot Applications stay
  refused.
- The detector (a pilot sync whose `initiatedBy` and `info` do not match a
  `sync_requested` row) is **post-effect**.

Constraints S0 evaluates:

- the shortest workable project-role JWT TTL;
- who mints the JWT (minting needs `projects, update`, so the minter becomes
  a higher-value target, and that is recorded);
- a Vault path that no agent policy reads;
- the token never present in agent worktrees or MCP processes.

A NetworkPolicy is **not** counted as proof that the token cannot be used
elsewhere: the token is a bearer credential valid at `argocd-server` from
any reachable client. T105 performs the direct sync without a grant and
expects **success**. T106 checks that the detector fires and is labelled
post-effect.

#### 6.7 Phase transitions and rollback ordering (re-review P1-4)

The state is the triple (window W ∈ {none, deny-mS:false, deny-mS:true},
tenant `sync` on the pilot T ∈ {present, revoked}, broker identity
B ∈ {present, absent}):

| W | T present | T revoked |
|---|---|---|
| none | safe (normal) | safe (tenant UX cost) |
| deny-mS:false | safe; the broker cannot sync either (D behaviour) | safe |
| deny-mS:true | **UNSAFE**: any tenant can sync during the freeze | safe; the broker is the only non-admin sync path if B is present |

- **Rollout order.** Revoke T and verify it (tenant `can-i sync` is refused
  on the harness). Then add B and verify it. Then set W to deny-mS:true and
  verify it is `effective` (section 3.1).
- **Rollback order.** Set W to deny-mS:false and verify it `effective`
  (`canSync` false for manual), or end the freeze under its own approved
  procedure and verify that the window is gone. Then remove B. Then restore
  T.
- **On a verification failure** at any step, stay at the last verified
  state, alert, and do not continue.

RBAC changes go through `argocd-self-managed` and window changes through
`root-app`. Both are in AppProject `default`, so the rollback order is
executable through GitOps only because no window may exist in `default`
(3.2). A self-lockout would turn every rollback step into break-glass. They are separate commits that are each **observed** before the
next one is merged. Commit order alone proves nothing (R-R4). Revision 3's
rollback ("restore tenant RBAC, then remove the window") passed through the
unsafe cell and is withdrawn. T96 and T130-T133 test every edge.

#### 6.8 Argo resource hooks: a hypothesis only

A PreSync hook Job that verifies the operation's revisions against a claimed
grant before the Sync phase starts would be a pre-effect check inside Argo.
It is labelled **`unknown`, and weak by construction**, because the hook is
part of the content being verified: content B can omit it. The hook would
also need ledger credentials inside the tenant namespace. S0 records the
idea, with the reason it is not a G0 mechanism. It is not prototyped unless
the memo finds a source-independent placement, and none is known at v3.3.8.

#### 6.9 Default deny and recoverability

The following lead to **no new authorized sync**, with the window unchanged:

- no grant;
- mctl-api unreachable;
- policy unreadable;
- window not `effective`;
- changed manifest or spec;
- unknown outcome;
- broker down;
- Argo down.

Recovery when the broker is unavailable is the documented admin break-glass,
recorded and reviewed afterwards. Automation never edits the window. No
persistent bypass exists, because the broker never edits the window, RBAC or
spec. One exception remains: the token-compromise boundary (6.6), which is a
residual and is not a fail-open of the design.

### 7. Other exception paths (compared, not preferred)

- **E1, GitOps carve-out.** Regenerate the AppProject without the
  Application, let auto-sync apply `main`, then restore the window. It
  **fails open**: a failed restore leaves the Application unprotected. Its
  guarantee is `none`. Kept as a baseline (T97).
- **E2, RBAC-restricted `manualSync`.** Deny with `manualSync: true`, tenant
  `sync` removed, and a human role syncs by hand. It is fail-closed at Argo
  but has no grant binding, so the role holder is the de facto authority. Its
  guarantee is `none` with respect to the ledger. **The broker is E2 plus a
  grant-bound, journaled, single-call caller.** A role-held human can also
  pass pinned revisions, so E2 on a pinned pilot gets G0 *revision*
  pinning, but still without a grant.
- **B (issue), temporary per-Application window exception.** The same
  mechanism as E1, with a TTL. It inherits E1's fail-open behaviour.
- **C (issue), upstream, fork or proxy.** No v3.3.8 hook exists, and #29558
  is open. A proxy does not cover UI, CLI or admin paths. Recorded with cost
  only.
- **D, no runtime exception.** An immutable deny with `manualSync: false`. A
  hotfix is an admin break-glass with an incident record. Simplest, and
  fail-closed for non-admins.

### 8. Operator and agent interface and status contract (design only; re-review P2-5, P2-6, P3-8)

No tool is implemented in S0. `mcp-model/` is an offline model only.

#### 8.1 Tools

| Tool | Effect | Never |
|---|---|---|
| `list_release_windows`, `check_release_window`, `explain_release_block` | read-only; return the 8.3 contract | write anything |
| `request_exception` | creates a **pending** `release.freeze_exception` request in mctl-api | decide, claim or call the broker |
| `mctl_propose_release_window` | opens a GitOps PR adding one window to the policy file | `PUT` an AppProject, sync, merge, approve |
| `mctl_propose_window_removal` | opens a GitOps PR removing or shortening one window | the same; it also needs an owner reviewer |

The MCP server's identity holds no Argo `projects, update`, no
`applications, sync` and no broker token. It writes only through a GitHub
App identity that can push branches `release-window/*` and open PRs, and it
cannot merge.

#### 8.2 PR-authoring contract (P2-5, P3-8)

- **Input schema (exact scope).**
  - `scope` is a list of exact Application names, each present in the
    generated map (Table C / task 4).
  - `kind` must be `deny`. `allow` is refused in the MVP (2.1, T183).
  - The target AppProject must not be `default`, and the rendered match
    set must not reach the recovery chain (3.2, T160-T161).
  - Schedule: either `zone` (IANA, validated with `zoneinfo`) plus `recur`
    (the section 2 subset) plus `start_local`/`end_local`; or
    `start_utc`/`end_utc`.
  - `owner`, `decided_in` (an issue link) and `reason` are required.
  - The duration must not exceed `max_window`.
  - Unknown fields are refused.
- **Deterministic id.** `window_id = "w-" + sha256(canonical(scope, kind,
  schedule, zone))[:12]`. The idempotency key is `(caller,
  client_request_id)`.
- **Dedup.** The branch is `release-window/<window_id>`. If an open PR exists
  for it, the tool returns that PR. If the window is already on `main`, the
  tool returns "already present" with the merge SHA. A request that overlaps
  an existing window with the same scope and kind is refused, with a pointer
  to the existing window.
- **Diff restriction.** The allowlist is the one policy file, and within it
  only the `windows[]` entry with this id. The validator, run from the base,
  diffs the PR against the base. It refuses any change outside that entry,
  any widened scope, and any change that shortens, removes or converts an
  existing deny, unless the PR is a `propose_window_removal` for that id.
- **Rebase or retry.** On a base change, the tool recomputes the semantic
  diff. If it no longer equals the original request, the PR is closed with a
  reason and nothing is force-pushed over it.
- **Approval.** Normal review applies, with no self-approval: the requester
  identity cannot be the approver. Removals and weakenings need an owner
  reviewer (CODEOWNERS on the policy file, a later S1/S2 decision). The
  merge goes through the merge queue like any PR.
- **Derived blast radius.** The PR body lists the exact Applications
  matched, their AppProjects, and whether each is a G0 pilot. It includes a
  dry-run projection that is marked `incomplete` if any construct is
  not-translatable.
- **Audit.** Request id, caller, window id, PR number, reviewed head SHA,
  merge SHA, and later the activation-state transitions.

#### 8.3 Status contract (P2-6)

```json
{
  "application": "labs-mctl-telegram",
  "project": "apps",
  "policy": {"decision": "DENY", "rule": "row2:w-7f3a9c", "source_sha": "<sha>"},
  "activation": {"state": "effective", "window_id": "w-7f3a9c",
                 "root_app_synced_revision": "<sha>", "live_window_hash": "<sha256>",
                 "assigned": true, "active": true, "manual_can_sync": false,
                 "read_at": "2026-11-21T10:30:00Z", "read_age_s": 12},
  "coverage": {"path": "P8a", "label": "enforced",
               "residuals": ["P8b admin", "P8c kubectl", "P8d restart (unknown)", "in-flight sync"]},
  "exception": {"path": "none", "guarantee": "none"},
  "notes": ["canSync is the manual-sync answer; it is not proof of path coverage"]
}
```

`coverage.label` is per asked-about path, never "all paths". The fixtures
cover:

- an unrelated project (the window does not match, so the policy says `DENY`
  but the activation state is `drifted`);
- a live window that matches `root-app` (`self-locked`, "not recoverable via
  GitOps", never `drifted`; T165);
- a changed selector;
- a missing live AppProject (`unknown`);
- admin and `kubectl` residuals;
- an in-flight sync at the start;
- a tenant restart action (P8d `unknown`).

### 9. S0 decision / coverage / threat / cost matrix (current evidence; refreshed at S0 exit)

| Criterion | Broker on G0 pinned pilot | Broker on main-tracking app (G2) | E1 carve-out | E2 manualSync + RBAC | D break-glass only | Native/plugin (C) |
|---|---|---|---|---|---|---|
| Guarantee at effect | G0 for revisions; spec-field race `unknown` (T103) | **G2**: partial unauthorized apply possible (T104) | none | none (G0 revisions if pinned, no grant) | n/a | n/a at v3.3.8 |
| Exactly one approved release | only if T100-T103 pass, and excluding token compromise and admin | **no** | no | no | no | n/a |
| Fail mode | closed | closed (after detection) | **open** on a failed restore | closed | closed | n/a |
| Token compromise | **not enforced**: pinned revisions applied without a grant (T105) | **not enforced**: `main` applied without a grant | n/a | role token: same | n/a | n/a |
| Tenant manual-sync bypass | blocked if T revoked first (6.7) | same | open during carve-out | blocked | blocked | n/a |
| Admin / kubectl bypass | residual | residual | residual | residual | is the path | residual |
| Second approval authority | no (mctl-api ledger) | no | no | **the role holder** | the admin | n/a |
| Requires a pin change of the pilot (S3) | **yes**, through M1/M2/M3 only (6.3.1, T170-T177) | no | no | no | no | fork |
| Recovery chain stays syncable | required (3.2, T160-T169) | required | the carve-out edits the AppProject through root-app, so required | required | required | n/a |
| New trusted component and state | broker, Argo role, `release_exception_ops`, dedicated kind, token minter | same | generator + detector | role + token | none | fork |
| Tenant UX cost | loses manual sync on the pilot; deploys by pin PR | loses manual sync | none | loses manual sync | none | n/a |
| Implementation burden | high | high | medium | low | none | very high |
| Recovery when the component is down | D | D | must restore the window | role holder | n/a | n/a |

Falsifiable S0 outcome. The memo picks exactly one:

- `BROKER_PINNED_PILOT_CANDIDATE`, only if all of the following hold:
  - T100-T103 show zero unapproved apply on the pinned harness pilot;
  - one pin mechanism passes T170-T177;
  - T160-T169 pass (no self-lockout is reachable, and recovery is shown);
  - T80-T96, T120-T133 pass;
  - the token-compromise boundary is accepted **explicitly** as a residual;
  - the dedicated-kind semantics are acceptable to the mctl-api owner.
- `BROKER_DETECT_ONLY_REQUIRES_OWNER_RISK_ACCEPTANCE`: G0 fails or pinning is
  unacceptable, so only G2 remains. S0 does **not** recommend this outcome;
  it names it so that the owner can reject or accept it explicitly.
- `E2_HUMAN_ROLE_ONLY`: the broker fails single-call or fail-closed tests,
  but RBAC isolation (T90) holds.
- `D_BREAKGLASS_ONLY`: tenant isolation fails on v3.3.8.
- `NEITHER_SAFE_YET`: blocking unknowns remain (#2543, P12, live
  RBAC/`argocd-cm` unreadable, the T103 result, activation observability).
  This is the **default if evidence is incomplete**.

The calendar outcome is recorded alongside. The working hypothesis is
`HYBRID`, with Sync Windows as the secondary safeguard counted only when
`effective`. `BOUNDED_CALENDAR_MVP` is scoped to the image-bump window
policy.

### 10. Translation matrix and product comparison (from revision 2, unchanged)

Translation to v3.3.8 `syncWindows`:

| Construct | Classification |
|---|---|
| Weekly, daily and `bymonthday` windows in UTC | translatable |
| Recurring windows in DST zones | UTC cron, widened for deny or narrowed for allow; otherwise `not-translatable` |
| One-offs, including the cross-year `0 0 24 12 *` + `216h` | translatable-with-lifecycle (emit near start, remove after end, drift check feeding the `drifted` state) |
| Ordinal weekday, `COUNT`, `UNTIL` | not-translatable; the Argo layer is `incomplete`, with a non-zero exit and no partial projection |

`timeZone` is not used. Allow rows are model-only: the MVP projection emits
deny windows only (2.1), never into AppProject `default` (3.2).

Products (primary docs read 2026-11-20):

- [GitLab deploy freezes](https://docs.gitlab.com/user/project/releases/):
  advisory `$CI_DEPLOY_FREEZE`.
- [Octopus deployment freezes](https://octopus.com/docs/deployments/deployment-freezes):
  project, environment and tenant scope, with an override-with-reason
  permission. Multi-project freezes are enterprise-only.
- [Harness deployment freeze](https://developer.harness.io/docs/continuous-delivery/manage-deployments/deployment-freeze/):
  beta, and "Account admins will always be able to bypass".

None of these governs MCTL's GitOps writes or Argo syncs. They are reference
only, and prices are `unknown`.

## Alternatives

- **Broker on main-tracking Applications as the recommended path (revision
  3).** Dropped as a recommendation: it is G2, so unapproved content can be
  applied before terminate (re-review P1-1). It is kept only as the named
  `BROKER_DETECT_ONLY_REQUIRES_OWNER_RISK_ACCEPTANCE` outcome.
- **E1 as the default.** Dropped: it fails open and gives no guarantee.
- **Global `manualSync: true`.** Rejected while the tenant CSVs grant `sync`.
- **ADOPT_ARGO_SYNC_WINDOWS alone as the authorizer.** Dropped: Argo cannot
  see MFA grants. Windows count only when observed as `effective`.
- **A PreSync-hook guard.** Not a G0 mechanism, because the hook is part of
  the verified content (6.8).
- **Direct AppProject writes by MCP tools.** Rejected in favour of PR
  authoring (section 8).
- **External CD product.** Dropped as an engine.
- **Pinning a pilot through the shared `targetRevision`.** Rejected: it pins
  every Application and the generator (6.3.1).
- **Windows in AppProject `default`.** Rejected for the MVP: they can lock
  root-app and argocd-self-managed (3.2). A narrower rule ("only selectors
  that miss root-app") was dropped because it depends on proving the
  recovery chain complete, which S0 has not done.
- **Allow windows in the MVP.** Dropped: an allow freezes its matched
  Applications outside its interval (2.1).
- **Mutating the Application spec per exception.** Dropped: it is an unbound
  production write with a fail-open revert. Pinning by a reviewed PR is
  different: it is the normal GitOps path, and it is evaluated only as an S3
  precondition.
- **A "production deployment freeze" claim.** Dropped (Tables A/B).

## Platform impact

- Migrations: none. S0 adds documentation, inert fixtures, a local harness
  and inert prototypes. Nothing references them.
- Backward compatibility: no behaviour change. Release holds, ledger mode,
  the merge queue, Argo settings, RBAC, AppProjects, Application pins,
  mctl-api and MCP are untouched.
- Resources: a local kind/k3d cluster and a local Postgres, on the
  researcher's machine only.
- Eventual production boundary. This is not authorized and is recorded only
  for a future security GO. Each item is a separate reviewed change,
  applied in the 6.7 order and each observed before the next:
  - pin the pilot's sources through the one mechanism that passed
    T170-T177 (never the shared value);
  - the recovery-chain guard (3.2) and the deny-only rule (2.1) in CI,
    before any window is merged;
  - an Argo project role and token minter;
  - the `argocd-cm` flag;
  - RBAC deny lines for the pilot and a narrower `wft-create-tenant`;
  - a deny window on one pilot AppProject;
  - a Vault path and an ExternalSecret;
  - the broker Deployment and NetworkPolicy;
  - the mctl-api dedicated kind and `release_exception_ops`;
  - the MCP tools.

  Rollback follows the 6.7 order.
- Risks and mitigations:
  - S0 output mistaken for a GO: the stage table and R-B4.
  - The harness touching production: its scripts refuse any kube context
    but their own and use no mctl credentials.
  - Stale evidence: every claim is pinned to a SHA, tag or dated read.
  - G2 detection mistaken for enforcement: R-E2 and the matrix.
  - A merged window mistaken for an active one: section 3.1.
  - Token theft: 6.6, labelled not enforced.
  - A freeze locking its own revert path: 3.2, refused on every write path
    and reported `self-locked` if it appears live.
  - A pilot pin rippling into other services: 6.3.1, byte-equal proofs.
  - An allow window freezing outside its interval: 2.1, deny-only MVP.
  - The broker becoming a second authority: it only spends ledger grants.
