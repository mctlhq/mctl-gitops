# Governed release calendar: deployment freezes, release windows and audited exceptions (research spike)

## Context

Issue mctlhq/mctl-gitops#2828 asks for a research spike: what is the smallest safe
architecture for an operator-visible release/change calendar that *enforces*
(not merely displays) deployment freezes across MCTL's existing GitOps and
governed release paths. It must reuse the existing release governance
(`platform-gitops/release-gates.yaml`, `scripts/release-gate.py`,
`scripts/release-preflight.py`, `scripts/release-ledger-shadow.py`, the
MFA-backed mctl-api release ledger in `enforce` mode since 2026-11-18) and must
not create a second approval authority, a new deployment engine, or any live
change. The deliverable is evidence-backed requirements/design/tasks that stop
at `status=proposed` for independent review and an explicit owner decision.

This matters because today MCTL has *version* holds (exact version/digest needs
an owner GO) but no *temporal* policy: nothing refuses a release because of
when it happens. The write-path inventory in
`docs/runbooks/mctl-api-release-hold.md` already shows several BLOCKING-UNKNOWN
bypasses (P5b/P6 deploy-key push to `main`, P7 chart tracking `main`, P8 Argo
CD/kubectl overrides, P12 spoofable `validate` context). A calendar that claims
to "enforce" a freeze would inherit exactly those gaps, so the proposal has to
be honest about coverage before any enforcement is switched on.

Recommended decision outcome: **HYBRID**, delivered in phases, with
enforcement gated: a canonical MCTL policy file judged at the existing GitOps
write points (option B as primary), shadow mode first, Argo CD `syncWindows`
generated from the same file only as a later secondary defence (option D), and
no enforcement claim for any write path that `mctl-api-release-hold.md` still
marks BLOCKING-UNKNOWN. Until the owner's security decision, the effective
outcome is `REUSE_EXISTING_ONLY` + read-only inventory (P0).

## User stories

- AS the platform owner I WANT to declare recurring and one-off deployment freezes in a reviewed GitOps file SO THAT production changes are refused during those periods without trusting each operator or agent to remember.
- AS an operator I WANT to see the current and upcoming freezes and why a specific deploy was refused SO THAT I can plan releases and not guess at failures.
- AS an on-call engineer I WANT a bounded, MFA-backed, single-use exception for an exact service and digest SO THAT I can ship a hotfix or rollback during a freeze without disabling the freeze for everyone.
- AS a security reviewer I WANT each production write path labelled enforced, observed-only or unknown for the calendar SO THAT the freeze is never advertised as stronger than it is.
- AS an AI agent (DevLoop, deploy tools) I WANT read-only `check_release_window` / `explain_release_block` answers SO THAT I stop before attempting a refused deploy, without ever being able to grant myself an exception.

## Acceptance criteria (EARS)

Policy and evaluation
- WHEN a release write point (release-deploy `bump`/`publish-*`, gitops-bump `bump`/`publish-*`, Argo `wft-deploy-service`/`wft-rollback-*`/`wft-promote-deployment` before push, `validate-manifests.yml` on a PR) evaluates a change THE SYSTEM SHALL read the window policy from `origin/main` (never from the commit under evaluation), as `release-gate.py` does with `--policy-rev origin/main`.
- WHEN the policy evaluates an instant THE SYSTEM SHALL compute in UTC, treat every window as half-open `[start, end)`, expand recurrences in the window's declared IANA timezone, and report the result with both the UTC instant and the local display time.
- WHEN a recurring local time is ambiguous (DST fall-back) THE SYSTEM SHALL cover both occurrences for a deny window and only the later occurrence for an allow window; WHEN a local time does not exist (DST spring-forward) THE SYSTEM SHALL shift it forward to the first existing instant. Both rules SHALL be covered by fixtures.
- WHEN a deny window and an allow window overlap for the same scope THE SYSTEM SHALL refuse (deny wins); priority numbers SHALL NOT be able to turn a deny into an allow.
- WHEN no window matches a change THE SYSTEM SHALL apply the policy's explicit `default` (`allow` initially); the default SHALL be a required field.
- IF the policy file is absent, unparseable, has a duplicate key, an unknown field, an invalid timezone or an invalid recurrence THEN THE SYSTEM SHALL refuse (exit 6) in `enforce` mode and report "unknown" (exit 7, non-blocking) in `shadow` mode; a failed read SHALL never be reported as "no freeze".
- WHEN a write is evaluated THE SYSTEM SHALL judge the expected effect interval `[now, now + propagation_margin]` (margin from the policy, initially 15 minutes, justified by #970 and `timeout.reconciliation: 180s`), and refuse if any part of it falls in a deny window.

Composition with existing gates
- WHILE a version hold, gate group, ledger requirement or `min_tag` refuses a change THE SYSTEM SHALL keep refusing it regardless of any calendar allow window or exception (the calendar can only add refusals; logical AND).
- WHEN a calendar exception is presented THE SYSTEM SHALL lift only the calendar refusal for the exact service, environment, image repository and digest it names, and SHALL leave every other check of `release-gate.py` and `release-ledger-shadow.py gate` unchanged.
- THE SYSTEM SHALL NOT read any approval from the calendar view, ICS feed, MCP read tool or chat message; exceptions SHALL be decided only as MFA-backed human decisions in the existing mctl-api approval mechanism (#1022 lineage).

Emergency exceptions
- WHEN an exception is used THE SYSTEM SHALL require: a human approver identity with fresh MFA, an exact scope (service, environment) and exact digest, a TTL no longer than the policy's `max_exception_ttl` (initially 4 hours), a reason class (`hotfix` or `rollback`), and single use (consumed on the first successful write).
- IF an exception is expired, consumed, bound to a different digest or scope, or cannot be read THEN THE SYSTEM SHALL refuse the write.
- WHEN a rollback targets a deployment previously observed healthy (as `wft-rollback-revision` requires) THE SYSTEM SHALL still require an exception during a freeze unless the policy explicitly lists `rollback_allowed: true` for that window; the default SHALL be false.
- WHEN an exception is consumed THE SYSTEM SHALL emit an audit record and open a post-freeze review item linking the exception, the write commit and the workflow run.
- THE SYSTEM SHALL NOT auto-open, auto-approve or agent-approve an exception.

Detection and visibility
- WHEN a push to `main` changes a production image tag/digest during a deny window without a consumed matching exception THE SYSTEM SHALL fail `release-gate-watch.yml` (detector, not guard) and alert through the existing workflow_failed channel.
- WHEN an operator or agent queries a window THE SYSTEM SHALL return the active window(s), next transition, matching scope and the exact rule that would refuse a proposed deploy.
- WHILE a write path is labelled BLOCKING-UNKNOWN in `docs/runbooks/mctl-api-release-hold.md` THE SYSTEM SHALL label calendar coverage for that path as "not enforced" in every view and report.

Rollout
- WHEN the policy is first introduced THE SYSTEM SHALL run in `mode: shadow` (report only) and SHALL switch to `enforce` only through a reviewed PR recording the owner's decision, mirroring the ledger `mode` precedent in `release-gates.yaml`.
- THE SYSTEM SHALL keep the new policy file and its evaluator in `auto-merge.yml` `protected_re` so no bot-approved PR can change them.

## Out of scope

- Implementing, merging or deploying anything from this spike; creating any production freeze, calendar event or grant.
- Changing `release-gates.yaml`, `release-gate.py`, the ledger mode, ArgoCD AppProjects or rulesets.
- A new CD engine or adopting Octopus Deploy / Harness / GitLab as the release engine.
- Rewriting DevLoop, the merge queue or ADR-006 (merge, deploy, monitor).
- Closing #2543 (deploy-key bypass) or the admission-policy work; this proposal depends on them, it does not do them.
- Inventing a holiday/weekend calendar; such windows are owner-configured data.
- Non-production (preview namespaces) freezes in the first phases.

## Open questions

- Owner decision: which outcome (`HYBRID` recommended, `DEFER_UNTIL_GATES_CLOSED` as the conservative alternative) and whether P0 enforcement may start before #2543 closes P5b/P6.
- Scope of "production": all `platform-gitops/services/*/*` plus `bootstrap/templates/mctl-platform/*`, or only a listed set of services? Tenant-owned services (`karabu`, `namax66`, `redloop`, `labs`) may need tenant-owned windows.
- Should a freeze also block non-image changes (values, templates, RBAC, ArgoCD specs)? This proposal starts with image tag/digest writes only, because those are the only ones the gate tooling already parses deterministically.
- Can the existing mctl-api release-ledger decision type carry a "calendar exception" kind, or does it need a new decision kind? Requires mctl-api owner input (#1022).
- Propagation margin value: 15 minutes is a starting point derived from #970 and `timeout.reconciliation: 180s`; no measured distribution was read in this run.
- Argo CD sync-window behaviour (deny vs in-flight sync, selfHeal during deny, manualSync, timezone field, `andOperator`) and current product licensing for Octopus/Harness/GitLab were not verified against primary docs in this run; they must be verified (tasks 3 and 9) before Phase 3.
- Deployed state could not be fully observed: `mctl_list_tenants` was refused (non-admin caller). Live ArgoCD AppProjects and ruleset 18465404 were not read.
- Alert-triggered ("incident") freezes: should an open critical incident create an automatic deny window? Recommended no for now (would be a non-human policy writer); recorded for owner decision.
