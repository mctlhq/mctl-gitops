# Design: issue-2828-spike-release-governed-release-calendar

## Current state

Repository read at `main` = `27158635e889a57f4b0fc2aa6d6d707d30616c33` (2026-11-20).

### What exists (version governance, no temporal policy)

- `platform-gitops/release-gates.yaml` (405 lines) has two sections:
  `version_holds` (line 38; one hold, `mctl-api-bootstrap`, `held_from: "4.155.0"`,
  `ledger.mode: enforce`, `wait_minutes: 60`, `bump_pr_author: mctl-gitops-pr[bot]`,
  `bump_pr_branch_prefix: release-bump/`) and `gates` (line 381; group
  `mctl-agents-workers` with `min_tag`, `requires`, `prepull_paths`). There is no
  time, window, schedule or freeze field anywhere. `grep -ri syncWindow` over the
  repo returns nothing.
- `scripts/release-gate.py` (1000 lines): `check` / `verify` / `diff` /
  `pr-identity`; exit 6 = refused, 7 = could not observe; "could not observe is
  never observed fine". Policy is read from `origin/main` via `_policy_doc(...,
  rev)` (`--policy-rev origin/main`). `_ledger_cfg` validates `mode` in
  `LEDGER_MODES = ("shadow", "enforce")`; this shadow-then-enforce pattern is the
  precedent this design reuses.
- `scripts/release-ledger-shadow.py` (657 lines): `gate` (release-deploy
  `ledger-gate` job, polls mctl-api `GET /api/v1/release/grants` for an approved,
  unexpired, unconsumed MFA decision bound to repository+version+commit+digest)
  and `watch` (post-push in `release-gate-watch.yml`, job `ledger`).
- `scripts/release-preflight.py`: preflight/publish checks, reads
  `platform-gitops/release-bindings.yaml` and `release-gates.yaml` from main;
  `ALLOWED_PREFIXES` = `services/`, `argo-workflows/cluster-templates/`,
  `bootstrap/templates/mctl-platform/`.
- `platform-gitops/argo-workflows/scripts/release-gate-guard.sh` (`target` /
  `outgoing`, POSIX sh + yq, no python in `mctl-workflow-tools`) is called by
  `wft-deploy-service`, `wft-rollback-service`, `wft-rollback-revision`
  (lines 198, 211, 216), `wft-promote-deployment`, `tpl-git-commit`,
  `wft-add/remove-custom-domain`, `wft-provision-database`, `tpl-validate-tenant`.
- `.github/workflows/auto-merge.yml` `protected_re` keeps the gate files and the
  bump workflows out of bot auto-merge.
- `docs/runbooks/mctl-api-release-hold.md`: write-path inventory with statuses.

### Release write-path inventory, re-labelled for a calendar

Effect points: (a) a commit lands on mctl-gitops `main`; (b) Argo CD resolves
and syncs it (auto-sync + `selfHeal` in `applicationset-apps.yaml:56-58`,
`applicationset-tenants.yaml:54-56`, `root-app.yaml:50-54`; reconciliation
poll `timeout.reconciliation: 180s` in `platform-gitops/argocd/values.yaml:35`;
#970 reports up to ~7 min until resolved, measured after the fact by
`.github/workflows/argocd-freshness.yml`); (c) out-of-band cluster changes.

| # | Path (from runbook + workflows) | Could a calendar check run before effect? | Status for a calendar today |
|---|---|---|---|
| P1 | `release-deploy.yaml` (`preflight`, `ledger-gate` :210, `bump` :246, `publish-direct` :662 env `gitops-bump`, `publish-pr` :748) | yes, same points as `release-gate.py check/verify` | not implemented; enforceable |
| P2 | `gitops-bump.yaml` (`bump` :143, `publish-direct` :522, `publish-pr` :569, `enqueue-bump` :719) | yes | not implemented; enforceable |
| P3 | Human PR through merge queue (`validate-manifests.yml`, `merge_group`) | yes at PR + queue; but freeze may start between queue check and merge | not implemented; enforceable with margin |
| P4/P4b | `claude/*` auto-merge, `release-bump/*` PR route | yes via `validate` | not implemented; enforceable |
| P5a | Argo CWFTs (`wft-deploy-service`, `wft-rollback-*`, `wft-promote-deployment`, `tpl-git-commit`) | yes, inside `release-gate-guard.sh`-style step (sh + yq only) | not implemented; enforceable in template code |
| P5b/P6 | deploy-key push to `main` outside template code (ruleset 18465404 `DeployKey` bypass, #2543) | no pre-effect check exists | BLOCKING-UNKNOWN (detector only) |
| P7 | mctl-api chart `targetRevision: main` (chart changes with no GitOps write) | no | BLOCKING-UNKNOWN |
| P8 | Argo CD UI/CLI sync/param override, `kubectl` by admins, `argocd --core` break-glass | only Argo sync windows (and only for syncs, not kubectl) | BLOCKING-UNKNOWN |
| P12 | `validate` status context spoofable by a PR-defined job | no | BLOCKING-UNKNOWN |
| -- | Commit pushed before freeze, reconciled during freeze | only Argo sync windows act at effect time | gap unless effect margin or sync window |

Deployed state checked:
- `git log -1` of the clone: `27158635...` (2026-11-20); every file citation above is at this SHA.
- `mctl_list_tenants`: refused, "listing all tenants requires admin access". Tenant list NOT observed via API.
- `$MCTL_GITOPS_ROOT`-style checkout at `/workdir/mctl-gitops/platform-gitops`: `services/` has `admins, karabu, labs, namax66, redloop`; `tenants/` has `admins, commerce-proof, erpact, karabu, labs, mctl, namax66, redloop`. This is GitOps desired state, not live state.
- `platform-gitops/bootstrap/templates/projects/project-{apps,default,erpact,platform}.yaml`: no `syncWindows` in any AppProject (desired state). Live AppProjects were not read.
- Ruleset 18465404, deploy keys, live Argo CD version and live AppProjects: not observed in this run (no read-only access used); taken only from the runbook's 2026-11 statements, which must be re-verified (task 1).
- Upstream product docs (Argo CD sync windows, Octopus, Harness, GitLab): not fetched in this run; statements below are marked "to verify".

## Proposed solution

Recommended outcome: **HYBRID**, phased, with enforcement held behind an owner
security decision. One canonical policy, judged where MCTL already judges
releases; Argo CD sync windows later, generated from the same policy, as a
secondary defence for effect-time and UI-sync paths.

### 1. Canonical policy: `platform-gitops/release-windows.yaml` (new, illustrative)

Separate file rather than a new section in `release-gates.yaml`, because
`version_holds` is REQUIRED and every gate consumer parses that file; a
separate file can be introduced in shadow without changing existing failure
modes. Same conventions: read from `origin/main`, duplicate keys refused, all
unknowns refuse in enforce.

```yaml
# Illustrative only. Not a real freeze.
version: 1
mode: shadow                 # shadow | enforce (enforce only via owner-decided PR)
default: allow               # required; applies when no window matches
propagation_margin: 15m      # effect interval judged = [now, now + margin]
max_exception_ttl: 4h
scopes:                      # named blast-radius groups, explicit paths only
  platform-core:
    paths:
      - platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
      - platform-gitops/services/admins/*/values.yaml
windows:
  - name: example-weekly-freeze
    owner: mashkovd
    issue: mctlhq/mctl-gitops#NNNN      # where the window was decided
    effect: deny                        # deny | allow
    scope: platform-core
    timezone: Europe/Berlin             # IANA; storage and evaluation in UTC
    rrule: "FREQ=WEEKLY;BYDAY=FR;BYHOUR=16;BYMINUTE=0"
    duration: 64h                       # half-open [start, start+duration)
    rollback_allowed: false
  - name: example-one-off
    owner: mashkovd
    issue: mctlhq/mctl-gitops#NNNN
    effect: deny
    scope: platform-core
    start: "2026-12-24T00:00:00Z"       # one-off, UTC
    end:   "2027-01-02T00:00:00Z"
```

Semantics: deny wins over allow; no priority field (avoids allow-overrides-deny
escalation); if any `allow` windows exist for a scope, writes outside them are
refused (release windows); RRULE subset only (FREQ=DAILY/WEEKLY/MONTHLY,
BYDAY, BYHOUR, BYMINUTE, BYMONTHDAY; no COUNT/UNTIL tricks initially); DST
rules as in requirements.md; holidays are just owner-written one-off windows.
Audit of edits = git history + required PR + `protected_re`; the window's
`issue` field names where it was decided.

### 2. Evaluator: `scripts/release-window.py` (new, stdlib + PyYAML + `zoneinfo`)

Subcommands mirroring `release-gate.py`: `check --files F... --at T`,
`diff --base B --head H` (judged at the push time), `explain --file F --at T`,
`list --from --to` (expanded windows, for the calendar view and ICS),
`--selftest`. Exit 0/6/7 same meaning. Pure function of (policy, files, instant,
exception) so fixtures are deterministic with an injected clock. For Argo
CWFTs (no python), a precomputed, committed expansion is not acceptable (stale);
instead the CWFT calls the evaluator through the existing mctl-api surface or a
python step image - decided in task 6.

### 3. Hook points (only after the owner GO; shadow first)

Same places `release-gate.py` runs: `release-deploy.yaml` `preflight` and
before every push in `publish-direct` / `publish-pr`; `gitops-bump.yaml` same;
`validate-manifests.yml` (PR and `merge_group`; a queue entry can wait up to
120 minutes, longer than the margin, so a merge can still land after a freeze
starts and the push-time `release-gate-watch` re-check reports it); `release-gate-guard.sh outgoing` path for CWFTs;
`release-gate-watch.yml` `diff` as detector for everything (incl. P5b/P6).
Composition: each hook runs the calendar check *in addition to* existing checks
(AND). An exception argument is consumed only by the calendar check.

### 4. Exceptions: reuse the MFA ledger, do not build a second authority

An exception is a decision record in the existing mctl-api release ledger
(`/api/v1/release/grants` lineage, #1022): human, fresh MFA via the decide page,
bound to {scope, environment, repository, digest, reason class, not_after <=
max_exception_ttl}, single use. `release-window.py` only *verifies* it, exactly
like `release-ledger-shadow.py gate` verifies a release decision. Agents may
call a future `request_exception` that creates a *pending* request; it can never
approve. Every consumed exception produces a post-freeze review item.

### 5. Argo CD sync windows (Phase 3, secondary defence)

Generate `spec.syncWindows` for `project-apps.yaml` / `project-platform.yaml`
from `release-windows.yaml` (generator + CI drift check, never hand-edited).
Purpose: cover effect-time (commit before freeze, reconcile during) and UI/CLI
syncs (part of P8). Known limits to verify with an inert kind/k3d fixture
(task 3): windows use cron + duration, not RRULE, so the policy RRULE subset
must be translatable or refused; deny blocks auto-sync and selfHeal (drift
persists through the freeze); `manualSync: true` re-opens manual syncs to
anyone with sync RBAC; AppProject editors and `argocd --core` users bypass;
it does not stop commits to `main` nor `kubectl`. Hence never primary.

### 6. Read-only view and agent interface (Phase 2/4)

`release-window.py list` output rendered as a static ICS + markdown table
published by CI; later read-only MCP tools `list_release_windows`,
`check_release_window`, `explain_release_block` in mctl-api reading the same
file from main. The view shows coverage labels per write path. It holds no
state of its own and is never an approval source.

### Decision matrix

| Criterion | A: Argo sync windows + thin PaC | B: extend release-gate tooling | C: external product | D: hybrid (B primary + generated A) |
|---|---|---|---|---|
| Safety (no 2nd authority) | good | good (reuses ledger) | poor (second engine/approvals) | good |
| Enforcement coverage | effect-time syncs only; not commits, not kubectl | all write points that already run gates; not P5b-P8/P12 | only paths it drives | union of A and B |
| Bypass resistance | AppProject edit / manualSync / core | deploy-key bypass (#2543) | MCTL paths bypass it | best, still not P8 kubectl |
| Operator UX | Argo UI shows windows | needs view (ICS/table) | rich | view from one file |
| Cost | none | none | licence + integration (to verify) | none |
| Implementation burden | low, but cron-only, lag semantics | medium | high | medium-high, phased |

## Alternatives

- **A alone (ADOPT_ARGO_SYNC_WINDOWS):** dropped as primary: does not refuse the
  GitOps write, so a freeze leaves a pending commit that applies the moment the
  window ends (surprising), blocks selfHeal during the freeze, and is bypassed
  by AppProject edits and `manualSync`. Kept as Phase 3 secondary.
- **C (Octopus Deploy / Harness / GitLab deploy freezes):** dropped: each only
  governs deployments it executes; GitLab's freeze periods are, to our
  understanding, an advisory `CI_DEPLOY_FREEZE` variable jobs must honour;
  Octopus/Harness freezes sit in paid tiers (to verify against current primary
  docs, task 9). Useful only as reference semantics (recurrence, exceptions).
- **B alone (BOUNDED_CALENDAR_MVP):** viable and is Phases 0-2 of this plan;
  dropped as the end state only because it cannot act at Argo effect time.
- **DEFER_UNTIL_GATES_CLOSED:** the conservative alternative; this design
  already defers *enforcement claims* for BLOCKING-UNKNOWN paths, and its P0 is
  read-only, so it subsumes deferral while still producing the inventory.

## Platform impact

- Migrations: none in this spike. Later phases add one file, one script, tests,
  and steps in workflows that are in `protected_re` (reviewed PRs).
- Backward compatibility: shadow mode first; an absent `release-windows.yaml`
  is "no calendar policy" only until the file exists; once introduced it becomes
  required (same as `version_holds`).
- Resource impact: negligible CI time; no cluster resources until Phase 3.
- Risks and mitigations:
  - False sense of safety -> per-path coverage labels; no "enforced" claim for P5b/P6/P7/P8/P12.
  - Freeze blocks a needed hotfix/rollback -> MFA single-use exceptions; rollback carve-out per window; rollback in `mode: shadow` until exceptions are proven live.
  - Policy outage freezes everything in enforce -> fail-closed is intended; recovery is a reviewed PR setting `mode: shadow` (as with the ledger).
  - Start/end race (check passes at T, push lands after freeze start) -> effect interval with margin; re-check before every push attempt; watcher detects.
  - Ledger wait (up to 60 min) crossing a freeze boundary -> calendar re-checked after `ledger-gate`, at push time, not only at preflight.
  - DST/timezone bugs -> UTC evaluation, `zoneinfo`, fixtures for both transitions.
