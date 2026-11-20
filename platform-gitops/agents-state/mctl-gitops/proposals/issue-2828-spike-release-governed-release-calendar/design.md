# Design: issue-2828-spike-release-governed-release-calendar

Revision 2 (2026-11-20). It answers the independent review in
[#2828 comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218).
The scope is **S0 only**: research, read-only inventory, inert offline
experiments and a decision memo. Sections 5-8 describe what S0 must *evaluate*
and are not authorization to build any of it (see requirements.md, stage
table).

## Current state

Clone read at `main` = `5bdf00a0c75291daafda4dc5bff3fc804c1b5fef`
(2026-11-20 10:09 UTC). Every repo citation below is at this SHA unless marked
otherwise. Upstream Argo CD citations are at tag `v3.3.8`. mctl-api citations
are at `main` = `2a8de33ae4494f214ddb798d4cf880de24251160`.

### Version governance that exists (no temporal policy)

- `platform-gitops/release-gates.yaml` contains `version_holds` and `gates`. It
  has no time, window or freeze field, and `grep -ri syncWindow` over the repo
  finds nothing outside this proposal.
- `scripts/release-gate.py` (`check`/`verify`/`diff`/`pr-identity`): exit 6
  means refused, exit 7 means could not observe. It reads the policy from a git
  revision (`--policy-rev`, or `--base HEAD^1` in `pr-identity`).
- `scripts/release-ledger-shadow.py` `judge_ledger` (lines 98-160) is a **pure
  read**. It treats a grant with `consumed_at` as refused and does not reserve
  or consume anything. This read is what P1-2 objects to.
- mctl-api `internal/workitems/action_approvals.go` `ConsumeActionApproval` /
  `consumeActionApproval` (around lines 907-960) is an **atomic CAS**:
  `UPDATE action_approval_requests SET state='consumed', consumed_at=$3 WHERE
  id=$1 AND state='approved' AND intent_hash=$2 AND expires_at > $3 AND
  (fresh_until IS NULL OR fresh_until > $3) AND <kind predicate> RETURNING ...`.
  Requests are idempotent per `(requested_by, idempotency_key)`. This is the
  primitive the exception design reuses (section 5).
- `platform-gitops/argo-workflows/scripts/release-gate-guard.sh`
  (`target`/`outgoing`, POSIX sh + yq) guards **gated groups only**. It is not a
  generic freeze, and it is called by `tpl-git-commit`, `tpl-validate-tenant`,
  `wft-add/remove-custom-domain`, `wft-deploy-service`,
  `wft-promote-deployment`, `wft-provision-database`, `wft-rollback-revision`
  and `wft-rollback-service`.
- `.github/workflows/release-gate-watch.yml` runs on push and schedule
  (`release-gate.py diff`, ledger job). It detects **after the write**.
- `.github/workflows/argocd-freshness.yml` runs after every push to `main` and
  checks whether Argo CD has resolved the commit. It is "Not a merge gate" and
  reports pass/fail, not a latency distribution.

### Table A: production effect paths, labelled for a window policy today

Labels: `enforced` = refused before effect by trusted code; `detected-after-write`;
`not-covered`; `unknown` (could not observe). No window policy exists yet, so
"today" means "what a window check *could* attach to, and what bounds it".

| # | Path | Changes | Pre-effect hook available | Label for a future window check | Evidence |
|---|---|---|---|---|---|
| P1 | `release-deploy.yaml` jobs `preflight` :115, `ledger-gate` :210, `bump` :246, `publish-direct` :662 (env `gitops-bump`), `publish-pr` :748, `enqueue-bump` :899 | image tag/digest | yes, in the workflow itself, before push | candidate `enforced` for direct push (bounded by section 3 margin); queued route as P4b | workflow file |
| P2 | `gitops-bump.yaml` `bump` :143, `publish-direct` :522, `publish-pr` :569, `enqueue-bump` :719 | image tag/digest | yes | as P1 | workflow file |
| P3 | Human PR through merge queue | **anything** | PR + `merge_group` checks only | `not-covered` at effect time (section 3); check runs candidate code (section 4) | ruleset read; `validate-manifests.yml:3-17,62,123` |
| P4 | `claude/*` auto-merge | anything not in `protected_re` | `validate` | as P3 | `auto-merge.yml:78` |
| P4b | `release-bump/*` PR enqueued by `scripts/release-bump-enqueue-wait.sh` | image tag/digest | guards judged on one head **before enqueue** | `not-covered` at merge/sync time unless Argo layer exists | script header lines 19-36 |
| P5a | Argo CWFTs pushing to `main` (`wft-deploy-service`, `wft-rollback-service`, `wft-rollback-revision`, `wft-promote-deployment`, `tpl-git-commit`) | values incl. image | yes, in template code before push | candidate `enforced` only after a CWFT hook exists; template code only | `grep -l "git push" cluster-templates` |
| P5c | CWFTs with **non-image** production effects: `wft-create-tenant`, `wft-delete-tenant-safe`, `wft-retire-service`, `wft-add/remove-custom-domain`, `wft-provision-database`, `wft-platform-skill-*` | namespaces, ingress hosts, databases, removals | same | `not-covered` in any image-bump MVP | same grep |
| P5b/P6 | Write deploy key used outside template code; mctl-agents CWFT `commit-and-push` | any path | none | `unknown`: ruleset `bypass_actors` unreadable (`null`) to this token; runbook says `DeployKey` bypass; #2543 OPEN | `gh api .../rulesets/18465404`; runbook :64-65 |
| P7a | `admins-mctl-api` source 1: `mctlhq/mctl-api.git` `helm/` at `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361` | chart | pin moves only by a GitOps PR | treated as P3 (it is now a GitOps write) | `mctl-api.yaml:10-20` |
| P7b | `admins-mctl-api` source 2: mctl-gitops `platform-gitops/infra-components/mctl-platform/mctl-api` at `main` | manifests | none beyond P3 | as P3 | `mctl-api.yaml:827-829` |
| P7c | Every `apps` / `tenants` / root Application tracks `main` (`bootstrap/values.yaml:4`) | everything under `platform-gitops/` | none beyond P3 | as P3 | `applicationset-apps.yaml`, `root-app.yaml:41` |
| P8 | Argo CD UI/CLI sync or parameter override, `kubectl`, `argocd --core` | anything | Argo Sync Windows cover **syncs only**; tenants hold `applications, sync` on own apps | `not-covered` (kubectl), `unknown` (sync, no windows live) | `argocd/rbac/tenants/labs.csv`; `argocd/values.yaml:165-173` |
| P9/P10 | Vault value changes, optional Secrets via `envFrom` | runtime config | none in git | `not-covered` | runbook :68-69 |
| P12 | Required contexts `validate`, `reserved-hosts`, `cloudflare-plan` bound to integration 15368 (GitHub Actions) | merge gate trust | none | `unknown`/spoofable by a same-named job | ruleset read 2026-11-20 |
| P14 | `cloudflare-apply.yml` (env `cloudflare-apply`, reviewer-gated) | edge / DNS / WAF | environment reviewer | `not-covered` by any GitOps or Argo window | `.github/workflows/cloudflare-apply.yml:314` |
| P15 | Commit merged before freeze, Argo applies during freeze | as committed | only Argo Sync Windows | `not-covered` today | section 3 |

### Table B: non-image GitOps writes that change production without an image tag

`platform-gitops/helm-charts/base-service/**` (renders every `apps` Application
at once), `helm-charts/tenant/**` (every `tenant-*`), non-`image` keys in
`services/<team>/<svc>/values.yaml` (env, resources, ingress, secrets wiring),
`bootstrap/templates/**` (Applications, AppProjects, ApplicationSets),
`argocd/**` (RBAC CSVs, `argocd-cm` settings via `argocd-self-managed`),
`argo-workflows/**` (cluster templates via `argo-workflows-config`),
`infra-components/**`. None of these is parsed by `release-gate.py`, which
parses image tag/digest lines only. This is why the MVP is named
**"image-bump window policy (partial coverage)"** (requirements R-S3).

### Table C: GitOps path to Application to AppProject (hand-read; S0 task 4 must regenerate it from a render)

| GitOps path | Application name | AppProject | Destination ns |
|---|---|---|---|
| `platform-gitops/services/<team>/<svc>/` (+ `helm-charts/base-service/`) | `<team>-<svc>` (`applicationset-apps.yaml` template name from `path.segments[2]-[3]`) | `apps` | `<team>` |
| `platform-gitops/tenants/<t>/` (+ `helm-charts/tenant/`) | `tenant-<t>` | `platform` | (tenant chart) |
| `bootstrap/templates/mctl-platform/mctl-api.yaml` + `infra-components/mctl-platform/mctl-api` | `admins-mctl-api` | `platform` | admins |
| `bootstrap/templates/data/temporal*.yaml` | `temporal`, `temporal-web` | `platform` | |
| `bootstrap/templates/mctl-platform/mctl-agent.yaml`, `mctl-portal.yaml`, core-infra, data, observability | `admins-mctl-agent`, `backstage-workspace-ready`, `vault`, `zitadel`, ... | `default` | various |
| `bootstrap/templates/erpact/applications.yaml` | `erpact-shared` and others | `erpact` | erpact |
| `platform-gitops/bootstrap/**` (incl. AppProjects themselves) | `root-app` | `default` | argocd |
| `platform-gitops/argocd/**` | `argocd-self-managed` | `default` | argocd |

Observations: (1) `<team>-<svc>` names are hyphen-joined, so a wildcard such as
`labs-*` cannot tell apart team `labs` from a hypothetical team `labs-x`; only
exact names are safe (R-M2). (2) AppProjects are rendered by `root-app` in
project `default`. A window in `apps`/`platform` therefore never blocks the
commit that edits the window (R-A9). (3) `project-prod.yaml` is a commented-out
TODO. There is no production/preview project split, so "production" is a
property of the Application, not of the project.

### P7 re-read (corrects revision 1 and the runbook)

Revision 1 stated that P7 was "chart `targetRevision: main`". That is stale.
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml:19` pins the
mctl-api chart to `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361` (comment lines
11-18: 4.164.0 release commit, #2528). The second source (`:827-829`) still
tracks mctl-gitops `main`, and `syncPolicy.automated` has `prune: true`,
`selfHeal: true` (`:893-895`). `docs/runbooks/mctl-api-release-hold.md:66`
still describes P7 as `targetRevision: main`. That runbook line is stale and is
not used as evidence here.

### Argo CD 3.3.8 facts (deployed chart pin, read from source)

- Version: `platform-gitops/argocd/Chart.yaml` depends on `argo-cd` 9.5.9, whose
  packaged `Chart.yaml` (`charts/argo-cd-9.5.9.tgz`) has `appVersion: v3.3.8`.
  `argocd/values.yaml:148` also says "ArgoCD v3.3.8". This is the desired
  version; the running version was not observed.
- `SyncWindow` fields at v3.3.8 (`pkg/apis/application/v1alpha1/types.go` around
  :2781-2799): `kind`, `schedule`, `duration`, `applications`, `namespaces`,
  `clusters`, `manualSync`, `timeZone`, `andOperator` (Go field
  `UseAndOperator`), `description`. **There is no `syncOverrun` field.** It
  exists only on upstream `master` (field `syncOverrun`, documented under "Sync
  Overrun" in `docs/user-guide/sync_windows.md` on master, not in the v3.3.8
  doc).
- `CanSync(isManual)` (v3.3.8 `types.go:3025`): no windows → allow; an active
  deny → deny unless manual and every active deny has `manualSync`; an active
  allow → allow; inactive matching allows exist → deny unless manual and
  `manualSync`; otherwise allow. An invalid window returns an error, and
  `controller/sync.go:559-570` then treats the sync as blocked (fail closed).
- In-flight: `controller/sync.go:141-149` checks the window on every operation
  reconcile. A running operation stays `Running` with message "Sync operation
  blocked by sync window" and continues after the window ends. It is neither
  completed nor rolled back. A multi-wave sync can therefore be left partially
  applied for the whole freeze.
- Time: `active()` (v3.3.8 `types.go:3117-3137`) parses a 5-field cron with
  `robfig/cron` and an absolute `time.ParseDuration`. `scheduleOffsetByTimeZone`
  (`:2886-2893`) uses the zone offset **at `time.Now()`**, not at the
  occurrence, and on an invalid zone logs a warning and **falls back to UTC**
  (validation at `:3182` rejects invalid zones on write). Near DST transitions,
  a `timeZone` window can be off by the DST delta.
- Auto-sync: `appcontroller.go:1860` gates automated sync, including
  `selfHeal`-triggered syncs, with `CanSync(false)`. Drift is therefore not
  healed during a deny window.
- Selectors: application names, destination namespaces and clusters are
  OR-ed by default and AND-ed with `andOperator: true` (docs v3.3.8, "Use AND
  operator" in UI). Wildcards are supported.

### Timing

- #970 (closed 2026-09-02) reported up to ~7 min propagation. Since then the
  push webhook and `--revision-cache-expiration=30s`
  (`platform-gitops/argocd/values.yaml:137,306,313-322`) were added, with a
  180 s poll fallback (`:35`). No measured latency distribution was found;
  `argocd-freshness.yml` recent runs (2026-11-20) are a mix of success,
  failure and cancelled (concurrency `cancel-in-progress`). The "7 min" figure is
  stale-until-measured.
- Merge queue (ruleset 18465404): `check_response_timeout_minutes: 120`,
  `max_entries_to_build: 1`, `max_entries_to_merge: 1`,
  `min_entries_to_merge_wait_minutes: 0`, merge method `MERGE`.
- `release-ledger-shadow.py gate` can wait for an owner decision (the hold has
  `wait_minutes: 60`). A check at preflight can therefore be up to an hour
  older than the push.

Deployed state checked:
- `git log -1` on the clone: `5bdf00a0...` (2026-11-20 10:09 UTC).
- `/workdir/mctl-gitops/platform-gitops/services/*/` (`$MCTL_GITOPS_ROOT`): same
  service directories as the clone (`diff` empty). Tenants admins, karabu, labs,
  namax66, redloop have services. This is desired state only.
- `mctl_whoami`: `agent:issue-investigator`, Admin false, Teams [], no
  namespaces. No tenant/service live state is observable with this identity.
- `mctl_get_service_status admins/mctl-api`: "ArgoCD application not found:
  admins-mctl-api". Interpreted as **no access**, not absence (the Application is
  defined in `mctl-api.yaml`). Live Argo state is `unknown`.
- `gh api repos/mctlhq/mctl-gitops/rulesets/18465404`: rules `deletion`,
  `non_fast_forward`, `pull_request` (1 approval, dismiss stale),
  `required_status_checks` (`cloudflare-plan`, `reserved-hosts`, `validate`, all
  integration 15368, not strict), `merge_queue` (above). `bypass_actors`: `null`
  (not readable); `current_user_can_bypass: never`.
- `gh issue view`: #2543 OPEN (2026-11-13), #2528 CLOSED (2026-11-11), #970
  CLOSED (2026-09-02), #2668 OPEN (2026-11-15).
- `gh run list -w argocd-freshness.yml -L 5`: runs exist; conclusions vary; no
  latency figures in the listing.
- Upstream: Argo CD `v3.3.8` source (`types.go`, `controller/sync.go`,
  `controller/appcontroller.go`) and docs `sync_windows.md` at v3.3.8 and master;
  mctl-api `action_approvals.go` at `2a8de33`.
- Vendor primary docs read 2026-11-20 (section 8).

## Proposed solution

S0 delivers evidence and an offline model. It does not deliver a running
system. The items below define what S0 must produce and what the later-stage
design must satisfy if the owner continues.

### 1. S0 deliverables and exit gate

1. `docs/spikes/2828-release-calendar/inventory.md`: tables A-C regenerated and
   re-verified, each row labelled per R-S2 with a citation and date.
2. `tests/research/release_calendar_s0/model.py` (stdlib + PyYAML + `zoneinfo`,
   run with `python3 -I`): the pure policy function of R-P1, plus fixtures under
   `tests/fixtures/release-calendar-s0/`. It is **not** referenced by any
   workflow, `validate-manifests.yml` or CWFT, and runs only by hand.
3. `tests/research/release_calendar_s0/argo-inert/`: a kind/k3d script that
   installs Argo CD v3.3.8 (chart 9.5.9) with dummy Applications from a local git
   server, and the recorded results of tests T20-T25, T40-T44 and T50-T56. It
   never connects to the production cluster or repo.
4. `docs/spikes/2828-release-calendar/decision.md`: the S0 decision matrix
   (below, refreshed with results), the recommended outcome, residual risks, and
   a list of follow-ups mapped to existing issues (#2543, #2668, mctl-api#1022,
   .github#181, .github#254, mctl-agents#217).
5. Exit gate: an independent review of the memo, then an owner decision on
   #2828. S1 needs a new proposal, and S2/S3 a separate security GO.

### 2. Policy model (illustrative schema, fixtures only)

```yaml
# tests/fixtures/release-calendar-s0/policy-example.yaml (illustrative; not a real freeze)
version: 1
default: allow                 # v1: must be "allow"; deny-by-default = allow windows
max_window: 21d                # bounds recurrence expansion and any one window
margins:
  sync_start: 5m               # placeholder until S0 task 3 measures it
scopes:
  platform-api: {applications: [admins-mctl-api]}      # exact Argo names only
  labs-bot:     {applications: [labs-mctl-telegram]}
windows:
  - name: example-weekend-freeze
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    zone: Europe/Berlin
    recur: {freq: weekly, byday: [FR]}     # constrained RRULE subset
    start_local: "16:00"                   # wall clock, per occurrence
    end_local: {day_offset: 3, time: "08:00"}  # Monday 08:00 local
  - name: example-year-end
    owner: <github-login>
    decided_in: mctlhq/mctl-gitops#NNNN
    kind: deny
    scope: platform-api
    start_utc: "2026-12-24T00:00:00Z"      # one-off, absolute UTC instants
    end_utc:   "2027-01-02T00:00:00Z"
```

**Truth table** (per Application `a`, instant set `I = [t_check, t_effect_max]`).
Let `M` = windows whose scope contains `a`, `D*` = deny windows in `M` active at
some instant of `I`, and `A*` = allow windows in `M`. The table is evaluated
top-down and the first matching row wins.

| # | Condition | Result | Argo 3.3.8 `CanSync(false)` |
|---|---|---|---|
| 0 | policy unreadable/invalid (R-P2) | `UNKNOWN` | error → blocked |
| 1 | `M` empty | `default` (= `ALLOW` in v1) | no windows → allow |
| 2 | `D*` non-empty | `DENY` | active deny → deny |
| 3 | `A*` non-empty and every instant of `I` lies inside some allow in `A*` | `ALLOW` | active allow → allow |
| 4 | `A*` non-empty, otherwise | `DENY` (outside release window) | inactive allows → deny |
| 5 | only deny windows match, none active in `I` | `ALLOW` | → allow |

Row 1 resolves revision 1's contradiction: `default` applies **only when no
window matches the scope**. Allow windows, once present for a scope, define the
only permitted times (row 4), exactly as in Argo. Tests T1, T5 and T6 are
rewritten to this table, and T6 asserts row 4. Multi-Application changes
combine as R-P4 describes.

**Time semantics (P3-10).** Recurring windows: each occurrence's start and end
are computed as wall-clock local times in `zone` with `zoneinfo`, then converted
to UTC. The duration is therefore the wall-clock span, and the absolute length
of an occurrence changes by the DST delta. Example: Fri 16:00 to Mon 08:00
Europe/Berlin is 64 h absolute normally, 65 h across the late-October
fall-back, and 63 h across the late-March spring-forward. A gap time moves
forward to the first existing instant. For an ambiguous time, deny windows use
`fold=0` at the start and `fold=1` at the end, and allow windows do the
opposite, so ambiguity always widens deny and narrows allow. Absolute
`duration:` is accepted only when `zone: UTC` or for `start_utc`/`end_utc`
one-offs. All intervals are half-open `[start, end)`. The expansion horizon is
`[t - max_window, t_effect_max]`. Supported recurrence subset: `freq` daily,
weekly or monthly; `byday` (no ordinals); `bymonthday`; no `COUNT`/`UNTIL`
(use one-offs). Anything else is `UNKNOWN`.

### 3. Merge queue and point of effect (P1-1)

The four instants: `t_check` (a CI check or workflow step evaluates),
`t_merge` (commit on `main`), `t_sync_start` (Argo starts an operation at that
revision) and `t_sync_end`. A check proves nothing about `t_merge` or
`t_sync_start` unless something bounds the gap:

- **Direct-push writers (P1/P2 `publish-direct`, P5a CWFTs):** the writer can
  evaluate immediately before each push attempt, so `t_merge - t_check` is
  seconds. `t_sync_start - t_merge` is bounded only statistically (webhook,
  30 s cache, 180 s poll) and has no hard upper bound (retries, a down
  controller). A write-time check can therefore refuse writes into a window
  but cannot guarantee that a write made just before a window is applied before
  it. The judged interval `[t_check, t_check + sync_start margin]` reduces the
  gap, and only an Argo deny window closes it.
- **Queued PRs (P3, P4, P4b):** `release-bump-enqueue-wait.sh` judges one head
  before enqueue. The `merge_group` run of `validate` starts when the entry is
  built and can take up to 120 min (`check_response_timeout_minutes`), and the
  merge follows its completion. A check at the *end* of the `merge_group` job
  bounds `t_merge - t_check` only to the GitHub merge latency, which is not
  documented. **Conclusion for S0: no PR or queue path may be labelled
  `enforced` at the point of effect.** At best it is "refused at check time,
  with a residual gap". Point-of-effect coverage exists only where an Argo deny
  window matches the Application (R-Q1, R-Q4).
- **Commit before freeze, sync during freeze (P15):** with no Argo window it is
  `not-covered`. With a deny window (no `manualSync`) the sync does not start
  until the window ends, and the commit applies at window end. S0 records this
  as expected behaviour for operators ("pending changes apply when the freeze
  ends").
- **In flight at window start:** on v3.3.8 the operation pauses mid-way (Argo CD
  3.3.8 facts above). A multi-wave service can therefore stay partially applied
  for the whole freeze. S0 must measure this on the inert cluster. Any later
  design must either accept it explicitly or schedule deny windows to start only
  after a `sync_start` margin with no running operation, which cannot be
  guaranteed.

Fixtures (T20-T25): (a) check T-60m, freeze T, merge T+5m, sync T+6m; (b) a PR
held in the queue across T; (c) merge T-2m, sync start T+1m; (d) a multi-wave
sync started T-1m, wave 2 at T+1m; (e) the same as (c) with an Argo deny window
present; (f) a direct push whose check is at T-30s and whose push lands at T+10s
(the pre-push re-check must refuse).

### 4. Trust boundary (P2-9)

Fact: `validate-manifests.yml` checks out the PR merge ref (`:62`, no `ref:`)
and runs `python3 scripts/release-gate.py pr-identity --base HEAD^1 ...`
(`:123`) from that checkout. The policy comes from the base, but the **code
comes from the candidate**. Any later evaluator must:
- obtain both evaluator and policy from the base commit, e.g. `git show
  "$BASE:scripts/<evaluator>" > "$RUNNER_TEMP/eval.py"` and `git show
  "$BASE:<policy>"`, then run `python3 -I "$RUNNER_TEMP/eval.py"` from a
  directory that contains no candidate files; or run in a workflow that never
  checks out candidate code;
- not count any integration-15368 context as trusted enforcement until the
  App-bound `release-hold` context (runbook task 14) or an equivalent exists
  (P12);
- not count `protected_re` (`auto-merge.yml:78`) as a trust boundary.

S0 builds the malicious-PR fixtures in a **local throwaway git repository**:
the PR changes the evaluator to always allow; the PR deletes the active window;
the PR changes the fixtures; the PR adds a workflow job named `validate`. The
first three are tested against the base-pinned runner pattern. For the fourth,
S0 records the GitHub documentation of rulesets' integration binding and labels
it `unknown` unless reproduced in a sandbox repository the owner provides
(never in mctlhq/mctl-gitops).

### 5. Single-use exception protocol (P1-2; design to evaluate, S2 to build)

Authority stays where it is: a human with fresh MFA on the existing mctl-api
decide page. The calendar adds no approver.

1. **Request.** An operator or agent creates a pending request of a new
   action kind (proposed `release.calendar_exception`) in mctl-api's
   `action_approval_requests` with `idempotency_key` = a key chosen by the
   requester. The intent fields (R-X3) are hashed into `intent_hash`;
   `expires_at` is at most `max_exception_ttl`. Agents can request, never
   decide.
2. **Decide.** A human approves on the decide page (MFA, `fresh_until`).
3. **Claim (atomic).** The writer (a bump workflow job or a CWFT step)
   recomputes the intent hash from what it is about to push and calls the
   consume endpoint. mctl-api runs the existing CAS. Exactly one concurrent
   writer wins. A loser, an expired or stale grant, or an intent mismatch is
   refused (R-X4). The writer records `writer_run = <workflow run id>/<attempt>`
   in the commit trailer, not in the hash, so that hash equality is the binding.
4. **Effect.** The writer pushes one commit whose diff is exactly the bound
   path(s) and digest, with the trailers `Release-Exception: <aar_id>` and
   `Release-Exception-Intent: <intent_hash>`. On a non-fast-forward it rebases
   and re-runs `release-bump-diff-guard.py`-style checks on the outgoing diff.
   If the diff still equals the intent it pushes again; otherwise it aborts and
   the claim stays spent (R-X5).
5. **Crash / failed push.** Spent with no effect. A new human decision is
   needed (consume-before-effect gives at-most-once, never twice). This is the
   same rule mctl-api already applies to `deploy.apply` grants.
6. **Reconcile.** A post-push detector (a `release-gate-watch` sibling) maps
   commits to consumed exceptions 1:1 (R-X7). A covered-path commit in a deny
   window with no trailer, a trailer whose exception is not consumed, or two
   commits with one id is a violation. Consumed with no commit after `not_after`
   is reported as "spent without effect".
7. **Rollback.** Same protocol. The intent binds the target `dep_` deployment
   (already required to be succeeded and observed healthy by
   `wft-rollback-revision`), its gitops commit and digest.

Open dependency: whether the generic consume path (which excludes "dedicated"
kinds) and the writer's authentication fit this. This needs mctl-api owner
input (requirements, Open questions).

### 6. Exception vs Argo deny (P1-3)

Requirement: an approved hotfix or healthy rollback passes, an unapproved sync
stays denied, and the freeze is never disabled globally. Candidates S0 must
test on the inert cluster:

- **E1, scoped carve-out (candidate).** Generated deny windows list exact
  Application names (R-M2). After the exception is consumed, a carve-out commit
  regenerates the AppProject without `a` in that window's `applications` list
  (or, if `a` is alone, removes that one window) and adds an annotation that
  carries `aar_id` and `not_after`. The carve-out lands before the bump; `root-app`
  (project `default`) syncs the AppProject, then `a` auto-syncs the approved
  commit. Every other Application stays denied. Restore is a second commit.
  Risks: the carve-out is itself a production-governance write during a freeze
  and goes through the same guard; a failed restore leaves `a` open
  (fail-open), so the detector must alert past `not_after`; while carved out,
  anyone with `sync` on `a` can sync, but `main` for `a`'s paths contains only
  the approved change because the write guards still refuse other writes.
- **E2, narrow manual path.** Deny windows with `manualSync: true` **and**
  Argo RBAC that removes `applications, sync` for frozen Applications from
  tenant roles (today `p, role:team-labs, applications, sync, apps/labs-*,
  allow` in `argocd/rbac/tenants/labs.csv`), leaving sync only to a dedicated
  exception account used by the exception writer. Risk: the RBAC change is
  permanent rather than time-bound, it changes tenant UX outside freezes, and
  `role:admin` (`argocd/values.yaml:167`) can still sync.
- **E3, global `manualSync: true`.** Rejected (R-A6): every tenant and admin
  sync becomes a bypass.

Test matrix (T40-T44): an approved hotfix reaches Synced/Healthy; an
unapproved `argocd app sync` of a frozen Application is refused; an approved
rollback to a healthy `dep_` succeeds; a carve-out past `not_after` is
detected; restore without disabling other windows.

### 7. Translation matrix to `syncWindows` (P2-5)

| Policy construct | Argo 3.3.8 form | Class |
|---|---|---|
| weekly `byday` + wall-clock start/end, `zone: UTC` | `M H * * DOW` + `duration` | translatable |
| daily, UTC | `M H * * *` + duration | translatable |
| `bymonthday`, UTC | `M H D * *` + duration | translatable |
| any recurring window in a DST zone | UTC cron, widened (deny) / narrowed (allow) by the DST delta on transition weeks, or split per DST period | translatable-with-lifecycle (generator re-run at each DST change), else not-translatable |
| one-off within one calendar year | `M H D Mon *` + duration (repeats yearly) | translatable-with-lifecycle (emit near start, remove after end, drift check fails if stale) |
| one-off crossing a year (2026-12-24 to 2027-01-02) | `0 0 24 12 *` + `216h` | translatable-with-lifecycle (as above) |
| ordinal weekday ("2nd Tuesday") | robfig cron ORs DOM and DOW, no ordinals | not-translatable |
| `COUNT`/`UNTIL` | none | not-translatable (use one-offs) |
| exception carve-out | list edit (section 6) | special: E1 only |
| `timeZone` on the window | supported, but offset taken at `time.Now()` | not used (R-A4) |

A `not-translatable` window that matches an Application makes the Argo layer
for that Application `incomplete` (R-A2). The generator exits non-zero, and no
partial projection is applied, so there is no silent fallback.

### 8. Product comparison (P3-11; primary docs read 2026-11-20)

| Product | Freeze model | Enforcement point | Bypass | Licence/tier (as documented) | Fit for MCTL |
|---|---|---|---|---|---|
| Argo CD Sync Windows (v3.3.8) | cron + duration, allow/deny, `manualSync`, `timeZone`, `andOperator`; no `syncOverrun` until after 3.3 | Argo sync (auto, manual, selfHeal) | AppProject edit, `manualSync`, `kubectl`, `argocd --core` | open source, already deployed | secondary safeguard (S3) |
| GitLab deploy freeze ([docs](https://docs.gitlab.com/user/project/releases/)) | cron `freeze_start`/`freeze_end` + time zone | jobs must check `$CI_DEPLOY_FREEZE` via `rules` | jobs that do not honour it | page lists Free/Premium/Ultimate | reference only (advisory variable) |
| Octopus deployment freezes ([docs](https://octopus.com/docs/deployments/deployment-freezes)) | start/end + daily/weekly/monthly/annual/custom recurrence; project/environment/tenant scope | Octopus deployments | `DeploymentFreezeAdminister` + override with reason | multi-project freezes enterprise-only from 2025.2.7631; price not on page | reference for scope and override-with-reason UX |
| Harness deployment freeze ([docs](https://developer.harness.io/docs/continuous-delivery/manage-deployments/deployment-freeze/)) | schedule + recurrence + time zone; account/org/project scope | Harness pipelines; running pipeline finishes current stage, then "Aborted By Freeze" | Override permission; "Account admins will always be able to bypass"; webhook keys with override | Beta behind feature flag; plan not stated | reference for in-flight semantics |

None of them governs MCTL's GitOps writes. Adopting any of them as an engine is
out of scope. Prices are `unknown` (not on the primary pages read).

### S0 decision matrix (current evidence; refreshed at the S0 exit)

| Criterion | A: Argo Sync Windows + thin PaC | B: extend release-gate tooling | C: external product | D: HYBRID (B primary, generated A secondary) | DEFER_UNTIL_GATES_CLOSED |
|---|---|---|---|---|---|
| Safety (no second authority) | good | good (ledger CAS) | poor | good | good |
| Enforcement coverage | Argo syncs only; not commits, kubectl, edge, Vault | direct-push image writers only; PR/queue only with gap | only its own pipelines | image-bump writers + point-of-sync for exact-named Apps; still partial | none new |
| Bypass resistance | AppProject edit via root-app, admin, `--core` | #2543 deploy key `unknown`, P12 | MCTL paths bypass it | best of A+B; still P5b/P8/P12/P14 | n/a |
| Exception compatibility | cannot see ledger; needs E1/E2 | CAS exists in mctl-api | own approvals = second authority | needs section 5 + 6 together | n/a |
| Operator UX | Argo UI shows windows | needs a view | rich | one policy, one view | none |
| Cost | none | none | licence + integration | none | none |
| Implementation burden | low, but DST/one-off limits | medium | high | high, staged | none |

Working recommendation for the memo: **HYBRID under investigation**. S0 is
expected to end with either `HYBRID` (with S1 limited to an "image-bump window
policy (partial coverage)" shadow) or `DEFER_UNTIL_GATES_CLOSED` if #2543/P12
remain open. The S0 results decide which.

## Alternatives

- **Revision 1 as written (phased build with enforcement in the task list).**
  Dropped. It mixed research and implementation, claimed single use without an
  atomic claim, and had a margin that did not cover the queue and an Argo layer
  that blocked approved exceptions (review P1-1..P1-3).
- **ADOPT_ARGO_SYNC_WINDOWS alone.** Dropped as the primary authorizer: it
  cannot refuse the GitOps write, cannot see MFA exceptions, is cron-only with
  a now-offset zone, and AppProject edits ride `root-app`. Kept as the S3
  secondary safeguard.
- **External product (C).** Dropped as an engine: each one governs only its
  own pipelines, and their approvals would be a second authority. Used as
  reference semantics.
- **Expand to a full "production deployment freeze" now.** Dropped: Table A/B
  paths P5b, P5c, P8, P9/P10, P12, P14 have no pre-effect hook today. Claiming
  it would be false (P1-4).

## Platform impact

- Migrations: none. S0 adds documentation and inert test assets only, none of
  them referenced by workflows, charts or CWFTs.
- Backward compatibility: no behaviour change. Release holds, the ledger
  `enforce` mode, the merge queue, Argo CD settings and RBAC are untouched.
- Resource impact: a local kind/k3d cluster on the researcher's machine during
  S0; no cluster or CI resources.
- Risks and mitigations:
  - S0 artifacts mistaken for an enforcement promise → every artifact carries
    the coverage labels and the MVP name "image-bump window policy (partial
    coverage)".
  - An inert test leaks to production → the scripts take an explicit kubeconfig
    for a kind/k3d context and refuse any other context; no mctl credentials
    are used.
  - Stale evidence → the memo pins every claim to a SHA, tag or API read with
    date; unreadable sources are `unknown`.
  - Agents treating acceptance as an implementation GO → requirements R-B3/R-B4;
    tasks contain no S1-S3 checkboxes.
