# Design: issue-14-smoke-test-verify-temporal-dev-loop-pipe

## Current state

`CONTRIBUTING.md` (repo root, 65 lines) is organized as:

1. `## Open to everyone` — issues, question reports, code PRs.
2. `## Closed at MVP: content pull requests from forks` — explains the R2
   snapshot / fork-secrets limitation.
3. `## Clean-room rules` — the existing pointer:
   ```
   If you contribute anything under `content/`, read
   [`CONTENT-POLICY.md`](CONTENT-POLICY.md) first. It is binding.
   ```
   followed by a one-paragraph summary of the attestation requirement.
4. `## Workflow` — conventional commits, branch naming, semver tags.
5. `## Review gates` — table distinguishing code review gate vs. content gate
   (schema lint, verbatim citation verification, human CODEOWNER approval).
6. `## Local development` — placeholder, app does not exist yet.

`CONTENT-POLICY.md` (repo root) is the binding policy this pointer refers to:
authorship (`agent:<name>` only), the two-criterion review checklist, and the
attestation requirement, matching `.github/pull_request_template.md`'s
"Content attestation" section (lines 5-24), which itself already links back
to `CONTENT-POLICY.md` and instructs deleting that section for non-content
PRs.

`.github/CODEOWNERS` gates `/CONTENT-POLICY.md` itself (and `/content/`,
`/SOURCES.md`, `/LEGAL.md`, `/PRIVACY.md`) behind `@mashkovd` approval —
consistent with `CLAUDE.md`'s statement that policy documents get the same
review gate as content.

So: the pointer the issue asks for already exists, positioned before
"Workflow" and "Review gates" in reading order, i.e. structurally before a
contributor would act on PR conventions. What it does not do is use language
tied to the *event* of opening a PR ("read ... first" is about reading order
generally, not specifically about the PR-opening moment the issue calls out).

## Proposed solution

Edit only the existing sentence in `## Clean-room rules`, in place, from:

```markdown
If you contribute anything under `content/`, read
[`CONTENT-POLICY.md`](CONTENT-POLICY.md) first. It is binding.
```

to:

```markdown
Before you open a content pull request, read
[`CONTENT-POLICY.md`](CONTENT-POLICY.md). It is binding.
```

This is a two-line diff (one line changed, effectively) that:

- Directly answers the issue's ask in its own words ("pointing contributors
  to CONTENT-POLICY.md before they open a content PR").
- Does not duplicate the existing paragraph or introduce a second, redundant
  pointer elsewhere in the file — avoiding the drift risk of two places in
  the same doc saying almost the same thing with different wording.
- Requires no change to `CONTENT-POLICY.md`, `SOURCES.md`, `LEGAL.md`,
  schemas, or `content/`, keeping this PR out of the CODEOWNERS content gate
  and the content-attestation checklist entirely — it is a plain docs/code PR
  under `claude-review.yml`, not the content pipeline
  (`CONTENT-POLICY.md`/CODEOWNERS gate) the issue is explicitly not
  exercising.
- Stays inside the section boundary CI would expect: `git diff --stat` shows
  one file, `CONTRIBUTING.md`, a handful of changed lines — matching the
  issue's "Keep the diff minimal -- a few lines."

No other file is touched. No schema, script, or test in `scripts/` or
`tests/` references `CONTRIBUTING.md` (checked: `scripts/validate-content.mjs`
and `tests/content-lint.test.mjs` operate on `content/**`, not root-level
docs), so this change carries no risk of breaking `npm run lint:content` or
`npm run test:content`.

## Alternatives

1. **True no-op (skip the edit, since a pointer already exists).**
   Matches the issue's literal conditional most conservatively, but leaves
   the implement CWFT with nothing to commit, which defeats the purpose of
   this specific smoke test step (issue #14 exists specifically to confirm
   the implement CWFT opens a PR). Rejected: the issue's stated *purpose*
   ("confirm ... the implement CWFT opens a PR") outweighs a literal reading
   of a conditional clause that turned out to be false when checked against
   real repo state.

2. **Add a second, new paragraph elsewhere (e.g. under "Open to everyone" or
   at the top of the file) instead of editing the existing one.**
   Produces a real diff and satisfies the issue's literal ask without
   touching existing text, but creates two slightly different statements of
   the same rule in one document — a maintenance hazard exactly like the one
   `CLAUDE.md` warns against for `content/branding.yaml` (single source of
   truth for naming). Rejected in favor of editing the existing sentence.

3. **Move the "Clean-room rules" section earlier in the file (e.g. before
   "Closed at MVP"), on the theory that "before they open a PR" means
   "earlier in the document."**
   Larger diff (section reordering) for no behavioral gain — the existing
   position already precedes "Workflow," which is the section a contributor
   reads when actually about to open a PR. Rejected: reordering is not
   "a few lines," and the wording gap identified above is a smaller, more
   targeted fix.

## Platform impact

- **Migrations:** none — docs-only change.
- **Backward compatibility:** none affected; no code, schema, or CI behavior
  changes.
- **Resource impact:** none — no service redeploy, no new dependency.
- **Risks:**
  - Risk: the PR gets merged instead of closed (issue explicitly says it
    will be closed regardless of content). Mitigation: none needed from this
    proposal's side — that is an operator action outside the implement
    CWFT's control; the content of the change is safe to merge or discard
    either way since it is a strict wording improvement with no factual
    change.
  - Risk: `claude-review.yml` (automated code review, applies to non-content
    changes per `CLAUDE.md`) flags something. Mitigation: the change is a
    single-sentence wording edit with no ambiguity; expected to pass cleanly.
  - Risk: this proposal is itself a repeat of a step already effectively
    exercised by PR-producing steps in #10-#13's earlier attempts. Mitigation:
    none of #10-#13 reached the implement-CWFT-opens-a-PR step successfully
    per the issue body (they failed earlier, on registry and service
    registration bugs) — this is the first attempt with those blockers
    cleared, so the step is not actually redundant.
