# Design: issue-21-feat-content-generate-20-published-quest

## Current state

`content/` is a flat, git-tracked corpus validated by two independent layers
(`CLAUDE.md`, "The gate"):

1. **JSON Schema** (`content/schemas/question.schema.json`,
   `source.schema.json`), compiled with ajv's 2020-12 build in
   `scripts/validate-content.mjs` (draft-07, ajv's default export, silently
   ignores `minContains`/`maxContains` — the comment in that file is explicit
   about why the 2020-12 import matters).
2. **The lint** (`scripts/validate-content.mjs` itself): cross-file objective
   references against `content/branding.yaml`, duplicate id/option-text
   detection, the `AGENT_AUTHOR` regex (`^agent:[a-z0-9][a-z0-9-]*$`) on
   `authored.by`, the `published` ⇒ `reviewed` lifecycle rule, and a
   bank-wide answer-position-bias check once ≥12 questions exist.

A question (`content/questions/q-*.yaml`) has: `id` (`q-[a-z0-9]{12}`),
`status` (`draft|needs_review|published|retired`), `domain`, `objective`
(`domain-N/objective-id`, cross-checked against `branding.yaml`), a `stem`,
exactly 4 `options` (one `correct: true`, each with an `explanation` — this is
the "per-option feedback" the issue asks for and it already exists as a
required field, not new work), an `evidence` array (`source_id` +
≤25-word verbatim `excerpt`), `authored` (`by`/`at`), and an optional
`reviewed` (`by`/`at`) that gates `published`.

A source (`content/sources/src-*.yaml`) has: `id`, `url` (host-checked against
`SOURCES.md`'s two-entry allowlist), `title`, `retrieved_at`, `sha256`, an
`objectives` array, and an optional `snapshot` (`bucket`/`key`, `key ===
sha256`). `checkEvidence()` in the lint treats a question whose source has no
`snapshot` as un-publishable, and a question whose source is `status:
drifted` the same way.

I read every existing `domain-2` question and source
(`q-fc01a2b3c4d5.yaml` .. `q-fc04a8b9c0d1.yaml`,
`q-so01d5e6f7a8.yaml` .. `q-so03f7a8b9c0.yaml`,
`src-function-calling.yaml`, `src-structured-output.yaml`) and cross-referenced
`content/branding.yaml`'s `domain-2` objective list. Result: `domain-2` has 7
objectives; only `function-calling` and `structured-output` have a source
record; the other five (`chat-completions`, `embeddings-and-rerank`,
`retrieval-pipelines`, `framework-integrations`, `agent-sandboxes`) have zero
sources and therefore zero possible published questions today. This is the
actual gap issue #21 is asking to close, even though its body only says
"generate 20 questions."

`scripts/capture-source.mjs` is the existing tool for adding a source: it
fetches an allowlisted URL, hashes it, uploads to R2 via
`scripts/lib/snapshot-store.mjs` (`storeFromEnv()`, requiring
`R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`), and writes the
`content/sources/<id>.yaml` record. `.github/workflows/content-evidence.yml`
runs `npm run verify:evidence` with those same three secrets on same-repo
pushes/PRs only — never on a fork, which is exactly why `CONTRIBUTING.md`
closes content PRs from forks.

Content review is entirely human-gated: `.github/CODEOWNERS` assigns
`/content/` to `@mashkovd`, `.github/pull_request_template.md` carries the
clean-room attestation and a hard "10 questions per PR" checkbox, and
`CONTRIBUTING.md`'s review-gates table states the same cap in prose. No
LLM reviews content PRs (`CLAUDE.md`, "Review gates"); the only automation is
schema + lint + evidence CI.

## Proposed solution

Two additive tracks, both inside `content/`, no schema/lint/application code
changes:

**Track A — source coverage (prerequisite for 15 of the 20 questions).**
Add 5 new `content/sources/src-*.yaml` records, one per currently source-less
`domain-2` objective, by researching the canonical
`docs.tokenfactory.nebius.com` page for each (mirroring how
`src-function-calling.yaml` points at `.../function-calling.md`) and running
`node scripts/capture-source.mjs <url> --id <src-id> --objective domain-2/<objective>`
wherever the R2-backed environment variables are available. Each new source's
`objectives` array must resolve against `content/branding.yaml`
(`chat-completions`, `embeddings-and-rerank`, `retrieval-pipelines`,
`framework-integrations`, `agent-sandboxes`) or the lint rejects it outright.

If the environment running this proposal's implementation cannot reach R2
(see Open questions in requirements.md), the fallback is: write the source
record with the `url`/`sha256`/`title` fields populated from a manual fetch,
omit `snapshot`, and let the lint's existing behavior do its job — questions
citing that source simply cannot carry `status: published` until someone with
credentials completes the capture. This degrades gracefully to "draft
content waiting on infrastructure" rather than a blocked PR.

**Track B — 20 new question files.** One YAML file per question under
`content/questions/`, ids following the established mnemonic convention
(2-letter objective code + 2-digit sequence + 8 hex chars, e.g. `q-cc01...`
for `chat-completions`, `q-er01...` for `embeddings-and-rerank` — `el` is
already taken by `endpoint-lifecycle` in `domain-4`, so `er` avoids collision;
`rp` for `retrieval-pipelines`, `fi` for `framework-integrations`, `as` for
`agent-sandboxes`). Distribution (see requirements.md "Open questions" for the
reasoning): 3 questions each for the 5 newly-sourced objectives (15) + 3 more
for `function-calling` + 2 more for `structured-output` (5), totaling 20 and
landing every `domain-2` objective at 3+ published questions.

Every new question:
- `authored.by: agent:<name>` (never a human name — `CONTENT-POLICY.md` and
  the lint's `AGENT_AUTHOR` check both require this).
- `status: draft` at authoring time. A human `reviewed` block and the flip to
  `status: published` happens as part of the CODEOWNER's PR review — mirroring
  exactly how the 7 existing `domain-2` questions are already `published` with
  `reviewed.by: mashkovd`. This proposal's own output is therefore
  "20 draft/needs_review questions that pass every mechanical check and are
  ready for human review," not "20 already-published questions" — an agent
  cannot make itself the reviewer without collapsing the clean-room
  separation `CONTENT-POLICY.md` exists to enforce. The issue title's
  "published" is the end state after merge, not something this PR can set
  unilaterally.
- Four options, unique text, one `correct: true`, every option (including
  wrong ones) carrying an `explanation` ≥12 characters — this is already a
  schema-required field, so "per-option feedback" from the issue body is
  satisfied by filling required fields correctly, not by inventing a new
  content shape.
- One `evidence` entry citing the matching new (or existing) source, excerpt
  ≤25 words, verbatim from the captured document — verified later by
  `verify:evidence` in CI, not guessed at authoring time.

**Track C — PR sequencing.** Split the 20 questions into 2 PRs of 10 each
(the `CONTRIBUTING.md` cap is absolute, not a target), each carrying the
attestation checklist from `.github/pull_request_template.md` and targeting a
non-`main`, non-underscore-prefixed branch (e.g.
`feat/domain-2-questions-batch-1`, `feat/domain-2-questions-batch-2`), each
merged with a merge commit, never squashed.

## Alternatives

1. **Put all 20 questions on the 2 already-sourced objectives
   (`function-calling`, `structured-output`).** Rejected: it satisfies the
   issue's literal count but makes the coverage problem worse — 27 of
   domain-2's questions would sit on 2 of 7 objectives, directly working
   against the weight-35 domain's own objective map and the mock composition
   (10 of 30 mock slots come from domain-2, drawn across all 7 objectives in
   principle). It also does nothing for the actual defect this investigation
   found.
2. **Skip Track A and ship whatever fits without new sources (7 more
   questions on the 2 existing objectives, falling short of 20).** Rejected:
   does not satisfy the issue, and defers the real gap to whichever future
   issue is forced to notice it again.
3. **Change `scripts/capture-source.mjs` or the lint to allow a `published`
   question with no snapshot (e.g. "trust the excerpt, verify later").**
   Rejected outright: this is precisely the fail-open pattern
   `checkEvidence()` and `content-evidence.yml` are designed to prevent
   ("Missing snapshot or non-matching excerpt blocks publication," `PLAN.md`
   section 4). Weakening it to hit a content quota would break the mechanism
   the whole content-policy design depends on for every future domain, not
   just this one.
4. **Have this proposal's implementer also set `reviewed` and
   `status: published` directly.** Rejected: violates
   `CONTENT-POLICY.md`'s author/reviewer separation and the lint's
   `AGENT_AUTHOR` check would in fact still pass (it only checks `authored.by`,
   not `reviewed.by`) — meaning this failure mode is not mechanically caught
   and must be avoided by design/process instead. Documented here so the
   implementer does not "helpfully" do it.

## Platform impact

- **Migrations:** none. Content is flat YAML, no database exists yet
  (`CLAUDE.md`: "the application does not exist yet").
- **Backward compatibility:** additive only. No existing question, source, or
  schema changes. `schema_version: 1` unchanged.
- **Resource impact:** 5 new R2 objects (one per new source snapshot, sizes
  comparable to the existing 7 snapshots — full doc pages, single digit KB to
  low hundreds of KB) in the already-provisioned `academy-source-snapshots`
  bucket. 20 new small YAML files in-repo (a few KB each). No new CI jobs —
  `ci.yml` and `content-evidence.yml` already run on every PR.
- **Risks and mitigations:**
  - *Risk:* the 5 new source URLs, once fetched, do not actually support 3
    solid, single-best-answer questions each. *Mitigation:* Track A completes
    before Track B is written for a given objective — a question is never
    drafted against a source that has not been read.
  - *Risk:* R2 credentials are unavailable to whatever agent implements this,
    stalling Track A. *Mitigation:* documented fallback (source record without
    `snapshot`, questions stay `draft`) so the PR can still land and be
    finished by a credentialed human rather than blocking entirely.
  - *Risk:* answer-position bias. Bank-wide check in
    `scripts/validate-content.mjs` fires once ≥12 questions exist and any
    position exceeds 50% of correct answers; going from 20 to 40 questions is
    exactly the kind of bank-size change that could tip this. *Mitigation:*
    explicitly vary correct-option placement across the 20 new items and run
    `npm run lint:content` before opening each PR — it is a hard CI failure,
    not a suggestion.
  - *Risk:* citation excerpts drift from "genuinely verbatim" during drafting
    (paraphrasing to fit the 25-word cap, per the schema's own warning: "If 25
    words cannot support the claim... do not paraphrase to fit"). *Mitigation:*
    copy excerpts directly from the fetched document text before writing the
    question, and let `verify:evidence` be the final check, not the first one.
  - *Risk:* two concurrent 10-question PRs both touching answer-position
    balance or objective distribution without seeing each other. *Mitigation:*
    sequence the PRs (Track C) rather than opening both simultaneously, or
    validate the combined set locally with `ACADEMY_CONTENT_DIR` before
    opening the second.
