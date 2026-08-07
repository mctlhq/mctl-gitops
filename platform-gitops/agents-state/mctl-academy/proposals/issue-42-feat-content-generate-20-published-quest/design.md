# Design: issue-42-feat-content-generate-20-published-quest

## Current state

- `content/branding.yaml` defines four domains with `schema_version: 1`.
  `domain-4` ("Production operations", weight 25, `mock_questions: 8`) has
  seven objectives: `dedicated-endpoints`, `endpoint-lifecycle`,
  `capacity-and-scaling`, `rate-limits`, `observability`,
  `billing-and-consumption`, `team-access`.
- `content/questions/*.yaml` (20 files today) validate against
  `content/schemas/question.schema.json`: exactly 4 options, exactly one
  `correct: true` (via `minContains`/`maxContains`, which requires ajv's
  2020-12 build — `scripts/validate-content.mjs` imports
  `ajv/dist/2020.js` specifically), a required `explanation` per option, at
  least one `evidence` entry with a `source_id` and a ≤25-word `excerpt`,
  and an `authored: {by, at}` block. `reviewed: {by, at}` is optional in
  schema but required by the lint (`checkLifecycle`) before `status:
  published`.
- Five `domain-4` questions currently exist and are all `status: published`:
  `q-el01a0b1c2d3.yaml`, `q-el02b1c2d3e4.yaml` (objective
  `endpoint-lifecycle`), `q-rl01d7e8f9a0.yaml`, `q-rl02e8f9a0b1.yaml`,
  `q-rl03f9a0b1c2.yaml` (objective `rate-limits`). I read `q-rl01d7e8f9a0.yaml`
  and `q-op01d1e2f3a4.yaml` in full as style references: a scenario-style
  stem, four options each with a distinct wrong-answer rationale, one
  `evidence` entry citing a `src-*` id, `authored.by: agent:claude`,
  `reviewed.by: mashkovd`.
- `content/sources/*.yaml` (8 files) validate against `source.schema.json`.
  Only two have `objectives` under `domain-4`: `src-endpoint-lifecycle.yaml`
  and `src-rate-limits.yaml`, both with a `snapshot: {bucket:
  academy-source-snapshots, key: <sha256>}` and `status: current`. The other
  five domain-4 objectives have no source record at all.
- `scripts/capture-source.mjs` (`npm run snapshot:capture`) is the only path
  that produces a valid source record with a snapshot: it fetches the URL
  (host must be on `ALLOWED_HOSTS`, same list as `SOURCES.md`), hashes it,
  writes the object to R2 via `scripts/lib/snapshot-store.mjs`
  (`storeFromEnv()`, needs `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/
  `R2_SECRET_ACCESS_KEY`), and writes `content/sources/<id>.yaml` with
  `snapshot.key === sha256`. Without a snapshot, `checkEvidence` in
  `scripts/validate-content.mjs` blocks `status: published` (but allows
  `status: draft`, confirmed by the lint test "allows a draft to cite a
  source with no snapshot").
- `scripts/validate-content.mjs` (`npm run lint:content`) is structural only
  — no network, no secrets, runs on forks. It checks: schema validity,
  duplicate ids, objective-belongs-to-domain and objective-is-in-branding,
  evidence source exists and (for published items) is snapshotted and not
  drifted, `authored.by` matches `agent:<name>`, `reviewed` present for
  `published`, no duplicate option text, and (once the bank has 12+
  questions) no single correct-answer position exceeding 50% bank-wide.
- `scripts/verify-evidence.mjs` (`npm run verify:evidence`, run by
  `.github/workflows/content-evidence.yml`) does the verbatim check against
  the R2 snapshot; it needs `R2_*` secrets and is skipped on fork PRs
  (`content-evidence.yml`'s `if:` condition).
- `.github/CODEOWNERS` requires `@mashkovd` approval on anything under
  `/content/`. `.github/workflows/claude-review.yml` explicitly
  `skip-paths: '^content/(questions|lessons|sources)/'` — content PRs are
  never LLM-reviewed, by design (`CLAUDE.md`, `CONTENT-POLICY.md`).
- `CONTRIBUTING.md`: "Content pull requests are capped at 10 questions."

## Proposed solution

Two-phase content batch, entirely inside `content/`, no schema or app code
touched:

**Phase A — source capture (prerequisite).** For each of the five
uncovered domain-4 objectives (`dedicated-endpoints`,
`capacity-and-scaling`, `observability`, `billing-and-consumption`,
`team-access`), identify one authoritative page under
`docs.tokenfactory.nebius.com` (primary, per `SOURCES.md`) or
`docs.nebius.com` (secondary, infrastructure-only) that documents it, then
run `npm run snapshot:capture -- <url> --id src-<slug> --objective
domain-4/<objective>` to produce a new `content/sources/src-<slug>.yaml`
with a real snapshot, following the exact shape of
`src-endpoint-lifecycle.yaml`. This is the only mechanism in the repo that
produces a citable, publishable source — hand-writing a source YAML without
running the capture script would leave `snapshot` empty and permanently
block publication of anything citing it (`checkEvidence`).

**Phase B — question authoring.** Draft 20 new `content/questions/q-*.yaml`
files, `status: draft`, `authored.by: agent:<name>` (a stable identifier for
this batch, e.g. `agent:academy-content`), distributed across all seven
domain-4 objectives (roughly 3 each — see Open questions #3 in
requirements.md for the exact split). Each item:

- Four options, exactly one `correct: true`, each option carrying a
  distinct `explanation` (including for wrong answers, per the schema
  comment: "the part that makes this a study tool rather than a quiz").
- At least one `evidence` entry citing a `domain-4` source (existing or
  newly captured in Phase A), with a verbatim excerpt ≤25 words.
- `id` following the existing `q-<domain-prefix><nn><hex>` convention (e.g.
  `q-de01...` for `dedicated-endpoints`, `q-cs01...` for
  `capacity-and-scaling`, etc. — pick unused two-letter prefixes per
  objective, mirroring `el`/`rl`/`op`/`so`/`ft`/`fc`/`df`/`pf` already in
  use).
- Style matching `q-rl01d7e8f9a0.yaml`: scenario-framed stem, plausible
  distractors with their own rationale rather than "obviously wrong"
  filler.

Run `npm run lint:content` and `npm run test:content` locally before
opening any PR — both are cheap, secret-free, and are exactly what `ci.yml`
re-runs.

Split the 20 items across at least two PRs of ≤10 each (`CONTRIBUTING.md`
cap). A natural split: PR1 covers the two already-sourced objectives plus
one or two newly-sourced ones (~10 items, unblocks review sooner since no
new source risk); PR2 covers the remaining newly-sourced objectives. Each
PR fully checks the attestation checklist in
`.github/pull_request_template.md`, branches as `feat/domain-4-questions-1`
/ `feat/domain-4-questions-2` (no leading underscore, per `CONTRIBUTING.md`
branch-naming rule), and targets `main` for a merge commit (never squash).

Publication (`status: published` + `reviewed` block) happens when
`@mashkovd` reviews each PR against the two-criterion checklist in
`CONTENT-POLICY.md` and pushes the `reviewed` block — outside this
proposal's automated scope by design.

## Alternatives

1. **Author all 20 items citing only the two already-sourced objectives
   (`endpoint-lifecycle`, `rate-limits`).** Rejected: it sidesteps the real
   gap (5 of 7 objectives have zero content) and violates
   `CONTENT-POLICY.md`'s "coverage is allocated from the published domain
   weights only" — piling every new item onto two objectives because
   they're easy is exactly the recall-shaped bias that policy exists to
   prevent.
2. **Hand-write new `content/sources/*.yaml` records with a fabricated or
   manually-computed `sha256`/`snapshot`, skipping `capture-source.mjs`.**
   Rejected: `snapshot.key` must equal the actual document hash
   (`validate-content.mjs`: "snapshot.key must equal sha256"), and
   `verify-evidence.mjs` re-fetches from R2 by that key — a hand-written
   snapshot reference would either fail the lint immediately or (worse)
   silently fail verification later. The capture script is the only correct
   path.
3. **One PR for all 20 questions.** Rejected outright by
   `CONTRIBUTING.md`'s explicit 10-question cap, stated as a deliberate
   review-load ceiling given a single human reviewer.
4. **Write items straight to `status: published` with a placeholder
   `reviewed` block.** Rejected: `CONTENT-POLICY.md` and `CODEOWNERS` make
   review/approval exclusively a human action separated from authorship; a
   agent-written `reviewed.by` would fail `AGENT_AUTHOR`-style intent even
   though the schema's `reviewed.by` field itself doesn't pattern-match
   agents — doing this would defeat the entire clean-room separation the
   project is built around, not just fail a lint rule.

## Platform impact

- **Migrations**: none. No schema change, no `content/schemas/*.json`
  touched.
- **Backward compatibility**: additive only — new question and source
  files. Existing published items are untouched, so no attempt history is
  affected (source drift / re-verification rules already handle that case
  and are out of scope here).
- **Resource impact**: negligible. `npm run snapshot:capture` makes up to 5
  outbound HTTPS fetches to allowlisted docs hosts and 5 small R2 PUTs.
  `npm run lint:content` / `test:content` are local, no-network.
- **Risks + mitigations**:
  - *R2 credentials may not be available to the executing agent outside
    GitHub Actions* — `capture-source.mjs` hard-fails with "snapshot store
    is not configured" if `R2_*` env vars are absent. Mitigation: if
    unavailable, Phase A cannot complete for the agent alone; fall back to
    drafting only the two already-sourced objectives' questions now (draft
    status, still useful) and file a follow-up task for a maintainer (who
    has Vault-provisioned credentials per `PLAN.md`'s deployment notes) to
    run capture for the remaining five. Documented as task 1's fallback in
    `tasks.md`.
  - *Wrong or thin authoritative source picked for an objective* (e.g.
    `billing-and-consumption` might live under `docs.nebius.com` rather
    than `docs.tokenfactory.nebius.com`) — mitigation: prefer Token
    Factory docs per `SOURCES.md`'s explicit primacy note, fall back to AI
    Cloud docs only where the objective genuinely touches infrastructure
    (the doc's own carve-out), and record the chosen URL/title in the PR
    description so the reviewer can sanity-check provenance alongside the
    excerpt.
  - *Answer-position bias check* (`validate-content.mjs`, active once the
    bank has 12+ questions, which domain-4 will exceed) — mitigation:
    deliberately vary which option (`a`/`b`/`c`/`d`) is correct while
    drafting, per the lint's own comment about the pattern it was built to
    catch.
  - *Duplicate `q-*`/`src-*` ids* — mitigation: generate ids following the
    existing `<prefix><nn><12-hex>` pattern and diff against
    `content/questions/`/`content/sources/` before writing, since the lint
    only catches duplicates that are actually committed together, not ids
    that collide with a not-yet-merged sibling PR.
  - *Fork-PR limitation is irrelevant here* — this work happens on a
    same-repo branch per `CONTRIBUTING.md` ("content changes come from
    maintainer and agent branches inside this repository"), so
    `content-evidence.yml`'s secrets are available and the evidence check
    runs for real, not skipped.
