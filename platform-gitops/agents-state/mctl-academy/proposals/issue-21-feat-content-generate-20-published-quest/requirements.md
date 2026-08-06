# feat(content): 20 published questions for Domain 2 (Inference and agent integration)

## Context

Issue #21 asks for 20 reviewed items for "Domain 2 (Agent Architecture &
Orchestration)" with source-documentation evidence citations and per-option
feedback. The issue title's domain label does not match `content/branding.yaml`,
which is the single source of truth for domain names (see "Open questions"):
the actual `domain-2` there is titled "Inference and agent integration",
weight 35 (the largest of the four), with 7 objectives: `chat-completions`,
`embeddings-and-rerank`, `retrieval-pipelines`, `function-calling`,
`structured-output`, `framework-integrations`, `agent-sandboxes`.

Today `content/questions/` holds 20 published questions total (the Phase 0
seed set — `PLAN.md` calls for "20 reviewed questions, minimum 3 per domain").
Of those, 7 belong to `domain-2`, and all 7 sit on only two of its seven
objectives: `function-calling` (4 questions, source `src-function-calling`)
and `structured-output` (3 questions, source `src-structured-output`). The
other five `domain-2` objectives have no source record under
`content/sources/` at all. Per `SOURCES.md`, "an objective with no approved
source stays unpublished rather than being covered from general knowledge" —
so today those five objectives cannot produce a single published question,
regardless of authoring effort.

This matters for the exam-prep value of the course: `domain-2` carries the
highest study-time weight (35) and the most mock-exam slots (10 of 30), but
five-sevenths of its objective map is currently unbuild-able. Closing that gap
is the real work behind "generate 20 questions" — the questions themselves are
mechanical once each objective has an evidence-backed source.

## User stories

- AS the course maintainer (product owner and reviewer under
  `CONTENT-POLICY.md`) I WANT 20 new published `domain-2` questions spread
  across its under-covered objectives SO THAT Practice and Mock draw from a
  domain-2 bank that reflects the course's own weighting instead of two
  objectives out of seven.
- AS a learner I WANT every `domain-2` objective to have practice questions
  SO THAT I am not silently skipping topics the course claims to cover.
- AS the content-authoring agent I WANT a documented, mechanically checkable
  path from "objective with no source" to "published question" SO THAT this
  gap does not recur for `domain-1`, `domain-3`, or `domain-4`.
- AS the human reviewer I WANT every new item to arrive already passing
  `npm run lint:content` and citing a snapshot-backed source SO THAT my review
  time goes to the two policy criteria (evidence supports the claim; exactly
  one option is best) and not to formatting.

## Acceptance criteria (EARS)

- WHEN a source record is added for a previously source-less `domain-2`
  objective THE SYSTEM SHALL require its `url` host to be on the `SOURCES.md`
  allowlist (`docs.tokenfactory.nebius.com` primary, `docs.nebius.com`
  secondary) and its `objectives` entries to exist in `content/branding.yaml`.
- WHEN a new question is authored THE SYSTEM SHALL set `authored.by` to an
  `agent:<name>` identifier, never a human name, per `CONTENT-POLICY.md` and
  the lint's `AGENT_AUTHOR` check in `scripts/validate-content.mjs`.
- WHEN a new question cites evidence THE SYSTEM SHALL keep the excerpt to at
  most 25 whitespace-separated words, quoted verbatim from the cited source's
  captured snapshot.
- WHILE a question's cited source has no `snapshot` block or has
  `status: drifted` THE SYSTEM SHALL keep that question's `status` at `draft`
  or `needs_review`, never `published` — `checkEvidence()` in
  `scripts/validate-content.mjs` enforces this.
- WHEN a question is proposed for `status: published` THE SYSTEM SHALL require
  a `reviewed` block (`by`, `at`) added by a human `CODEOWNERS` owner —
  `checkLifecycle()` rejects `published` without it, and under
  `CONTENT-POLICY.md` the maintainer is reviewer, never author.
- WHEN a batch of new questions is opened as a pull request THE SYSTEM SHALL
  contain at most 10 questions per PR (`CONTRIBUTING.md`, PR template) — 20
  questions therefore span at least 2 PRs.
- WHEN a content PR is opened THE SYSTEM SHALL carry the clean-room
  attestation checkboxes from `.github/pull_request_template.md`, unchecked
  boxes blocking merge.
- IF a content PR is opened from a fork THEN THE SYSTEM SHALL NOT be accepted
  (`CONTRIBUTING.md`) — this work happens on a branch inside
  `mctlhq/mctl-academy`.
- WHEN `npm run lint:content` runs over the new files THE SYSTEM SHALL report
  zero errors, including: unique option ids `a`-`d`, no duplicate option text,
  objective belongs to its declared domain, and (bank-wide, once ≥12
  questions exist) no single answer position holding more than 50% of correct
  answers.
- WHILE `npm run test:content`'s 15 rule-violation tests exist THE SYSTEM
  SHALL continue to pass unmodified — this proposal adds content, not lint
  behavior.
- WHEN all 20 questions are merged to `main` with `status: published` THE
  SYSTEM SHALL show every one of the 7 `domain-2` objectives represented by at
  least one published question (subject to the sourcing step landing first;
  see Open questions).

## Out of scope

- Building the application (React/Vite client, Express API, database) — per
  `CLAUDE.md`, "the application does not exist yet." This proposal is content
  only.
- Automating source capture or drift-checking in CI. `scripts/capture-source.mjs`
  already exists and is invoked manually/by a credentialed job; this proposal
  uses it as-is rather than changing it.
- Changing `content/branding.yaml` domain weights, objective ids, or titles.
- Adding lessons (`content/lessons/`) for `domain-2` — the issue asks for
  questions only.
- Retiring or editing the 7 existing `domain-2` questions.
- Relaxing the 10-question-per-PR cap or the fork-PR restriction.
- Standing up the R2 snapshot store or Vault credentials if they do not
  already exist for this repo — this proposal assumes
  `academy-source-snapshots` and its CI secrets are already provisioned, since
  `content-evidence.yml` and the existing published questions depend on them
  today.

## Open questions

- **Domain label mismatch.** The issue title says "Domain 2 (Agent
  Architecture & Orchestration)"; `content/branding.yaml`'s `domain-2` is
  titled "Inference and agent integration" and there is no domain anywhere in
  the branding map called "Agent Architecture & Orchestration." The closest
  conceptual match within `domain-2` is the `agent-sandboxes` objective
  ("Sandboxes, MCP, and SDK-driven agent execution"). Resolution taken here:
  treat the issue as targeting `branding.yaml`'s `domain-2` by id, since that
  is the only mechanically checkable domain-2 the lint and schema recognize,
  and flag the title text as stale/aspirational rather than blocking on it.
- **"20 questions" — net-new or total?** The issue could mean "the domain-2
  bank should have 20 published questions" (13 net-new, since 7 already
  exist) or "add 20 more" (27 total). Resolution taken here: 20 **net-new**
  published questions, matching the literal issue title ("generate 20
  published questions") and body ("generate 20 reviewed items"), landing
  domain-2 at 27 published questions total.
- **Distribution across objectives.** Nothing in the issue specifies how the
  20 should split across the 7 objectives. Resolution taken here: bring every
  currently source-less objective (`chat-completions`,
  `embeddings-and-rerank`, `retrieval-pipelines`, `framework-integrations`,
  `agent-sandboxes`) up to at least 3 questions each (15 questions), and add 5
  more spread across the two already-sourced objectives to keep them from
  becoming stale relative to the rest of the domain. This is a judgment call
  for the human reviewer to override, not a hard requirement.
- **Who runs `capture-source.mjs`.** It needs `R2_ACCOUNT_ID` /
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`, the same secrets
  `content-evidence.yml` uses. It is unclear whether the Tier 2 implementer
  agent's execution environment has these (Vault-backed) credentials
  available, or whether source capture for the 5 new objectives must be a
  separate, human/credentialed step before the implementer drafts questions
  against them. Resolution taken here: tasks.md treats source capture as its
  own task with an explicit fallback (open with sources still missing,
  `status: draft`, and call it out in the PR) if credentials are unavailable
  to the automated path.
- **Canonical doc URLs for the 5 new objectives.** This proposal does not
  pre-select exact `docs.tokenfactory.nebius.com` page URLs for
  `chat-completions`, `embeddings-and-rerank`, `retrieval-pipelines`,
  `framework-integrations`, and `agent-sandboxes` — that is a research step
  for whoever implements this (mirroring how `src-function-calling.yaml` and
  `src-structured-output.yaml` point at specific `.md` pages). Left to
  implementation; captured as Task 1 in tasks.md.
