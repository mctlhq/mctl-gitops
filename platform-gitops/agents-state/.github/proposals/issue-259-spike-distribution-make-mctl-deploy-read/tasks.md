# Tasks: issue-259-spike-distribution-make-mctl-deploy-read

- [ ] 1. Pin evidence: record 40-hex heads of `mctlhq/.github`, `mctlhq/mctl-api`, `mctlhq/mctl-gitops`, `mctlhq/mctl-docs`, `mctlhq/mctl-web` and the access date of the Anthropic directory/connector docs — DoD: "Evidence pins" table in `docs/spikes/mctl-deploy-claude-directory.md`, with unread sources listed as `unknown (not observed)`.
- [ ] 2. D2 requirements snapshot (depends on 1) — DoD: dated list of current Anthropic requirements (OAuth 2.0, Streamable HTTP, MCP version, tool names <= 64, `title`/`readOnlyHint`/`destructiveHint`, errors, token frugality, submission fields) with URLs; no endorsement claims.
- [ ] 3. D1 current-state matrix (depends on 1) — DoD: twelve Phase A rows `requirement | current implementation | evidence | gap | owner/issue`, from mctl-api code (MCP registration, annotations, OAuth/well-known handlers, audience and tenant checks, rate limits, audit), unauthenticated live-safe probes of `https://api.mctl.ai/mcp` and its OAuth metadata, and the non-admin tool-list observation (full catalogue incl. `confirm` tools offered to `agent:issue-investigator`, `Teams: []`); every row tagged.
- [ ] 4. D3 MCTL Deploy surface (depends on 3) — DoD: table of the eight candidate tools mapped to canonical #254 names and existing tools (`mctl_deploy_analyze`, `mctl_get_service_status`, `mctl_get_service_logs`, ...), each with annotation, visibility, authority, response bound; classification of every currently discoverable tool; list of tools with a `confirm` parameter routed to #254 `grants`; `tools/list` byte size and token estimate for current vs. proposed surface with method; filtering-vs-new-endpoint recommendation.
- [ ] 5. D4/D5 Claude connector protocol and golden-path report (depends on 4) — DoD: one row per Phase C step 1-13 and per negative test, status `PASS`/`FAIL`/`BLOCKED (#254:<item>)`/`unknown (not observed)`, evidence as identifiers only; steps needing #254 `plan`, `grants`, `deploy-record`, `preview-onboard`, `health-gate`, `promote-rollback-tools` marked BLOCKED; no shadow flow.
- [ ] 6. Phase E first-user script and score sheet (depends on 5) — DoD: prompts 1-5 and the nine metrics as a table; live values `unknown (not observed)` until a human runs it; support and plugin-bundle recommendations stated.
- [ ] 7. D6 compliance matrix and D7 draft packet (depends on 2, 3, 4) — DoD: PASS/FAIL/UNKNOWN per Phase D item with owner issue per gap; draft packet text for name, value proposition, description, use cases, read/write and auth disclosure; missing privacy/terms/support/branding/reviewer-account items listed as gaps, no legal text invented.
- [ ] 8. D8 verdict and D9 follow-up map (depends on 5, 6, 7) — DoD: exactly one provisional verdict with reasoning re-derived from evidence; D9 rows `gap | owning repo | existing issue | extend/create | blocks custom connector? | blocks directory submission?`, new issues proposed only for gaps not owned by #254, #236/#237/#241, #243, mctl-agents#597.
- [ ] 9. Add `roadmap/spikes/mctl-deploy-claude-directory.yaml` (depends on 8) — DoD: SpikeDefinition bound to `mctlhq/.github#259`, outcomes `READY_TO_SUBMIT, READY_AFTER_SMALL_GAPS, BLOCKED_ON_AGENT_DEPLOY, REVISE_CONNECTOR_SURFACE, NO_GO`, `lifecycle: active`, `timebox.decisionBy: "2026-12-15"`, `execution.devloop: true`, `evidence.report` set, no `decision`.
- [ ] 10. Add the report link under `# Spikes` in `AGENTS.md` (depends on 1) — DoD: one bullet matching existing style.

## Tests

- [ ] T1. `pip install -r roadmap/requirements.txt && python roadmap/scripts/validate.py` passes, including the new spike.
- [ ] T2. `python -m pytest roadmap/tests` passes unchanged (in particular `test_validate_spike.py`).
- [ ] T3. Grep the report for token-like strings (`Bearer `, `ghp_`, `eyJ`, `client_secret`) returns nothing.
- [ ] T4. Every D6 row with FAIL/UNKNOWN has an owner issue; every PASS row has a tagged evidence reference (manual review checklist in the PR description).
- [ ] T5. The report contains exactly one verdict string in D8 and it is one of the manifest `outcomes`.

## Rollback

Revert the PR: it only adds `docs/spikes/mctl-deploy-claude-directory.md` and
`roadmap/spikes/mctl-deploy-claude-directory.yaml` and edits one line of `AGENTS.md`.
No runtime, gitops or Anthropic-side state is touched, so revert is complete.
