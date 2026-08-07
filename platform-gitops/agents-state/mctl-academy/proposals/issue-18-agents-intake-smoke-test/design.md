# Design: issue-18-agents-intake-smoke-test

## Current state

`mctl-academy` is Phase 0 (`README.md`: "Status — Phase 0 — foundation ...
the application is not built yet"). The repository today contains only:

- Policy and planning docs at the root: `CLAUDE.md`, `CONTENT-POLICY.md`,
  `SOURCES.md`, `LEGAL.md`, `PRIVACY.md`, `PLAN.md`, `CONTRIBUTING.md`,
  `README.md`.
- `content/` — schemas (`content/schemas/{question,lesson,source}.schema.json`)
  and 20 YAML question files plus 8 source YAML files under
  `content/questions/` and `content/sources/`, and `content/branding.yaml`.
- `scripts/` — `validate-content.mjs` (the lint), `verify-evidence.mjs`,
  `capture-source.mjs`, `build-preview.mjs`, `scripts/lib/snapshot-store.mjs`.
- `tests/` — `content-lint.test.mjs`, `verify-evidence.test.mjs`,
  `build-preview.test.mjs`.
- `.github/workflows/ci.yml` — runs `npm run lint:content`,
  `npm run test:content`, and `npm run build:preview` on every PR and push
  to `main`; explicitly does not run citation verification (needs secrets
  unavailable on fork PRs).
- `.github/workflows/claude-review.yml` — reviews PRs that touch anything
  outside `content/{questions,lessons,sources}` (schemas count as code).
  It has a documented fast path: "If the diff is trivial — config/values
  YAML, a dependency bump with no logic change, docs or comments only, or a
  one-line typo — approve with a one-line reason and nothing else."
- `.github/CODEOWNERS` — requires `@mashkovd` approval for `/content/`,
  `/content/schemas/`, the policy docs, and `/.github/workflows/`. Nothing
  in `CODEOWNERS` covers a root-level file like `SMOKE-TEST.md`.
- `Dockerfile` — builds the (not-yet-existent) application container; not
  invoked by CI at Phase 0.

`PLAN.md` section 5 documents the agent dev-loop this proposal is meant to
exercise: a GitHub issue labeled `agents:intake` is picked up by
`run_issue_poller.py`, which starts a Temporal `DevLoopWorkflow`
(`dev-loop-mctlhq-mctl-academy-<issue>`). That workflow resolves the
`issue-investigator` agent release, submits the `mctl-agents-investigate`
Argo CWFT (this run), waits on a durable `wait_condition(approved)`, and
then submits `mctl-agents-implement`, which opens the pull request. Approval
is two independent steps — a Temporal `approve` signal and a `.status.yaml`
`proposed -> accepted` flip merged via a normal gitops PR — and skipping
either produces a failure mode that looks like success (`PLAN.md` section
5, "Approval is two steps, and skipping either fails silently"). `PLAN.md`
section 10 names this exact exercise as a required Phase 0 gate item: "one
end-to-end agent smoke test, run before any real content depends on it."

There is no prior smoke-test artifact in the repository, and no existing
convention for one — this is the first.

## Proposed solution

Add a single new file, `SMOKE-TEST.md`, at the repository root. Its content:

```markdown
# Agent dev-loop smoke test

This file exists because of issue #18 ("agents:intake smoke test"), the
Phase 0 end-to-end verification of the mctl-agents dev-loop described in
`PLAN.md` section 10: an intake issue travels investigate CWFT -> proposal
-> two-step approval (Temporal `approve` signal + `.status.yaml` flip) ->
implement CWFT -> this pull request.

It carries no product meaning and is not part of the application. It may be
removed once the smoke test is confirmed; see the proposal's rollback notes
at `platform-gitops/agents-state/mctl-academy/proposals/
issue-18-agents-intake-smoke-test/` in `mctl-gitops`.
```

Rationale for the shape of the change:

- **Root-level, not under `content/`.** Anything under `content/` triggers
  `CONTENT-POLICY.md`'s `authored.by: agent:<name>` lint rule and CODEOWNER
  review, and is excluded from `claude-review.yml`'s automated pass by
  design (content is gated by evidence CI + a human, not an LLM review —
  `CLAUDE.md`: "An LLM is never the gate"). A smoke test has no evidentiary
  content and should not borrow that gate.
- **Docs-only, not under `.github/workflows/` or `content/schemas/`.**
  Those paths score `3` (`claude-review.yml`'s classify step) and pull the
  heaviest review tier plus CODEOWNERS in the schemas' case — disproportionate
  ceremony for a file whose only job is to exist and be traceable.
  A root `.md` file scores into the "trivial" fast path
  ("docs or comments only ... approve with a one-line reason").
  This still proves the same thing: the implement CWFT can open a PR and
  `claude-review.yml` can act on it — just without spending review budget
  on a change that is not real product surface.
- **A new file, not an edit to an existing doc.** Editing e.g. `README.md`
  or `PLAN.md` to add a smoke-test marker would touch a file with real
  content and dilute its history with a throwaway edit; the diff of a new
  file is also more obviously additive and reversible than a patch to
  existing prose.
- **Self-documenting content.** The file names the issue and points back at
  this proposal directory, so a maintainer who finds it in six months (or a
  future agent scanning the tree) does not have to guess why it exists.

This design intentionally does not touch `mctl-agents`, `mctl-gitops`
registration files, or Temporal/Argo configuration — `PLAN.md` section 5
states those prerequisites are "already satisfied, verify before relying on
them," and the fact that this proposal exists at
`agents-state/mctl-academy/proposals/issue-18-agents-intake-smoke-test/` is
itself evidence the registration and directory bootstrap already happened.
Re-doing that bootstrap is out of scope (see `requirements.md`).

## Alternatives

1. **No code change at all — treat the smoke test as purely operational
   (issue -> proposal -> approve -> observe).** Dropped: `PLAN.md` section
   10 explicitly extends the smoke test through "implement CWFT opens a
   PR," and an implement CWFT with nothing accepted to act on cannot be
   distinguished from the "signal without flip" `skipped_reason` failure
   mode described in section 5. Without an actual proposal to accept, the
   two-step approval logic is never really tested — the whole point of the
   exercise is lost.
2. **A change under `content/` (e.g., a throwaway question or source
   entry).** Dropped: it would need `authored.by: agent:issue-investigator`
   and pass the JSON Schema and lint (`scripts/validate-content.mjs`) to
   avoid failing CI for unrelated reasons, would route through
   `CONTENT-POLICY.md`'s stricter review path and CODEOWNERS instead of
   `claude-review.yml`, and — worst — a "fake" question sitting in the real
   question bank blurs the "every question is original and evidence-backed"
   guarantee the README makes to learners. A smoke test must not pollute
   the content the product actually serves.
3. **A change to CI or workflow config to add a dedicated
   `smoke-test.yml` or similar.** Dropped: `.github/workflows/` is the
   highest review tier in `claude-review.yml`'s own scoring and is
   CODEOWNERS-gated; standing up permanent CI surface for a one-time
   verification is disproportionate, and it is exactly the kind of change
   `claude-review.yml`'s prompt calls out as needing the heaviest scrutiny
   ("Any change that weakens a check ... is a P1").
4. **Modify an existing file (`README.md` "Status" section) to note the
   smoke test.** Considered briefly alongside the new-file option above and
   dropped for the reasons given in "Proposed solution": a throwaway edit
   to a real, load-bearing doc is harder to review at a glance and harder
   to cleanly revert than a whole new file.

## Platform impact

- **Migrations:** none — no database, no schema change.
- **Backward compatibility:** none — this is an additive, isolated file
  with no consumers. Nothing in `scripts/validate-content.mjs`,
  `content/schemas/`, or `ci.yml` references it, so it cannot break the
  content lint, the evidence check, or the preview build.
- **Resource impact:** negligible — one Markdown file, no runtime, no CI
  job change (`ci.yml` already runs lint/test/build on every PR
  unconditionally; this file changes none of their outcomes).
- **Risks:**
  - *Risk:* the smoke-test PR is mistaken for a real product change by a
    future contributor skimming history. *Mitigation:* the file's own
    content states its purpose and origin (issue #18, this proposal path),
    and the commit/PR should use a `chore:` conventional-commit prefix
    making its throwaway nature explicit in `git log`.
  - *Risk:* the implement CWFT interprets this proposal's scope more
    broadly than intended and touches unrelated files. *Mitigation:* this
    design explicitly enumerates the single file and its exact content;
    `tasks.md` DoD checks the diff is exactly one new root-level file.
  - *Risk:* the two approval steps are done correctly but out of the
    documented order the first time, confusing whoever is watching.
    *Mitigation:* `PLAN.md` section 10 already calls for exercising both
    wrong-order failure modes deliberately; `tasks.md` folds that into the
    verification tasks so it is expected, not alarming.
