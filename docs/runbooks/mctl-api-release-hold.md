# mctl-api release hold: write-path inventory

Tasks 1, 12 and 16 of the #2528 design (PR #2589). Facts are read from the
repository on `main` (56c31ec6 plus the #2596 merge) and from `gh api`; where
something could not be observed it is marked so. This document grants nothing
and releases nothing.

Status legend: **KNOWN-ENFORCED** (a check refuses the write at the point of
effect), **KNOWN-NOT-A-PATH** (the code cannot write the guarded file),
**BLOCKING-UNKNOWN** (a writer exists that the current checks do not stop).

## What is enforced today

`platform-gitops/release-gates.yaml` carries `version_holds` (line 38): hold
`mctl-api-bootstrap` guards the image tag in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` (tag at line
45) from `held_from: "4.155.0"` with `allow: []` (lines 44, 50), so no version
at or above 4.155.0 can be written until a reviewed PR adds an allow record.

- Before the write: `scripts/release-gate.py check` in the bump script
  (`release-deploy.yaml:354`, `gitops-bump.yaml:239`).
- At the push, on the exact tree: `release-gate.py verify --policy-rev
  origin/main` in `publish-direct` (`release-deploy.yaml:598`, inside
  `release_gate()` called before every attempt; `gitops-bump.yaml:485`) and in
  `publish-pr` (`release-deploy.yaml:701`, `gitops-bump.yaml:564`).
- On every PR and on `main`: `validate-manifests.yml:597-598`.
- After the fact, on every push to `main` and daily:
  `release-gate-watch.yml:60` (`diff`) and `:82` (`verify`).

## Write paths to the guarded file

| # | Path | Can write the bootstrap tag? | Layer that covers it | Status |
|---|---|---|---|---|
| P1 | `release-deploy.yaml` (dispatched by the mctl-api release flow, or by hand). `bump` job `:199`; direct push in `publish-direct` `:543`; PR route in `publish-pr` `:629` | yes, direct push or a `release-bump/*` PR | hold check before the write, verify before every push, `validate` on the PR | KNOWN-ENFORCED |
| P2 | `gitops-bump.yaml` (any holder of `actions: write` on mctl-gitops). `bump` `:96`, `publish-direct` `:446`, `publish-pr` `:493` | yes | same | KNOWN-ENFORCED |
| P3 | Human PR to `main` | yes | review plus `validate` (verify runs on the PR tree) | KNOWN-ENFORCED |
| P4 | `claude/*` PR auto-merged on a bot approval | yes | `auto-merge.yml` `protected_re` (line 82) lists the gate files and the two bump workflows; `validate` | KNOWN-ENFORCED for the gate files. Whether `mctl-api.yaml` itself is in `protected_re` was not confirmed: it is not named in the pattern, so a `claude/*` PR that only changes the tag is held back by `validate` alone |
| P4b | `release-bump/*` PR opened by the `mctl-gitops-pr` App and auto-merged (`auto-merge.yml:33-41`) | yes, a tag line | diff guard (tag/digest lines only, forward moves), `validate` runs `release-gate.py verify`, route limited to `ghcr.io/mctlhq/mctl-api` in `release-bump-routes.yaml` | KNOWN-ENFORCED; first live use not yet observed |
| P5a | Argo `wft-deploy-service`, `wft-rollback-service`, `tpl-git-commit` as written | no: paths are `platform-gitops/services/${TEAM}/${COMPONENT}/values.yaml` (`wft-deploy-service.yaml:399`, `wft-rollback-service.yaml:131`, `tpl-git-commit.yaml:342-345`); `release-gate-guard.sh outgoing` (`wft-deploy-service.yaml:457`) covers gated groups only | n/a | KNOWN-NOT-A-PATH for the template code |
| P5b | Write deploy key `argo-workflows-bot-2026-10` (id 166128843) used outside the template code | yes: the ruleset 18465404 bypass entry (`DeployKey`, `actor_id: null`, `always`) lets it push any path to `main` with no PR and no check | none at push time; `release-gate-watch.yml` detects after the fact | **BLOCKING-UNKNOWN** until #2543 |
| P6 | mctl-agents CWFT `commit-and-push` steps (deploy-key push to `main`) | the credential can push any path; template code scopes `git add` to `agents-state/**` | template guard only | **BLOCKING-UNKNOWN** with P5b (same credential class) |
| P7 | Chart `targetRevision: main` for mctl-api `helm/` (`mctl-api.yaml:11`; the second source at `:583` also tracks `main`) | yes, with no GitOps write: any chart change merged to mctl-api `main` applies on the next sync (auto-sync with `selfHeal`, `mctl-api.yaml:641-644`) | none | **BLOCKING-UNKNOWN**. The planned pin to the 4.154.0 commit (task 6) is not neutral: see below |
| P8 | Argo CD UI/CLI parameter override, `kubectl set image/env` by cluster admins | yes | `selfHeal` reverts drift but not a disabled auto-sync | **BLOCKING-UNKNOWN**; needs the admission policy (task 10) |
| P9 | Runtime Secret keys from the zitadel-iac Job (`envFromOptionalSecrets`) | yes, via `envFrom` (this is how the orchestrator identity would have switched on; #2591 removed that entry) | none beyond review | KNOWN-ENFORCED in git for the entry removed by #2591; other optional Secrets are not scanned: **BLOCKING-UNKNOWN** |
| P10 | Vault value change on an existing `secretKey` | values only, not env names | n/a | KNOWN-NOT-A-PATH for new flag names |
| P11 | Any other workflow on `main` that names `environment: gitops-bump` and so receives `GITOPS_BUMP_DEPLOY_KEY` | yes (direct push) | today only the two bump workflows use it (`release-deploy.yaml:547,562`, `gitops-bump.yaml:453,467`); `protected_re` covers `.github/workflows/` edits to those two files and `test_gitops_write_credential_holders` pins the holder list | KNOWN-ENFORCED by that test |
| P12 | Required context `validate` (integration 15368) satisfied by a PR-defined job of the same name | yes, as a merge gate | none | **BLOCKING-UNKNOWN**: the App-bound `release-hold` context (task 14) is not built |
| P13 | `portal-allowlist-vendor.yml` (`:62`) and `cloudflare-drift.yml` (`:728`), both environment `app-gitops-pr` | no direct write; PR flow | PR controls | KNOWN-NOT-A-PATH for direct writes |

### P7: the pin is not neutral (found 2026-11-11)

`helm template` of the live bootstrap values against the mctl-api chart at tag
4.154.0 (a11b54d7) and at `main` (a5b9ef9c) differs in exactly one rendered
block: `main` adds the ingress path `/devloop` (service `mctl-api`, port 8080).
The live Ingress already carries `/devloop` (read-only `kubectl get ingress`).
Pinning `targetRevision` to the 4.154.0 commit would therefore remove a path
from production at the next sync. The chart changed between the two revisions
in `helm/templates/deployment.yaml`, `helm/templates/ingress.yaml`,
`helm/values.yaml` and `helm/render_test.go`; only the ingress path changes the
rendered output with the live values. A pin to the current `main` commit renders
identically to production by construction and still stops later chart changes
(for example the glovo ingress paths in mctl-api#1017) from applying without a
GitOps change. That choice, and moving the pin together with the tag at release
time, is the owner's call (task 6 is not done).

## Dependency map (task 12)

Each row says whether a machine reads it. "machine-checked: no" is the
owner's judgement, not a gap in code.

| Item | Role | machine-checked |
|---|---|---|
| mctl-api#934 | release PR for 4.155.0, Draft hold | no (the tag is held by `version_holds`, the PR state is not read) |
| mctl-gitops#2523 | docs-only dark rollout plan | no |
| mctl-agents#993 Part M | grant-pinned implement tokens, worker compatibility | no |
| mctl-agents#992 Part S | storage and slot compatibility | no |
| mctl-agents#1007 B4 | worker group marker rollback and floor | yes: `release-gates.yaml` group `mctl-agents-workers` (`min_tag`, `requires`) |
| mctl-api#935 | lease drain | no |
| mctl-gitops#1040 | reviewer aggregate gate | no |
| mctl-gitops#1292 | release signal watcher | no |

## Relation to #2543 (task 16)

- The PR route (`mctl-gitops-pr`, #2595/#2596) gives release bumps for
  `ghcr.io/mctlhq/mctl-api` a path that does not push to `main`. It does **not**
  remove any bypass: ruleset 18465404 still lists the `DeployKey` entry, the two
  write deploy keys still exist, and every image outside the route list still
  pushes directly.
- P5b and P6 stay BLOCKING-UNKNOWN. They turn into enforced only when a #2543
  stage lands: a broker that runs the hold check before pushing, or a no-bypass
  path restriction proven in a disposable repository. Until then the release
  decision packet carries D3 (the owner's written acceptance of the residual
  risk), and `release-gate-watch.yml` is a detector, not a guard.

## Reconciliation with the #2590 gate (tasks 2-5, 8, 9 not implemented)

`release-hold.py` as designed in #2589 would duplicate what `version_holds` in
`release-gate.py` already does, so it was not written. Stacking a second tool on
the same file would give two readers of one bootstrap values block (the design
itself requires one reader, tasks note "does not write a second reader").

Already enforced by #2590 / #2595 (see "What is enforced today"):
- a held tag cannot be written or pushed without a recorded allow naming exactly
  that version (design checks on hold and version);
- the allow record carries `grant`, `approved_by` and `expires`, and expiry gates
  new writes only;
- every unreadable input is a refusal (exit 7 for the watcher), including a failed
  read of the parent's held file;
- the check runs before the write, before every push attempt and after every
  rebase, on both routes (direct and PR), and again in `validate` and the watcher.

Not covered, and what each would take:
- **Digest and source binding** (design checks 4-8: grant added by an
  owner-merged PR, tag ref, GHCR manifest digest, `source_commit`, image
  `revision` label). The label is stamped from task 13; reading it needs GHCR
  and GitHub API reads at gate time, behind one injectable function. The
  smallest design that does not fork the tool is to add optional `digest` and
  `source_commit` fields to the `allow` record and have `release-gate.py` verify
  them, rather than a second script.
- **Runtime keys** (`MCTL_BRIDGE_*`, `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`
  in the bootstrap values or optional Secrets): the gate reads the image tag
  only. Same extension point.
- **Chart pin (P7)**, **admission policy (P8)**, **App-bound `release-hold`
  context (P12)**: separate work, see above.
- **Preflight advisory (task 5)**: `release-preflight.py` does not mention the
  hold; adding a notice is small but changes nothing at the point of effect.

Owner decision needed: extend `version_holds` (recommended) or build the second
tool the design describes.

## Not built (tasks 7, 10, 11, 14, 15)

- 7: `release-hold-pr.yml` and `release-hold-merge.yml`, the `release-hold`
  context and the extended `protected_re`.
- 10, 11: the ValidatingAdmissionPolicy and its later switch to Deny (needs one
  observed sync with no warnings and the live digest).
- 14: checker and merger Apps, their environments, and the ruleset change
  (owner actions; neither App may become a bypass actor).
- 15: the post-sync digest verifier CronJob.
