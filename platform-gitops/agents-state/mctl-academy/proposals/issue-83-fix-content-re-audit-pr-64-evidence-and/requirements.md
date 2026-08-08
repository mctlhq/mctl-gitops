# Re-audit PR #64 evidence and restore the content evidence merge gate

## Context

PR #64 (`1ba8078596c2cbd90895a54160bf4d69a29fe75a`) added 18 `published`
questions to grow the bank from 64 to 82, hitting the `PLAN.md` Phase 1 target
of >=80. Its own `Content evidence` run (`31202767629`) failed before merge:
three files (`q-de04e5f6a7b8.yaml`, `q-de06a7b8c9d0.yaml`,
`q-de09d0e1f2a3.yaml`) cite `src-rate-limits` with the excerpt "Lifecycle is
deployment state. Readiness is traffic-serving capability." — an excerpt that
does not exist verbatim in that snapshot. Reading the batch directly in this
clone confirms it is worse than three typos: `q-de05f6a7b8c9.yaml` reuses that
exact same lifecycle/readiness excerpt for a TTFT/ITL latency-metrics
question, and inspection of all 18 files shows a small set of excerpts
(`"Lifecycle is deployment state..."`, `"Both deliver identical model
outputs..."`, `"exist inside a project and inherit its access settings."`,
`"When you sign up for Nebius Token Factory, a personal organization is
created automatically."`) copy-pasted across stems on unrelated topics
(billing, RBAC, authentication, model catalog, Playground, deprecation,
multi-org membership). `scripts/verify-evidence.mjs` only proves an excerpt
exists verbatim in a snapshot; it cannot and does not prove the excerpt
supports the specific claim in the question it's attached to. That semantic
gap is exactly what `CONTENT-POLICY.md`'s two-criterion review checklist
("does the cited evidence support this statement?", "is exactly one option
best?") exists to catch, and it did not catch it here — the batch's
`authored.at`/`reviewed.at` timestamps are a single minute apart
(`2026-08-07T19:30:00Z` / `:19:31:00Z`) across 18 items, which is metadata,
not evidence that the two-criteria review was actually performed per item.

Despite the `Content evidence` workflow failing on PR #64 itself, the PR
merged into `main`. `main` has been red on that check ever since, and it
surfaced again on the unrelated, code-only PR #79 (run `31245715701`) because
`.github/workflows/content-evidence.yml` currently runs
`verify:evidence` against the full bank on every same-repo pull request, not
just ones that touch content. Both problems need fixing: the content itself,
and the fact that a failing evidence run was mergeable at all.

## User stories

- AS a learner using Practice or Mock mode, I WANT every `published`
  question's citation to genuinely support its claim SO THAT I can trust the
  practice material is accurate rather than a plausible-looking distractor
  factory.
- AS the content CODEOWNER, I WANT the `Content evidence` check to be a true
  hard merge gate SO THAT a red evidence run can never land on `main` again
  regardless of who merges or how.
- AS a contributor opening an unrelated code PR, I WANT the evidence workflow
  to stop reporting red because of pre-existing content defects SO THAT my
  PR's checks are meaningful, without the fix weakening content integrity or
  leaving a required check permanently stuck pending.

## Acceptance criteria (EARS)

- WHEN any of the 18 questions introduced by commit `1ba8078596c2cbd90895a54160bf4d69a29fe75a` is reviewed, THE SYSTEM SHALL record an explicit pass/fail against both CONTENT-POLICY.md criteria (evidence supports the statement; exactly one option is best) rather than relying on the batch's existing `authored`/`reviewed` timestamps as evidence that review occurred.
- IF a reviewed item's cited evidence does not verbatim-and-semantically support its claim, THEN THE SYSTEM SHALL either rewrite the item (stem, options, and/or evidence) so it is supported by a genuine excerpt from an already-approved `SOURCES.md` source, or set its `status` away from `published` (`needs_review`) so it is withdrawn from learner selection.
- THE SYSTEM SHALL NOT keep any item `published` whose evidence excerpt is not verified verbatim by `scripts/verify-evidence.mjs` against the real R2 snapshot.
- WHEN `bun run lint:content`, `bun run verify:evidence`, and `bun run test:content` are run against the repaired content tree, THE SYSTEM SHALL exit 0 for all three.
- THE SYSTEM SHALL NOT weaken `scripts/verify-evidence.mjs` (its normalization, its verbatim matching, or its fail-closed behavior for `published`/`needs_review` items) to make the three current `src-rate-limits` failures pass.
- THE SYSTEM SHALL NOT use an LLM judgment, exam recollection, or resemblance to a real exam item as a review or authoring signal, per `CONTENT-POLICY.md`.
- WHEN a future pull request introduces or leaves a `published`/`needs_review` item with a failing `Content evidence` check, THE SYSTEM SHALL prevent that pull request from being merged through the normal merge path.
- WHILE a pull request only changes files outside `content/`, `content/schemas/`, `scripts/verify-evidence.mjs`, and `scripts/lib/snapshot-store.mjs`, THE SYSTEM SHALL still report a completed (not permanently "Expected"/pending) status for the `Content evidence` required check, skipping only the expensive R2 verification itself.
- WHEN a push lands on `main`, THE SYSTEM SHALL run full-bank evidence verification against the real R2 store unconditionally (no path filtering on the `push` trigger).
- THE SYSTEM SHALL NOT achieve the code-only-PR ergonomics improvement by making `Content evidence` non-blocking, nor by using a workflow-level `on.pull_request.paths:` filter that would leave a required check stuck "Expected" on non-matching PRs.
- WHEN the resulting pull request is opened, THE SYSTEM SHALL include the clean-room attestation from `CONTENT-POLICY.md` / `.github/pull_request_template.md`, checked truthfully.
- IF the number of `published` questions falls below the Phase 1 target of 80 as a result of quarantining unsupported items, THEN THE SYSTEM SHALL accept that outcome rather than keep unsupported items `published` to preserve the count.

## Out of scope

- Building the mctl-academy application/API — per `CLAUDE.md`, the app does
  not exist yet; this is Phase 0 content-and-policy work only.
- Re-reviewing the 64 questions that predate PR #64. The issue scopes the
  re-audit to the 18-item batch from commit `1ba8078...`.
- Adding new sources to `SOURCES.md`. Any repair must cite sources already on
  the allowlist (`src-rate-limits`, `src-endpoint-lifecycle`,
  `src-org-projects`, `src-inference-overview`, or another already-approved
  source), not a newly onboarded one.
- Retroactively enforcing `CONTRIBUTING.md`'s "content PRs capped at 10
  questions" rule against PR #64's 18-question batch. It is a related process
  gap worth flagging in the PR description, but the issue's acceptance
  criteria do not ask for a mechanism change here; only the evidence gate is
  in scope for merge-gate enforcement.
- Changing `content/branding.yaml` domain weights or the objective map.

## Open questions

- Whether repaired items keep their existing `id` (schema: "assigned once,
  never changed, never reused") with rewritten body content, versus being
  retired and replaced by a freshly authored item under a new id. Adopted
  interpretation: repair in place under the same id when a genuine supporting
  excerpt exists for the same objective; only fall back to `needs_review`
  (never delete the file) when no such excerpt exists, preserving the audit
  trail the schema comments describe.
- The exact current branch-protection/ruleset configuration for `main` cannot
  be read from this sandbox — `gh api repos/mctlhq/mctl-academy/branches/main/protection`
  returns `403 Resource not accessible by integration` under this
  investigator's credentials, and no rules-as-code file exists in the repo to
  inspect instead. The implementer will need a GitHub token with repo admin
  scope to both diagnose why PR #64 merged red and to configure the required
  check going forward. This is recorded as a task, not resolved here.
- Whether `reviewed.by`/`reviewed.at` should be updated for items whose
  content is unchanged after re-review (the 3 the issue calls out as
  currently defensible: `q-op04a1b2c3d4`, `q-pf03d1e2f3a4`,
  `q-pf04e2f3a4b5`). Adopted interpretation: yes — update `reviewed.at` to the
  real re-review timestamp so the record reflects that the two-criteria check
  actually ran, rather than leaving the original bulk-stamp as the only
  evidence of review.
