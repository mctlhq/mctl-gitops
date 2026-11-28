# Design: issue-435-spike-growth-p1-mctl-content-engine-gove

## Current state

`mctlhq/.github` holds org governance, roadmap desired state and spike reports. It has no
content, blog or publishing code.

- `roadmap/epics/organic-discovery-growth.yaml` is the EpicDefinition for #349. It is
  `lifecycle: proposed`, and its header says "all work items are deliberately unbound"
  and that graph apply needs separate owner approval. It has work items `od-0-baseline`,
  `od-1-alice` (ext mctl-alice#174), `od-2-academy`, `od-3-docs`, `od-4-telegram` (ext
  mctl-telegram#784), `od-5-hub` (ext mctl-web#31), `od-shortlist`, `od-6-ai-discovery`
  (optional; ext mctl-web#215, .github#259) and `od-7-evaluation` (28-day GSC windows,
  keep-or-stop). There is **no OD-14 / content-engine item**. OD-14 is referenced only in
  the issue.
- `roadmap/schemas/spike-definition.schema.json`:
  - requires `title`, `question`, `lifecycle`, `github.issue` and at least 2 `outcomes`
    (pattern `^[A-Z][A-Z0-9_]*$`);
  - allows `epic`, `activation`, `timebox`, `evidence.report` and `execution.devloop`;
  - requires a `decision` only when the spike is `decided`.
- `roadmap/scripts/validate.py` (around lines 503-560) rejects `spec.epic` unless the named
  epic work item is bound to the same GitHub issue. Binding OD-14 to #435 would therefore
  change the "deliberately unbound" graph. This design leaves both unbound.
- Precedent spikes with a proposed verdict and an owner-only decision:
  - `roadmap/spikes/journey-intent-correlation.yaml` plus
    `docs/spikes/journey-intent-correlation.md`, which uses evidence tags `[CODE]`,
    `[CONFIG]`, `[LIVE]`, `[DOC]` and `unknown (not observed)`, plus an evidence-pin table;
  - `docs/spikes/finance-assistant/`, a stdlib Python reference model.
- `roadmap/tests/test_validate_spike.py` covers SpikeDefinition validation. CI runs it from
  `.github/workflows/roadmap-validate.yml` (see `roadmap/README.md`:
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and
  `python -m unittest discover -s roadmap/tests -p 'test_*.py'`).
- `AGENTS.md` lists each spike report under `# Spikes` and sets the spike-issue rules:
  current `spike.yml` template, the `Source:` dedup key, and verification before DevLoop.
- `.github/ISSUE_TEMPLATE/spike.yml` requires the title prefix `spike: `, a body with
  `Source:`, `Question:`, `Outcomes:`, `Lifecycle: proposed`, `Related:` and `Why mctl:`,
  and the labels `spike:scout` and `agents:intake`. Issue #435 as supplied does not
  conform (see Open questions).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-web/values.yaml`: ingress hosts `mctl.ru` and
  `mctl.ai`. `catalog-info.yaml` source-repo is `mctlhq/mctl-web`. `[CONFIG]`
- `services/labs/mctl-telegram/values.yaml`: hosts `tg.mctl.ai` and
  `labs-mctl-telegram.mctl.ai`. Source repo is `mctlhq/mctl-telegram`. `[CONFIG]`
- `services/admins/mctl-docs/values.yaml`: `docs.mctl.ai`. `services/labs/mctl-academy`:
  `academy.mctl.ai`. `services/labs/mctl-alice`: `alice.mctl.ai`. These are the
  expansion properties. `[CONFIG]`
- `services/admins/umami/values.yaml`: Umami runs at `stats.mctl.ai` and
  `admins-umami.mctl.ai`, with forward-auth on the admin host. It is an existing
  measurement source, so no new analytics is needed. `[CONFIG]`
- No Umami env or snippet line matched a grep of the mctl-web and mctl-telegram
  values.yaml files. Whether each property actually emits Umami events is **unknown (not
  observed)**. A grep miss in Helm values is not proof of absence, because the tracker
  may be configured in source.
- `mctl_get_service_status admins/mctl-web`: Synced/Healthy, image `7.24.0`. `[LIVE]`
- `mctl_get_service_status labs/mctl-telegram`: Synced/Healthy, image `0.151.0`,
  host `tg.mctl.ai`. `[LIVE]`
- Not observed: the source trees of mctl-web, mctl-telegram, mctl-docs, mctl-academy and
  mctl-agents (existing blog/content paths, Academy citation validator mctl-academy#83,
  AgentDefinitions); GSC data; the issues #433, #315, mctl-telegram#440/#683/#1152/#1517
  and mctl-web#215. CE0 must read them at pinned revisions. They are recorded as
  `unknown (not observed)`, never as absent.

## Proposed solution

This is a research-only spike delivered in `mctlhq/.github`. The proposal changes only
documentation, roadmap manifests and an offline reference model. Nothing runs in
production.

### 1. Spike report `docs/spikes/content-engine.md`

The report follows the `journey-intent-correlation.md` structure: non-claims, evidence
tags, an evidence pin table (40-hex commits), and a proposed verdict only.

- **CE0 inventory.** A table with these columns: artifact, candidate canonical owner
  repo/path, existing primitive reused, evidence tag. Rows:
  - brief: `docs/spikes/content-engine/briefs/` for the pilot only;
  - source manifest;
  - draft Markdown: the property repo canonical page, to be decided per property;
  - evidence review: the existing DevLoop independent review gate / review receipts;
  - destination URL and CTA: the property owner;
  - release controls: the existing CI and branch protection of each property repo;
  - repurposing: the Product Updates prepare flow mctl-telegram#440/#683;
  - measurement: GSC, Umami (stats.mctl.ai), #433 first permitted MCP action, and the
    OD-7 evaluation.

  The table also records a manual baseline vs workflow comparison of cost and steps.
- **Reuse/no-build decision.** The Content Scout is a brief template fed by
  human-reviewed #315 Product Scout source briefs; it is not a collector. The Technical
  Writer is the existing DevLoop implementer, run under a separately approved
  AgentDefinition/ExecutionProfile and budget. The reviewer is the existing independent
  review path. The editorial workflow is a Git draft PR in the property repo with
  exact-revision human approval and the existing release and rollback controls. Nothing
  new is deployed.
- **Vendor benchmark.** Outrank, AirOps, LurkAPI, SerpWrap and Tavily are compared from
  public pages, each with a retrieved date, on: terms, engines/geo/device, quotas,
  licensing/attribution, cost and fit. Every cell is either confirmed with a dated
  source or `UNKNOWN`. There are no purchases or accounts. GSC and public sources come
  first, and the vendors are optional.
- **Pilot controls and thresholds**, set before any pilot model execution. These are
  proposed defaults for the owner to confirm:
  - 100% of material claims supported or explicitly qualified;
  - 0 secret/PII findings and 0 duplicate canonical intents;
  - at most 90 reviewer minutes per article;
  - model spend per article at most USD 10, inside the approved provider budget;
  - 3 drafts for the pilot, and 2-3 per week only after a KEEP decision;
  - reviewer != writer;
  - approval bound to the exact head SHA and content digest;
  - rejected or changed content cannot publish; any later change needs re-approval;
  - stop conditions: a threshold breach, reviewer rejection of 2 of 3 drafts, or an
    owner stop.
- **Baseline comparison rubric.** Score 1-5 on source support, technical
  reproducibility, usefulness, duplication, review effort (minutes) and cost (USD). The
  comparison needs 3 human/manual baseline briefs on the same topics. If they are absent
  the result is `INCONCLUSIVE (baseline not supplied)`.
- **Measurement proposal (CE5).**
  - Per-article landing URL and CTA.
  - Qualified non-brand GSC impressions/clicks in 28-day comparable windows.
  - Aggregate Umami events only, and only those the owner approves.
  - #433 first permitted MCP action where observable.
  - A 6-8 week review feeding OD-7.
  - Verdict vocabulary KEEP / ITERATE / STOP / INCONCLUSIVE, with `UNKNOWN` for missing
    data and no growth guarantee.
  - No session replay, private content or identity joins.
- **Backlog.**
  - "What did I miss in Telegram": grounded in mctl-telegram#1517, labeled as design if
    not shipped, linking the #1152 account-wide hidden-dialog decision. The original
    Reddit thread must be re-verified, and its author is never claimed as a customer.
  - The hypotheses on messaging workflows, privacy/local custody and safe approvals, each
    recorded with observed evidence kept separate from editorial inference.
- **Proposed verdict.** `REUSE_DEVLOOP_PILOT` if the CE0 inventory confirms the
  primitives. Otherwise `MANUAL_EDITORIAL_ONLY`. The owner records the decision.

### 2. Reference model `docs/spikes/content-engine/`

Stdlib Python 3, offline, no network. Its files:

- `schema/brief.schema.json`, `schema/source-manifest.schema.json`,
  `schema/claim-map.schema.json`: shape documentation. Validation itself is hand-written
  in Python to stay stdlib-only.
- `content_check.py` with functions `check_brief`, `check_manifest`, `check_claims`,
  `check_secrets`, `check_duplicates`, `check_consent` and `check_injection`, plus a CLI
  `python -I content_check.py <candidate-dir> [--inventory inventory.json]`. Exit code is
  0 when the candidate passes and 1 when it has findings. Findings are JSON lines with a
  rule id and location; matched secret values are never printed.
  - Allowlist: `https://` only. Host classes are public docs, public GitHub repo blob
    URLs at a 40-hex commit, and vendor public pages. It rejects private issue/PR URLs
    unless the URL is listed as public in the manifest, and rejects query-string tokens.
  - Material claim detection is explicit. The draft marks claims with
    `<!-- claim:ID -->` anchors, and the claim map assigns each anchor `supported`
    (source ids) or `qualified` (qualifier text present in the draft). An anchor that is
    missing from the map, or that maps to an unknown source, is a finding. The semantic
    review stays human/independent, and the model only enforces completeness.
  - Injection check: retrieved snippets in the manifest are scanned for directive
    patterns ("ignore previous", "you are now", tool-call syntax). A match is flagged as
    `untrusted-instruction`. A match never alters any other result.
  - Duplicate check: the canonical intent key (normalized query + property + target URL)
    must not collide with another brief or with an inventory URL.
  - Consent check: CE6 repurposing entries and third-party quotes require
    `consent_ref`.
- `fixtures/` contains passing candidates and negative fixtures for: prompt injection in
  a snippet, an unsupported claim, a non-allowlisted/private source, a secret-shaped
  string, a duplicate canonical intent, and missing consent.
- `test_content_check.py`: unittest, runnable with
  `python -I -m unittest discover -s docs/spikes/content-engine`.

### 3. Three review-only candidates `docs/spikes/content-engine/candidates/<slug>/`

Each candidate directory holds `brief.json`, `sources.json`, `claims.json` and an
`outline.md` draft. The draft is clearly marked `DRAFT - NOT FOR PUBLICATION`, and its
target is a canonical URL on tg.mctl.ai or mctl.ai. Each draft links the existing
canonical onboarding rather than duplicating it.

1. `connect-telegram-mcp`: setup, OAuth and scopes, from public mctl-telegram docs and
   code at a pinned commit.
2. `mcp-apps-interop-matrix`: dated, versioned matrix that separates invocation from
   rendering. Cells not observed live are `UNKNOWN (not observed)`.
3. `secure-remote-mcp-server`: authorization, approval and revocation from public
   code/docs only. It leaves out internal vulnerabilities, credentials and deployment
   details.

All three must pass `content_check.py`.

### 4. Roadmap manifests (review-only)

- New `roadmap/spikes/content-engine.yaml`:
  - `metadata.name: content-engine`, `owner: mctlhq/.github`;
  - `lifecycle: proposed`, `github.issue: mctlhq/.github#435`;
  - outcomes `REUSE_DEVLOOP_PILOT`, `MANUAL_EDITORIAL_ONLY`, `EVALUATE_THIRD_PARTY`,
    `NO_GO`;
  - `execution.devloop: true`, `evidence.report: docs/spikes/content-engine.md`;
  - no `spec.epic` and no `decision`.
- `roadmap/epics/organic-discovery-growth.yaml`: append one unbound work item:

  ```yaml
      - id: od-14-content-engine
        title: Pilot governed technical content briefs and drafts with exact-revision review
        owner: mctlhq/.github
        phase: intent
        required: false
        dependsOn:
          - od-0-baseline
          - od-4-telegram
          - od-5-hub
  ```

  All other content stays byte-identical. There is no apply or reconcile.
- `AGENTS.md`: add one `# Spikes` bullet for the report.

## Alternatives

- **Build a dedicated content microservice / Growth Agent with a scheduler and CMS.**
  Dropped. The issue forbids it explicitly, and it would duplicate DevLoop, review gates,
  Product Updates and the analytics that already exist.
- **Adopt a third-party SEO content platform (Outrank/AirOps) first.** Dropped as the
  default. It needs accounts and paid plans that are not authorized, and its terms and fit
  are unverified. It is kept as the `EVALUATE_THIRD_PARTY` outcome, to use only if the
  pilot shows a measurable cost or quality gap.
- **Bind OD-14 to #435 and declare `spec.epic` in the SpikeDefinition.** Deferred. The
  validator requires the work item to be issue-bound, which contradicts the epic's
  "deliberately unbound" rule and the issue's "preserve unbound candidates" acceptance
  item. The owner can bind it later in a one-line change.
- **Write the drafts directly as PRs into mctl-web/mctl-telegram.** Dropped for this
  slice. That is publication-adjacent work in other repos, and it belongs to the separate
  CE3/CE4 exact-scope candidate.

## Platform impact

- No migrations, services, images, cron jobs, secrets or runtime changes. Resource
  impact is none, apart from one more SpikeDefinition and its tests in the existing
  roadmap CI.
- Backward compatibility: the epic change only appends an optional, unbound item. It does
  not change completion (`allRequired`) or ready-set semantics for existing items, and
  `od-shortlist` and `od-7-evaluation` stay as they are.
- Risk: candidate drafts could read as published claims. Mitigation: an explicit
  draft banner, `UNKNOWN` cells, and no destination-repo writes.
- Risk: the deterministic checks could be mistaken for semantic fact-checking.
  Mitigation: the report states the semantic citation review is independent and human
  (mctl-academy#83 lesson: substring match is not support).
- Risk: secret or PII leakage in fixtures. Mitigation: fixtures use obviously synthetic
  values built at test time, and the checker never echoes matches.
- Risk: the issue template does not conform. Mitigation: the owner fixes #435 before
  approving the DevLoop, as `AGENTS.md` requires.
- Cost: only the DevLoop implementer run that writes this spike. No pilot or Content
  Scout model execution.
