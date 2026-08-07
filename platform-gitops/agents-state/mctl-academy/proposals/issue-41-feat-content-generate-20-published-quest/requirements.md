# Author 20 Domain 3 (Data and post-training) questions and route them to human review

## Context

Issue #41 asks for "20 published questions" for "Domain 3 (Tool Use, Memory &
Context Management)" with source citations and per-option feedback.

Two facts from the actual repository state change what this proposal can
promise:

1. **The domain label in the issue does not match this repository's own
   outline.** `content/branding.yaml` defines `domain-3` as *"Data and
   post-training"* (objectives: `files-api`, `datasets`, `dataset-formats`,
   `supervised-fine-tuning`, `fine-tuning-jobs`, `lora-adapters`, `data-lab`).
   "Tool Use" maps to `domain-2/function-calling` and `domain-2/agent-sandboxes`
   in this repo's map; "Memory & Context Management" does not correspond to
   any objective defined anywhere in `content/branding.yaml`. See `## Open
   questions` — this is treated as an error in the issue text, not a request
   to introduce vendor exam-domain language, per `LEGAL.md` and
   `content/branding.yaml`'s own header comment ("These four domains ... are
   NOT the certification's published exam domains").
2. **"Published" is not something a content-authoring pipeline can produce by
   itself.** `content/schemas/question.schema.json` and
   `scripts/validate-content.mjs` (`checkLifecycle`) both require a `reviewed`
   block before `status: published`, and `CONTENT-POLICY.md` / `CLAUDE.md`
   are explicit that the maintainer approves, never authors. The
   Tier-2-implementer-produced deliverable of this proposal is therefore 20
   agent-authored items sitting in `needs_review` (or `draft`, where a cited
   source has no snapshot yet — see design.md), submitted as PRs against the
   `CODEOWNERS`-gated review path. A human flipping `reviewed` + `status:
   published` is the action that actually satisfies the issue's word
   "published"; it is out of scope of the automated part of this proposal.

Today, `domain-3` has exactly 4 published questions, covering 2 of its 7
objectives (`dataset-formats`: `q-df01f3a4b5c6`, `q-df02a4b5c6d7`;
`supervised-fine-tuning`: `q-ft01b5c6d7e8`, `q-ft02c6d7e8f9`). The other 5
objectives (`files-api`, `datasets`, `fine-tuning-jobs`, `lora-adapters`,
`data-lab`) have zero questions and zero source records in
`content/sources/`. Domain 3 is the thinnest domain in the bank relative to
its 7-objective breadth, so this work materially improves mock-exam coverage
(`domain-3` draws 6 of 30 mock questions per `content/branding.yaml`).

## User stories

- AS the mctl Academy maintainer (product owner and reviewer under
  `CONTENT-POLICY.md`) I WANT 20 new, evidence-backed Domain 3 draft items
  queued for review SO THAT I can approve toward the Phase 1 exit bar
  (>=80 published questions across all four domains) without authoring any
  item text myself.
- AS a learner using Practice/Mock mode I WANT every Domain 3 objective to
  have real question coverage SO THAT the mock's 6-question Domain 3 draw
  actually samples the full breadth of "Data and post-training" instead of
  only 2 of its 7 objectives.
- AS the content-writer agent I WANT a documented per-objective source
  inventory SO THAT I only author items against sources that are either
  already snapshotted or explicitly queued for snapshot capture, never
  against an objective with no allowlisted source at all.

## Acceptance criteria (EARS)

- WHEN the content-writer agent authors a new question file under
  `content/questions/` THE SYSTEM SHALL set `authored.by` to an
  `agent:<name>` identifier and leave `reviewed` absent, per
  `CONTENT-POLICY.md` and the `AGENT_AUTHOR` check in
  `scripts/validate-content.mjs`.
- WHEN a new question cites a source THE SYSTEM SHALL cite only
  `content/sources/` records whose `url` host is `docs.tokenfactory.nebius.com`
  or `docs.nebius.com` (the `SOURCES.md` allowlist, enforced by
  `ALLOWED_HOSTS` in both `scripts/validate-content.mjs` and
  `scripts/capture-source.mjs`), with an excerpt of at most 25
  whitespace-separated words quoted verbatim from that source's live text.
- IF a question's cited source has no `snapshot` recorded THEN THE SYSTEM
  SHALL set that question's `status` to `draft` (never `needs_review` or
  `published`) — `scripts/verify-evidence.mjs`'s `requiresVerification`
  enforces citation verification for both `needs_review` and `published`,
  and an unsnapshotted source fails that check closed.
- WHEN a source needed for an objective does not yet exist under
  `content/sources/` THE SYSTEM SHALL capture it with
  `npm run snapshot:capture -- <url> --id <src-id> --objective domain-3/<objective>`
  before any citing question is allowed past `draft`.
- WHEN the 20 questions are complete THE SYSTEM SHALL distribute them across
  all 7 `domain-3` objectives in `content/branding.yaml`, not concentrate
  them on the 2 objectives that already have coverage.
- WHILE any PR is open THE SYSTEM SHALL keep each content PR at or under 10
  questions, per the `CONTRIBUTING.md` review-load cap, requiring at least 2
  PRs for 20 questions.
- WHEN a content PR is opened THE SYSTEM SHALL target a `feat/`-prefixed
  branch (not starting with `_`), never commit to `main`, and include the
  `.github/pull_request_template.md` content-attestation checklist fully
  checked.
- THE SYSTEM SHALL NOT introduce the phrase "Tool Use, Memory & Context
  Management," or any other certification-domain wording not already present
  in `content/branding.yaml`, into any question, option, or explanation text
  — per `LEGAL.md` naming rules and the branding file's own
  not-the-official-domains disclaimer.
- IF a question is not yet publishable (no snapshot, or awaiting human
  review) THEN THE SYSTEM SHALL leave `status` at `draft` or `needs_review`
  and never set `status: published` itself, since only a human `reviewed`
  entry makes that legal under `checkLifecycle` in
  `scripts/validate-content.mjs`.
- WHEN each option is authored THE SYSTEM SHALL give every one of the 4
  options (not only the correct one) a distinct `explanation` of at least 12
  characters, and THE SYSTEM SHALL vary the position of the correct option
  across the 20 items so the whole bank does not trip the
  answer-position-bias check in `scripts/validate-content.mjs` (fires if
  any one position exceeds 50% of all questions once the bank has >=12
  items — it already does).

## Out of scope

- Actually flipping any question to `status: published` — that requires a
  human `reviewed` block and is explicitly reserved to the maintainer by
  `CONTENT-POLICY.md`.
- Adding a "Memory & Context Management" objective (or any new objective) to
  `content/branding.yaml`. If the maintainer wants that concept covered, it
  is a separate, deliberate change to the objective map — see
  `content/branding.yaml`'s own instruction that objectives are "add[ed]
  freely; retire them deliberately," which implies a conscious edit, not a
  side effect of a content-generation issue.
- Writing or editing lessons (`content/lessons/`) — none exist in the repo
  yet, and the issue only asks for questions.
- Changing `content/schemas/`, `scripts/validate-content.mjs`, or CI
  workflows.
- Running `npm run verify:evidence` against the real R2 store as part of
  this proposal's own verification — that needs live `R2_ACCOUNT_ID` /
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` credentials this
  read-only investigation clone does not have (see Open questions).

## Open questions

- **Domain label mismatch (highest priority for the reviewer to weigh in
  on).** The issue's parenthetical, "Tool Use, Memory & Context Management,"
  does not match `content/branding.yaml`'s `domain-3` title ("Data and
  post-training") and does not correspond to any objective defined there.
  This proposal proceeds using the repository's actual `domain-3` definition
  and objectives, and deliberately does not use the issue's wording anywhere
  in authored content, per `LEGAL.md`. If the issue's label was meant to
  describe a *different* domain (Tool Use lives under `domain-2` today), that
  is a separate, smaller proposal against `domain-2/function-calling` and
  `domain-2/agent-sandboxes`, not this one.
- Does the Tier 2 implementer's execution environment have
  `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` available to
  run `npm run snapshot:capture`, or is source capture for the 5
  currently-unsourced objectives a manual, maintainer-run step? The GitHub
  Actions jobs that use these secrets (`content-evidence.yml`,
  `source-drift.yml`) are same-repo triggered CI jobs, not obviously the same
  execution context as an agent-authored PR branch. If capture cannot run
  automatically, this proposal's tasks.md still produces valid `draft`-status
  items for the 5 uncovered objectives; they simply cannot progress to
  `needs_review` until a human (or a differently-privileged run) captures
  the sources.
- Exact split of 20 items across 7 objectives is left to the implementer's
  judgment (see design.md for a suggested 3/3/3/3/3/3/2 distribution); no
  acceptance criterion pins an exact per-objective count, only "all 7
  covered, none concentrated only on the existing 2."
