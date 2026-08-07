# Design: issue-41-feat-content-generate-20-published-quest

## Current state

- `content/branding.yaml` defines `domain-3` ("Data and post-training",
  weight 20, `mock_questions: 6`) with 7 objectives: `files-api`, `datasets`,
  `dataset-formats`, `supervised-fine-tuning`, `fine-tuning-jobs`,
  `lora-adapters`, `data-lab`.
- `content/questions/` has 4 `domain-3` items, all `status: published` with a
  `reviewed` block by `mashkovd`: `q-df01f3a4b5c6` / `q-df02a4b5c6d7`
  (`domain-3/dataset-formats`, citing `src-dataset-formats`) and
  `q-ft01b5c6d7e8` / `q-ft02c6d7e8f9` (`domain-3/supervised-fine-tuning`,
  citing `src-supervised-fine-tuning`). No other `domain-3` objective has any
  question.
- `content/sources/` has 8 records total; only 2 are `domain-3`:
  `src-dataset-formats.yaml` (`docs.tokenfactory.nebius.com/post-training/datasets.md`,
  status `current`, `snapshot` present) and `src-supervised-fine-tuning.yaml`
  (`docs.tokenfactory.nebius.com/post-training/how-to-fine-tune.md`, status
  `current`, `snapshot` present). `files-api`, `datasets`,
  `fine-tuning-jobs`, `lora-adapters`, and `data-lab` have no source record
  at all.
- The gate is two mechanical layers plus one network layer, all read during
  this investigation:
  - `content/schemas/question.schema.json` (ajv 2020-12,
    `scripts/validate-content.mjs`): shape — 4 options, exactly one
    `correct: true` via `minContains`/`maxContains`, 25-word excerpt cap via
    regex, `authored`/`reviewed` object shape.
  - `scripts/validate-content.mjs` cross-file checks: `checkObjective`
    (objective must exist in `content/branding.yaml` and start with the
    question's own `domain`), `checkEvidence` (cited `source_id` must exist;
    a `published` item with an unsnapshotted source is an error), `AGENT_AUTHOR`
    regex on `authored.by`, `checkLifecycle` (`published` without `reviewed`
    is an error), duplicate option-id/text checks, and a whole-bank
    answer-position-bias check once >=12 questions exist (already true).
  - `scripts/verify-evidence.mjs` (`npm run verify:evidence`, run by
    `.github/workflows/content-evidence.yml` on same-repo pushes/PRs only —
    forks get no R2 secrets): fetches each cited source's snapshot from R2 by
    `sha256`/`snapshot.key` and asserts the excerpt occurs verbatim
    (whitespace/quote-normalized only). Critically,
    `requiresVerification(status)` is `status === "published" ||
    status === "needs_review"` — **`needs_review` is enforced, not just
    `published`.** Only `draft` is exempt. An item at `needs_review` citing a
    source with no `snapshot` fails this job closed
    (`"source X has no snapshot recorded"`), even though
    `scripts/validate-content.mjs`'s lint alone would let it through.
  - `scripts/capture-source.mjs` (`npm run snapshot:capture`) is the only
    writer of `content/sources/*.yaml` `snapshot` blocks. It requires
    `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`
    (`storeFromEnv()` in `scripts/lib/snapshot-store.mjs`) and fetches the
    live `.md` twin of an allowlisted page, hashes it, and writes the source
    record with `id`, `url`, `objectives`, `sha256`, and `snapshot.key ===
    sha256`.
- `CONTRIBUTING.md` caps content PRs at 10 questions and requires the
  `.github/pull_request_template.md` attestation checklist. `CLAUDE.md`
  (repo root) repeats: branch, PR, merge commit, never squash; branch names
  must not start with `_`; content PRs skip `claude-review.yml`
  (`skip-paths: '^content/(questions|lessons|sources)/'`) entirely — the
  human `CODEOWNERS` reviewer plus the evidence CI is the whole gate for
  content.
- `content/schemas/question.schema.json`'s `id` pattern is
  `^q-[a-z0-9]{12}$`; existing ids follow an informal `<2-letter-objective-
  code><2-digit-index><10 hex-ish chars>` convention (e.g. `q-df01f3a4b5c6`,
  `q-ft02c6d7e8f9`) that is not machine-enforced beyond the regex — any
  unique 12-char `[a-z0-9]` suffix is schema-valid.

## Proposed solution

Two-stage content pipeline, matching how the 4 existing `domain-3` items were
built, run by the Tier 2 implementer against this same clone:

**Stage A — source inventory (prerequisite for 5 of the 7 objectives).**
For each `domain-3` objective with no `content/sources/` record today
(`files-api`, `datasets`, `fine-tuning-jobs`, `lora-adapters`, `data-lab`),
identify a canonical page under `docs.tokenfactory.nebius.com` (its published
`llms.txt` index, per `SOURCES.md`, is the discovery mechanism — the same
approach implied by the URL shape of the two existing `domain-3` sources,
`.../post-training/datasets.md` and `.../post-training/how-to-fine-tune.md`)
and capture it:

```
npm run snapshot:capture -- <url> --id src-<slug> --objective domain-3/<objective>
```

This requires live R2 credentials (see design's Platform impact and
requirements.md's Open questions). Where capture cannot run in this
proposal's execution context, the corresponding questions are authored at
`status: draft` and the capture step is left as a follow-up the maintainer
runs locally (`README.md`/`CONTRIBUTING.md` document no separate path for
this — `capture-source.mjs` is the only entry point either way).

**Stage B — author 20 question files.** One new YAML file per question under
`content/questions/`, following the shape of `q-df01f3a4b5c6.yaml`:
`schema_version: 1`, a fresh unique `id` matching `^q-[a-z0-9]{12}$`,
`domain: domain-3`, `objective: domain-3/<objective>`, a `stem` (12-2000
chars), exactly 4 `options` (ids `a`-`d`, each with distinct `text` and a
`>=12`-char `explanation` for every option, not only the correct one, and
exactly one `correct: true`), `evidence` (>=1 entry, `source_id` pointing at
a real `content/sources/` record, `excerpt` <=25 words verbatim from that
source's current text), and `authored: {by: agent:<name>, at: <UTC
timestamp>}` with `reviewed` absent.

Suggested distribution (not a hard requirement — requirements.md leaves the
exact split to the implementer): 3 new questions each for `files-api`,
`datasets`, `fine-tuning-jobs`, `lora-adapters`, `data-lab`, `dataset-formats`
(3 more, on top of the existing 2), and 2 more for
`supervised-fine-tuning` (on top of the existing 2) = 20. This gives every
objective at least 3 total published-or-pending questions and stops the
mock's 6-question `domain-3` draw from being dominated by just 2 objectives.
Status per item: `needs_review` where the cited source already has a
`snapshot` (`dataset-formats`, `supervised-fine-tuning`, and any objective
Stage A successfully captured); `draft` otherwise.

**Stage C — PRs.** Split the 20 files into >=2 PRs of <=10 questions each
(`CONTRIBUTING.md` cap), each on its own `feat/academy-domain3-questions-N`
branch, each with the `.github/pull_request_template.md` attestation section
filled in and every box checked truthfully, each requesting review from the
`content/**` `CODEOWNERS` owner. No PR touches `content/schemas/`,
`scripts/`, or `.github/workflows/` — that would route the PR into
`claude-review.yml` instead of (or in addition to) the content-only path, per
`skip-paths` in that workflow, which is not this proposal's intent.

**Stage D — human review (out of scope of the automated part, tracked so the
issue's "published" is actually satisfied eventually).** The maintainer
reviews each item against the two `CONTENT-POLICY.md` criteria (evidence
supports the statement; exactly one option is best), adds `reviewed: {by,
at}`, and flips `status: published`. `scripts/validate-content.mjs`'s
`checkLifecycle` is what makes this the only legal path to `published`.

## Alternatives

- **Author all 20 as `draft` regardless of source availability, to sidestep
  the R2-credential question entirely.** Rejected: 2 of the 7 objectives
  already have a captured, current source, so needlessly parking those
  items at `draft` delays review for no reason and produces a worse partial
  result than the two-tier status assignment above.
- **Skip the 5 uncovered objectives and put all 20 questions on the 2
  objectives that already have sources.** Rejected: this satisfies the
  issue's number (20) but not its intent (Domain 3 coverage) and makes the
  `dataset-formats`/`supervised-fine-tuning` skew worse, not better — the
  mock's 6-question `domain-3` draw would still never sample 5 of 7
  objectives.
- **Have this proposal itself run `snapshot:capture` and commit the results.**
  Rejected: this is the issue-investigator, working in a read-only clone
  with no R2 credentials and no write access — it is structurally unable to
  do this regardless of design preference. Captured as an explicit Stage A
  task for the implementer, with the credential question raised rather than
  assumed.
- **Rename the issue's "Domain 3" work to match its parenthetical ("Tool Use,
  Memory & Context Management") by targeting `domain-2` objectives
  (`function-calling`, `agent-sandboxes`) instead.** Rejected as the primary
  interpretation: the issue explicitly says "Domain 3," and
  `content/branding.yaml`'s `domain-3` is an unambiguous, existing,
  machine-checked identifier. Silently reinterpreting "Domain 3" as
  "whatever domain matches this label" would be a bigger, undiscussed
  scope change than proceeding on the id the issue actually names. Flagged
  in requirements.md as the top open question instead.

## Platform impact

- **Migrations:** none — content is flat-file YAML, no database involved
  before the application exists (per `CLAUDE.md`, "the application does not
  exist yet").
- **Backward compatibility:** none broken. New files only; no existing
  question, source, or schema is edited. `content/branding.yaml`'s objective
  map is unchanged, so no existing question can be orphaned by this work.
- **Resource impact:** 20 new YAML files (~1-2 KB each) plus up to 5 new
  source records and their R2 snapshots (full page text, private bucket).
  Negligible.
- **Risks and mitigations:**
  - *Excerpt does not verify against the live snapshot* (paraphrase drift
    between what the agent read and what was actually captured). Mitigation:
    author excerpts by reading the same live `.md` URL that
    `capture-source.mjs` fetches, keep them short and exact, and run
    `npm run lint:content` locally before opening a PR — it cannot catch a
    verbatim mismatch (no network), but it does catch every structural
    error first, so a subsequent `verify:evidence` failure is isolated to
    genuine quoting mistakes.
  - *`needs_review` items citing an uncaptured source fail
    `content-evidence.yml` closed.* Mitigation: Stage B's draft/needs_review
    split above is designed specifically to avoid this — nothing goes to
    `needs_review` without a `snapshot` already on its source record.
  - *R2 credentials unavailable to whichever agent executes tasks.md.*
    Mitigation: tasks.md sequences source capture as an explicit,
    independently-completable task so the rest of the plan (drafting
    `draft`-status items) is not blocked on it; flagged as an open question
    for the human reviewer rather than silently assumed either way.
  - *Content PR cap violation.* Mitigation: Stage C hard-splits at 10 per PR;
    tasks.md tracks this as an explicit DoD.
  - *Domain-label confusion causing content that doesn't match the
    maintainer's actual intent.* Mitigation: requirements.md's top open
    question surfaces this before any PR is opened, and no authored text
    anywhere uses the issue's mismatched label.
