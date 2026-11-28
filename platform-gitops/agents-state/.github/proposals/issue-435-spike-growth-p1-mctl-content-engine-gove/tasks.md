# Tasks: issue-435-spike-growth-p1-mctl-content-engine-gove

Precondition (owner, not implementer): issue #435 is brought in line with the current
`.github/ISSUE_TEMPLATE/spike.yml` (title prefix `spike: `, `Source:`/`Question:`/
`Outcomes:`/`Lifecycle:`/`Related:`/`Why mctl:` lines, template labels) before the
DevLoop is approved, per `AGENTS.md`.

- [ ] 1. Pin evidence revisions. Record 40-hex commits for mctlhq/.github, mctl-gitops,
  mctl-web, mctl-telegram, mctl-docs, mctl-academy and mctl-agents. Read each public source
  that will be used. For any repo or issue that cannot be read, record
  `unknown (not observed)`. — DoD: the evidence pin table exists in the report, and every
  gap is listed.
- [ ] 2. CE0 inventory and reuse/no-build decision in `docs/spikes/content-engine.md`
  (depends on 1). — DoD: there is one canonical owner per artifact, each row has an
  evidence tag, existing blog/content paths are listed or marked unknown, and the
  manual-baseline vs workflow comparison is described. The report states that no new
  service, CMS, agent runtime or analytics plane is proposed.
- [ ] 3. Vendor benchmark section (Outrank, AirOps, LurkAPI, SerpWrap, Tavily) from
  public pages only (depends on 1). — DoD: each cell is dated and sourced or `UNKNOWN`.
  There are no compatibility or free-capacity claims and no accounts or purchases.
- [ ] 4. Pilot thresholds, budget, rubric and approval rules (depends on 2). — DoD: the
  numeric ceilings (proposed defaults: 90 reviewer minutes and USD 10 per article),
  reviewer != writer, exact-revision approval, the no-publish-on-reject rule, stop
  conditions, the 1-5 scoring rubric and the `INCONCLUSIVE (baseline not supplied)` rule
  are all written down.
- [ ] 5. Reference model `docs/spikes/content-engine/content_check.py` and its JSON
  schemas. — DoD: stdlib only, no network. It implements the brief, manifest, claim,
  secret, duplicate, consent and injection checks; findings are JSON lines; exit codes
  are 0 and 1; matched secrets are never echoed.
- [ ] 6. Fixtures: passing and negative (depends on 5). — DoD: negative fixtures exist for
  prompt injection, an unsupported claim, a private or non-allowlisted source, a
  secret-shaped string (built at test time), a duplicate canonical intent, and missing
  consent.
- [ ] 7. Three candidates under `docs/spikes/content-engine/candidates/`:
  `connect-telegram-mcp`, `mcp-apps-interop-matrix` and `secure-remote-mcp-server`. Each
  has a brief, sources, claims and a draft outline (depends on 1, 5). — DoD: each draft
  carries the draft banner and links the existing canonical onboarding. 100% of claim
  anchors are supported or qualified. Host cells not observed live are
  `UNKNOWN (not observed)`. All three pass `content_check.py`.
- [ ] 8. CE5 measurement proposal and backlog section (depends on 2). — DoD: per-property
  GSC 28-day windows, aggregate Umami (stats.mctl.ai), #433 first permitted MCP action,
  a 6-8 week review feeding OD-7, KEEP/ITERATE/STOP/INCONCLUSIVE, UNKNOWN for missing
  data and no growth guarantee. The mctl-telegram#1517 candidate and the hypotheses are
  recorded as backlog with evidence kept separate from inference.
- [ ] 9. `roadmap/spikes/content-engine.yaml` SpikeDefinition (depends on 2). — DoD:
  `lifecycle: proposed`, issue #435, outcomes `REUSE_DEVLOOP_PILOT`,
  `MANUAL_EDITORIAL_ONLY`, `EVALUATE_THIRD_PARTY`, `NO_GO`, `execution.devloop: true`,
  `evidence.report`, no `epic` and no `decision`. Validation passes.
- [ ] 10. Review-only diff to `roadmap/epics/organic-discovery-growth.yaml`. It appends the
  unbound `od-14-content-engine` (`required: false`, phase `intent`, dependsOn
  `od-0-baseline`, `od-4-telegram`, `od-5-hub`). — DoD: `git diff` shows only the appended
  block, and nothing is applied or reconciled.
- [ ] 11. Add the `AGENTS.md` `# Spikes` bullet for the report (depends on 2). — DoD: one
  bullet stating "proposed verdict" and the owner-only decision.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with
  the new spike and the epic diff.
- [ ] T2. `python -m unittest discover -s roadmap/tests -p 'test_*.py'` passes with no
  regressions.
- [ ] T3. `python -I -m unittest discover -s docs/spikes/content-engine` passes. Each
  negative fixture produces exactly its expected rule id and exit code 1. The passing
  fixtures exit 0.
- [ ] T4. An injection fixture shows that a directive in a snippet is flagged
  `untrusted-instruction` and changes no other check result.
- [ ] T5. A secret fixture shows the finding output contains the rule id and location
  but not the matched value.
- [ ] T6. `content_check.py` run on each of the three candidates exits 0.
- [ ] T7. A diff check shows that every pre-existing line of
  `organic-discovery-growth.yaml` is unchanged.

## Rollback

All changes are documentation, manifests and offline scripts in one PR, so reverting the
merge commit removes them completely. No runtime state, graph apply, deployment or
external account is created. If only the epic diff is unwanted, delete the appended
`od-14-content-engine` block. Nothing references it, because it is unbound and optional.
