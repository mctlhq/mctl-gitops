# Tasks: issue-2828-spike-release-governed-release-calendar

Nothing below may start without an explicit owner GO on this proposal. Phase 0
is read-only/inert. Enforcement tasks additionally need the owner's security
decision recorded in a reviewed PR. Follow-ups map to existing issues first
(#2528, #2543, #2652, #970, mctl-api#1022, .github#181, .github#254,
mctl-agents#217); new issues only after a separate owner GO.

## Phase 0 - read-only inventory and inert prototype

- [ ] 1. Re-verify the write-path inventory for a calendar (extend `docs/runbooks/mctl-api-release-hold.md` with a "calendar coverage" column, or a sibling runbook) using read-only access: ruleset 18465404 bypass list, deploy keys, live AppProjects, Argo CD version — DoD: every path P1-P13 plus "commit before freeze, reconcile during" labelled enforced / observed-only / unknown with a cited source and date; failed reads recorded as unknown.
- [ ] 2. Measure propagation lag from existing `argocd-freshness.yml` run history (read-only) — DoD: p50/p95/max commit-to-resolved times documented; `propagation_margin` value justified or the open question kept.
- [ ] 3. Inert Argo CD sync-window experiment on a local kind/k3d cluster (never production): deny vs allow precedence, `manualSync`, selfHeal during deny, in-flight sync at window start, `timeZone`, ApplicationSet-generated apps — DoD: script + recorded results in the proposal follow-up; no live cluster touched.
- [ ] 4. Write the policy schema (JSON Schema) and illustrative `release-windows.yaml` as a test fixture only (under `tests/fixtures/release-windows/`), not under `platform-gitops/` (depends on 1) — DoD: schema covers scope, effect, timezone, rrule subset, one-off start/end, duration, owner, issue, rollback_allowed, mode, default, propagation_margin, max_exception_ttl.
- [ ] 5. Prototype `scripts/release-window.py` (`check`, `diff`, `explain`, `list`, `--selftest`) with injected clock and exit 0/6/7 (depends on 4) — DoD: deterministic fixtures T1-T14 pass; not wired into any workflow.
- [ ] 6. Decide how Argo CWFTs (sh + yq, no python) evaluate windows: python step image vs mctl-api read endpoint — DoD: decision recorded with the failure mode when the evaluator is unreachable (must refuse in enforce).
- [ ] 7. Product comparison from current primary docs (Argo CD sync windows, Octopus deployment freezes, Harness freeze windows, GitLab deploy freezes): capability, enforcement point, licence tier, lock-in — DoD: table with doc URLs and access date; corrects any "to verify" claim in design.md.
- [ ] 8. Independent proposal review (not the investigator) and owner decision among HYBRID / BOUNDED_CALENDAR_MVP / DEFER_UNTIL_GATES_CLOSED — DoD: decision recorded on #2828.

## Phase 1 - shadow evaluation (after owner GO)

- [ ] 9. Add `platform-gitops/release-windows.yaml` with `mode: shadow`, `default: allow`, and no windows or owner-provided windows only; add it and `scripts/release-window.py` to `auto-merge.yml` `protected_re` and `test_auto_merge_protected_paths` (depends on 5, 8) — DoD: reviewed PR merged; validate green.
- [ ] 10. Wire shadow reports into `release-deploy.yaml`, `gitops-bump.yaml` (preflight and before each push), `validate-manifests.yml`, and `release-gate-watch.yml` `diff` (depends on 9) — DoD: run summaries show the calendar verdict; nothing refused.
- [ ] 11. Publish read-only view: generated markdown table + ICS from `release-window.py list` as a CI artifact, with per-path coverage labels (depends on 9) — DoD: artifact reproducible from main; no state outside git.

## Phase 2 - enforcement and exceptions (after security decision)

- [ ] 12. Exception decision kind in the mctl-api release ledger (owner: mctl-api, under mctl-api#1022): human, fresh MFA, exact scope+digest, TTL <= max, single use, reason class — DoD: mctl-api issue/PR with its own review; no agent path can approve.
- [ ] 13. `release-window.py` verifies exceptions read-only like `release-ledger-shadow.py gate`; consumed exceptions open a post-freeze review item (depends on 12) — DoD: T9-T12 pass against fixtures and a staging ledger.
- [ ] 14. Flip `mode: enforce` in a reviewed PR recording the owner decision, only for paths labelled enforceable in task 1 (depends on 10, 13) — DoD: a test deny window in a non-critical scope refuses a test bump; rollback documented.
- [ ] 15. CWFT hook in `release-gate-guard.sh`-style step for `wft-deploy-service`, `wft-rollback-*`, `wft-promote-deployment`, `tpl-git-commit` (depends on 6, 14) — DoD: `tests/test_release_gate_guard.py`-style tests for refusal and unknown.

## Phase 3 - Argo CD secondary defence

- [ ] 16. Generator from `release-windows.yaml` to AppProject `syncWindows` (cron + duration translation, refuse untranslatable rules) with CI drift check; `manualSync: false` (depends on 3, 14) — DoD: generated output matches fixtures; drift check fails on hand edits.

## Phase 4 - agent integrations

- [ ] 17. Read-only MCP tools `list_release_windows`, `check_release_window`, `explain_release_block` in mctl-api; optional `request_exception` that only creates a pending human decision (depends on 11, 12) — DoD: tool cannot approve; covered by mctl-api authz tests; DevLoop/agent-native deploy (.github#254) calls `check_release_window` before deploy.

## Tests

- [ ] T1. No window matches -> `default` applies; `default` missing -> refuse (enforce) / unknown (shadow).
- [ ] T2. Half-open boundaries: instant == start refused, instant == end allowed.
- [ ] T3. DST spring-forward: window at a non-existent local time starts at the next existing instant.
- [ ] T4. DST fall-back: deny window at an ambiguous local time covers both occurrences.
- [ ] T5. Overlapping allow and deny for one scope -> deny.
- [ ] T6. Allow windows present, write outside them -> refused.
- [ ] T7. Partial freeze: deny on scope X does not refuse a write to scope Y; a grouped release touching X and Y is refused as a whole.
- [ ] T8. Start/end race: check at T passes, effect interval `[T, T+margin]` crosses freeze start -> refused.
- [ ] T9. Exception valid for exact scope+digest -> calendar refusal lifted, ledger/version-hold refusal still applies.
- [ ] T10. Exception for another digest, scope or environment -> refused.
- [ ] T11. Expired or already-consumed (replayed) exception -> refused.
- [ ] T12. Unreadable exception store -> refused (exit 7 in watcher, refusal at write).
- [ ] T13. Policy file malformed (duplicate key, bad timezone, unsupported RRULE part) -> refuse in enforce, unknown in shadow.
- [ ] T14. Policy read from `origin/main`, not from the commit under test (a PR that deletes its own freeze is still judged by main's policy).
- [ ] T15. Commit pushed before freeze, Argo reconcile during freeze: documented outcome per phase (Phase 1-2: applies; Phase 3: held by sync window) and asserted in the kind fixture.
- [ ] T16. Rollback during freeze with `rollback_allowed: false` needs an exception; with `true` passes only for a previously-healthy deployment.
- [ ] T17. Direct push via deploy key during freeze is detected by `release-gate-watch` (detector) and reported as such, never as prevented.
- [ ] T18. Mutation tests in the style of `tests/test_release_gate_ledger_hold.py` (each guard removed -> some test fails).

## Rollback

- This spike changes nothing live; rejecting the proposal is the rollback.
- Phase 1: revert the PR adding `release-windows.yaml` and the shadow steps; no deploy depends on them.
- Phase 2: a reviewed PR sets `mode: shadow` (same recovery as the ledger in `release-gates.yaml`); exceptions remain available for audit but are not required.
- Phase 3: a reviewed PR removes generated `syncWindows` from the AppProjects; Argo CD resumes normal auto-sync. Emergency: `argocd --core` break-glass per `infrastructure/k3s-preview/README.md`, followed by a reviewed PR and postmortem.
- Never roll back by weakening `version_holds`, the ledger or `protected_re`.
