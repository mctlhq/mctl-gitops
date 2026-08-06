# Point contributors to CONTENT-POLICY.md before they open a content PR

## Context

Issue #14 is a throwaway smoke test of the Temporal `DevLoopWorkflow` dev-loop
pipeline (issue-investigator -> approval -> implementer -> PR) for the
`mctl-academy` service, per `PLAN.md` section 10 ("Phase 0 also includes one
end-to-end agent smoke test"). It is a retry of #12/#13, both of which were
blocked by infrastructure issues that are now fixed (release-please freeze on
`mctl-agents#110`, manual CWFT image-tag bump via `mctl-gitops#724`). The PR
this proposal produces will be closed without merging regardless of its
content — the goal is exercising the pipeline mechanics, not shipping a real
change.

The nominal task, taken from the issue body, is small and self-contained: add
a short paragraph to `CONTRIBUTING.md` pointing contributors to
`CONTENT-POLICY.md` before they open a content PR, "if such a pointer does not
already exist."

Having read the current `CONTRIBUTING.md` in this clone, that pointer already
exists. The "Clean-room rules" section (between "Closed at MVP: content pull
requests from forks" and "Workflow") reads:

```
## Clean-room rules

If you contribute anything under `content/`, read
[`CONTENT-POLICY.md`](CONTENT-POLICY.md) first. It is binding.
```

This already precedes the "Workflow" and "Review gates" sections a
content contributor would reach before opening a PR, and it already names
`CONTENT-POLICY.md` as binding. The issue's own conditional ("if such a
pointer does not already exist") is therefore not satisfied — a pointer
exists. See `design.md` for how this proposal resolves that without either
duplicating the sentence or leaving the smoke test with a no-op diff.

## User stories

- AS a first-time content contributor I WANT `CONTRIBUTING.md` to tell me,
  in terms that unambiguously mean "before you open a PR," to read
  `CONTENT-POLICY.md` SO THAT I do not draft content and then discover the
  authorship/provenance rules only at review time.
- AS the maintainer running this smoke test I WANT a minimal, real,
  reviewable diff to `CONTRIBUTING.md` SO THAT the implement CWFT has
  something concrete to open a PR against, exercising the full pipeline.

## Acceptance criteria (EARS)

- WHEN a contributor reads `CONTRIBUTING.md` up to and including the section
  that precedes "Workflow" THE SYSTEM SHALL have presented a pointer to
  `CONTENT-POLICY.md` that is phrased in terms of timing relative to opening
  a content PR (e.g. "before you open a content pull request"), not only
  "read this first."
- WHEN the diff is produced THE SYSTEM SHALL touch only `CONTRIBUTING.md`,
  changing at most a few lines (per the issue's explicit "keep the diff
  minimal" instruction).
- IF a pointer to `CONTENT-POLICY.md` already exists in `CONTRIBUTING.md`
  THEN THE SYSTEM SHALL strengthen/clarify that existing pointer in place
  rather than add a second, near-duplicate paragraph elsewhere in the file.
- WHILE editing THE SYSTEM SHALL NOT change `CONTENT-POLICY.md`, `SOURCES.md`,
  `LEGAL.md`, schemas, or anything under `content/` — this is a docs-only
  change.
- WHEN the PR is opened THE SYSTEM SHALL use a conventional-commit subject
  under 72 characters (e.g. `docs: clarify when to read CONTENT-POLICY.md`)
  and a branch name that does not start with `_`, per `CLAUDE.md` and
  `CONTRIBUTING.md` conventions.
- WHEN the PR is opened THE SYSTEM SHALL NOT include the content-attestation
  checklist from `.github/pull_request_template.md` as a section requiring
  checked boxes, since this PR touches no file under `content/` (the template
  itself says to delete that section for docs-only changes).

## Out of scope

- Any change to the actual clean-room policy, source allowlist, or schemas.
- Any change to `content/` — this is a docs-only smoke test PR, and it will
  be closed unmerged regardless of outcome.
- Fixing or re-verifying the release-please / CWFT image-tag infrastructure
  issues described in the issue body — those are already resolved and are
  context, not part of this task.
- Driving the Temporal `approve` signal, the `.status.yaml` flip PR, or
  verifying the implement CWFT's resulting PR — those are orchestration steps
  the issue describes as being exercised around this proposal, not steps this
  proposal's own tasks perform.

## Open questions

- The issue's literal condition ("if such a pointer does not already exist")
  is false in this clone — a pointer exists. Resolution adopted here: treat
  the issue's intent (a pointer to `CONTENT-POLICY.md` that is unambiguously
  positioned *before* content-PR submission) as the acceptance bar, and close
  the gap between the existing wording ("read ... first") and the issue's
  literal wording ("before they open a content PR") with a small in-place
  edit rather than a no-op or a duplicate paragraph. This keeps the smoke
  test's PR real and reviewable without contradicting the issue's own
  "if not already present" guard.
- Whether the maintainer would prefer a true no-op (skip the edit entirely,
  since the substance already exists) is left to human review at the
  `.status.yaml` approval step — the diff proposed here is small enough to
  discard trivially if so.
