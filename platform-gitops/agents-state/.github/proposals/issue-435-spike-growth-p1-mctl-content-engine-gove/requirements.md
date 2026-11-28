# MCTL Content Engine spike: governed technical content and organic acquisition (OD-14)

## Context

Issue mctlhq/.github#435 is a P1 research spike under the Organic Discovery & Growth
initiative (mctlhq/.github#349, epic manifest `roadmap/epics/organic-discovery-growth.yaml`,
proposed work item OD-14). It asks whether verified MCTL engineering knowledge can become
a small number of useful technical articles, first for tg.mctl.ai and mctl.ai. The articles
should attract qualified users and lead to measurable activation. The work has to reuse the
existing DevLoop, evidence and review machinery. It must not build a new service, CMS,
Growth Agent, agent runtime or publication/analytics control plane. Seven slices are
proposed (CE0-CE6). This issue authorizes only research and a proposed bounded pilot: no
publication, deployment, external accounts, API keys, paid tools or new content-engine
model execution.

This proposal delivers the research slice in this repository only: a spike report, a
SpikeDefinition manifest, and a stdlib reference model with deterministic checks for the
pilot artifacts (content brief, source manifest, claim-to-source map, negative checks).
It also covers three review-only editorial candidate briefs with dated public evidence and
a review-only manifest diff that adds an unbound OD-14 work item. Writing articles into
destination repos, publishing and measuring outcomes are separate exact-scope candidates
that the owner must approve one at a time.

## User stories

- AS the platform owner I WANT an audited inventory of existing content sources,
  destinations, validators and owners SO THAT I can decide whether to reuse or build
  before spending model budget.
- AS the platform owner I WANT explicit pilot thresholds, a model and reviewer-time budget,
  and a manual-baseline comparison rubric fixed in advance SO THAT a later pilot can be
  judged KEEP / ITERATE / STOP / INCONCLUSIVE on evidence.
- AS an independent reviewer I WANT every material claim in a candidate draft mapped to a
  dated primary public source, or explicitly qualified, SO THAT nothing unverified
  reaches publication.
- AS a property owner (mctl-telegram, mctl-web) I WANT each candidate to name one
  canonical destination URL and link to existing canonical onboarding SO THAT the content
  does not compete with pages I already own.
- AS a security reviewer I WANT deterministic negative checks for prompt injection in
  retrieved text, bad evidence, duplicate publication, missing consent and secret/PII
  leakage SO THAT the workflow fails closed.

## Acceptance criteria (EARS)

- WHEN the spike report `docs/spikes/content-engine.md` is merged THE SYSTEM SHALL contain
  a CE0 inventory table that names exactly one canonical owner per artifact (brief,
  source manifest, draft, evidence review, destination page, CTA, measurement). Each entry
  is tagged `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]` or `unknown (not observed)`.
- WHEN the report records a reuse/no-build decision THE SYSTEM SHALL list the existing
  primitives reused (DevLoop investigator/implementer, independent review gate, existing
  CI, Product Updates feed mctl-telegram#440/#683, Umami at stats.mctl.ai, GSC, #433
  attribution, #315 Product Scout) and SHALL state that no new service, CMS, Growth Agent or
  analytics control plane is proposed.
- THE SYSTEM SHALL add `roadmap/spikes/content-engine.yaml` as a SpikeDefinition with
  `lifecycle: proposed`, `github.issue` = mctlhq/.github#435, at least two uppercase
  outcomes, `execution.devloop: true`, `evidence.report: docs/spikes/content-engine.md`
  and no `decision` block. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`
  SHALL pass.
- WHEN the review-only manifest diff is applied to
  `roadmap/epics/organic-discovery-growth.yaml` THE SYSTEM SHALL add exactly one work item
  `od-14-content-engine` with no `issue` binding and `required: false`. It SHALL leave
  every existing work item, dependency, phase and success criterion byte-identical and
  SHALL keep `lifecycle: proposed`.
- THE SYSTEM SHALL provide a stdlib-only Python reference model in
  `docs/spikes/content-engine/` that validates a content brief and a source manifest.
  The brief carries query/intent, audience, canonical target URL, duplicate check, CTA,
  priority and source confidence. The manifest carries URL, retrieved-at date, content
  hash, allowlist class and license note. The model also validates a claim-to-source map
  against fixed schemas.
- IF a draft contains a material claim (compatibility, security, partner, certification,
  pricing, host support) that is neither mapped to a source manifest entry nor marked
  qualified THEN THE SYSTEM SHALL report that claim and exit non-zero.
- IF a source manifest entry is not on the public allowlist (for example a private
  repository, private issue/PR, or an authenticated or non-HTTPS URL) THEN THE SYSTEM SHALL
  reject the manifest.
- IF retrieved source text contains instruction-like content THEN THE SYSTEM SHALL treat
  it as data, flag it, and not let it change the brief, the claim map or the check outcome.
- IF a draft or brief matches a secret-shaped pattern or a listed private-identifier
  pattern THEN THE SYSTEM SHALL fail the check without echoing the matched value.
- IF two briefs, or a brief and an existing canonical URL in the inventory, target the
  same canonical intent THEN THE SYSTEM SHALL report a duplicate and exit non-zero.
- IF a brief proposes a channel repurposing (CE6) or uses a user-supplied quote or
  thread without a recorded consent reference THEN THE SYSTEM SHALL fail the
  missing-consent check.
- WHEN the three editorial candidates are delivered THE SYSTEM SHALL provide, per
  candidate, a brief, a dated source manifest and a claim map in which 100% of material
  claims are supported or explicitly qualified, all passing the reference checks. The
  candidates are (1) Connect Telegram to ChatGPT or Claude via MCP, (2) MCP Apps
  interoperability matrix, (3) Secure remote MCP server.
- WHILE a host behaviour (ChatGPT, Claude, Grok Chat, Grok Bot) has not been observed live
  in this spike THE SYSTEM SHALL mark the corresponding matrix cell `UNKNOWN (not
  observed)` and SHALL NOT state support or non-support.
- THE SYSTEM SHALL record in the report, before any pilot model execution:
  - pilot thresholds (source support 100% of material claims; reviewer minutes per
    article ceiling; model spend per article ceiling; zero secret/PII findings; zero
    duplicate canonical intents);
  - a scoring rubric for the manual-baseline comparison (source support, technical
    reproducibility, usefulness, duplication, review effort, cost);
  - the rule that the reviewer is not the writer, that approval binds an exact
    revision, and that rejected or changed content cannot publish.
- WHERE manual baseline briefs or drafts are not supplied by a human THE SYSTEM SHALL
  record the baseline comparison as `INCONCLUSIVE (baseline not supplied)` rather than
  scoring workflow output alone.
- THE SYSTEM SHALL propose per-property measurement:
  - per-article landing and CTA;
  - qualified non-brand GSC impressions and clicks in 28-day comparable windows;
  - approved aggregate Umami events;
  - first permitted MCP action through #433 where observable.

  The proposal SHALL include a 6-8 week review. Missing data is recorded as `UNKNOWN`,
  and the proposal SHALL make no growth guarantee.
- THE SYSTEM SHALL add an entry for the new spike report under `# Spikes` in `AGENTS.md`.

## Out of scope

- Publishing, merging or deploying any article; writing into mctl-web, mctl-telegram,
  mctl-docs, mctl-academy or mctl-alice repositories.
- Any new service, CMS, generic Growth Agent, agent runtime, scheduler, cron job, or
  publication/analytics control plane.
- Enabling scheduled, event or on-demand Content Scout triggers (CE1 triggers are
  candidates only).
- External account linking, API key creation, paid subscriptions or purchases (Outrank,
  AirOps, LurkAPI, SerpWrap, Tavily). Vendors are benchmarked from public documentation
  only, and nothing is claimed as compatible or free unless confirmed.
- Running a separate Content Scout / Technical Writer model pipeline, which needs
  separate owner GO and budget.
- External posting on LinkedIn, X, Telegram or Product Updates broadcast (CE6).
- Roadmap graph apply or reconciliation, `agents:intake` labeling, binding OD-14 to an
  issue, and creating implementation issues.
- Private conversations, session replay, session-level data or inferred identity joins
  in measurement.
- The backlog candidate "What did I miss in Telegram" (mctl-telegram#1517). It is
  recorded as a backlog entry only, not a fourth pilot article.

## Open questions

- Issue #435 does not follow the current `.github/ISSUE_TEMPLATE/spike.yml`. The title
  uses `spike(growth):` instead of the `spike: ` prefix, and the body lacks the
  `Source:`, `Question:`, `Outcomes:`, `Lifecycle:`, `Related:` and `Why mctl:` lines.
  Its labels could not be checked here. `AGENTS.md` says a non-conforming spike must be
  fixed before DevLoop or `agents:intake`. This proposal assumes the owner fixes the
  issue before approving implementation, and it proposes `Source:
  mctlhq/.github#349 OD-14` as the dedup key.
- Canonical article destination is not decided. No blog/content path can be observed
  from this clone (mctl-web, mctl-telegram and mctl-docs source is not checked out here).
  CE0 must inventory it. The working assumption is per-property canonical pages owned by
  the property repo (tg.mctl.ai content in mctl-telegram, mctl.ai in mctl-web), not a
  central blog.
- Spike outcomes are proposed as `REUSE_DEVLOOP_PILOT`, `MANUAL_EDITORIAL_ONLY`,
  `EVALUATE_THIRD_PARTY` and `NO_GO`. The KEEP / ITERATE / STOP / INCONCLUSIVE vocabulary
  is the later post-publication verdict (OD-7), not the spike verdict. The owner may
  prefer a different split.
- Whether OD-14 should be `required: true` for epic completion. It is proposed as `false`
  so the existing completion semantics are preserved.
- Whether the implementer run can fetch live public web sources. If it cannot, source
  manifest entries are pinned to repository commits and public docs read at a given
  revision, and live-only evidence (host screenshots, vendor pricing pages) is marked
  `UNKNOWN (not observed)`.
- No human manual baseline briefs exist yet. Who writes the three baselines, and by when?
- Numeric pilot ceilings (model spend and reviewer minutes per article) need owner
  confirmation. Proposed defaults are in design.md.
