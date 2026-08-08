# Design: issue-83-fix-content-re-audit-pr-64-evidence-and

## Current state

The content pipeline has two independent gates, as documented in `CLAUDE.md`
and `scripts/validate-content.mjs`'s own header comment:

1. **Structural lint** (`scripts/validate-content.mjs`, run as
   `npm run lint:content` / `bun run lint:content`) — JSON Schema
   (`content/schemas/question.schema.json`, compiled with ajv's 2020-12 build)
   plus cross-file checks: objective map against `content/branding.yaml`,
   duplicate option text, `authored.by` matching `^agent:[a-z0-9-]+$`. It has
   no network access and reads no secrets, so it runs identically on a fork
   PR (`.github/workflows/ci.yml`, job `content`).
2. **Evidence verification** (`scripts/verify-evidence.mjs`, run as
   `verify:evidence`) — for every item whose `status` is `published` or
   `needs_review` (`requiresVerification()`), fetches the cited source's
   private R2 snapshot via `scripts/lib/snapshot-store.mjs` and asserts each
   `evidence[].excerpt` occurs verbatim (after whitespace/quote
   normalization only — case, punctuation, and word order are deliberately
   left significant) inside the snapshot text. This needs
   `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`, which GitHub
   does not expose to fork-triggered workflows, so it lives in its own
   workflow, `.github/workflows/content-evidence.yml`, gated to
   `github.event.pull_request.head.repo.full_name == github.repository` (or a
   push to `main`). Both `on.pull_request` and `on.push: branches: [main]`
   currently run the same full-bank verification unconditionally.

Neither script proves an excerpt *supports* the claim next to it — only that
it exists verbatim in the source. `CONTENT-POLICY.md` puts that semantic
check where a script cannot: "Does the cited evidence support this
statement?" is criterion 1 of the two-criterion human review checklist, and
`.github/CODEOWNERS` requires `@mashkovd` approval on anything under
`/content/`.

Reading the 18 files from PR #64 directly (`content/questions/q-de04e5f6a7b8.yaml`
through `q-pf12a1b2c3d4.yaml`) confirms the issue's audit: `q-de04`, `q-de06`,
and `q-de09` cite `src-rate-limits` with an excerpt
("Lifecycle is deployment state. Readiness is traffic-serving capability.")
that belongs to a different topic and does not verify against that
snapshot — the current, live `Content evidence` failure. Beyond those three,
`q-de05`, `q-de07`, `q-de08`, `q-op03`, `q-pf05` through `q-pf12` all cite one
of four recycled excerpts
(`"Lifecycle is deployment state..."`, `"Both deliver identical model
outputs..."`, `"exist inside a project and inherit its access settings."`,
`"When you sign up for Nebius Token Factory, a personal organization is
created automatically."`) attached to stems on unrelated claims (TTFT/ITL
latency, invitations/RBAC, Bearer-token auth, `/v1/models` context windows,
Playground usage, base URL, model deprecation, temperature, multi-org
membership). These pass `verify-evidence.mjs` today wherever the excerpt
happens to match its own source's snapshot (12 of 15), which is precisely why
a verbatim-only check is not a semantic-support check. Only `q-op04a1b2c3d4`
(personal-organization-on-signup claim, cited to the matching excerpt),
`q-pf03d1e2f3a4`, and `q-pf04e2f3a4b5` (Fast-vs-standard flavor claims, cited
to the matching Fast/standard excerpts) have evidence that is both verbatim
and on-topic as written.

Selection for learners is `status === "published"` only, in two places:
`scripts/build-content-bundle.mjs` (Practice, client bundle) and
`scripts/build-mock-bundle.mjs` (Mock). `needs_review` is already a first-class
status (`content/schemas/question.schema.json` enum:
`draft`/`needs_review`/`published`/`retired`) used today by the weekly
source-drift job per `SOURCES.md` ("dependent content is marked
`needs_review` and removed from new Practice and Mock selection until a human
re-verifies it"). No new mechanism is needed to quarantine an item — flipping
`status` to `needs_review` already removes it from both bundlers while
keeping it enforced by `verify-evidence.mjs` (which still checks
`needs_review` items) and keeping its file, id, and history intact.

`CONTRIBUTING.md` caps content PRs at 10 questions ("a ceiling on review
load"); PR #64 added 18 in one PR, which is a related process gap but not one
the issue's acceptance criteria ask to be mechanically enforced here.

This sandbox's GitHub token cannot read the current branch protection state
for `main` (`gh api repos/mctlhq/mctl-academy/branches/main/protection` ->
`403 Resource not accessible by integration`), and the repo carries no
rules-as-code file (`.github/settings.yml`, a rulesets JSON, etc.) that would
let this investigation infer it by reading files instead. The clone is also a
single-commit shallow clone (`git rev-parse --is-shallow-repository` ->
`true`, one commit in `--all`), so PR #64/#79's actual merge history (who
merged, whether an admin bypass was used, whether "Content evidence /
Verify citations" was even configured as a required check at the time) is not
inspectable from here either. The implementer will need `gh pr view 64`,
`gh api repos/mctlhq/mctl-academy/commits/{sha}/check-runs`, and repo-admin
access to `gh api repos/mctlhq/mctl-academy/branches/main/protection` (or the
newer rulesets API) to close that specific "confirm from history" requirement
from the issue.

## Proposed solution

**1. Re-audit and repair the 18-item batch.** For each of the 18 files, apply
`CONTENT-POLICY.md`'s two review criteria explicitly (not the existing
`authored`/`reviewed` stamps, which the issue correctly treats as unproven).
For the 3 items with defensible evidence as written
(`q-op04a1b2c3d4`, `q-pf03d1e2f3a4`, `q-pf04e2f3a4b5`), record the re-review
and refresh `reviewed.at` to the real re-review timestamp. For the other 15
(including the 3 with outright verbatim failures, which are a subset of this
set: `q-de04e5f6a7b8`, `q-de06a7b8c9d0`, `q-de09d0e1f2a3`), for each item
either:

- **Repair in place**: locate a genuine, ≤25-word, verbatim excerpt from an
  already-`SOURCES.md`-approved source (the four already cited in this batch,
  or another existing `content/sources/*.yaml` entry) that actually supports
  the item's claim, and rewrite whatever combination of `stem`, `options`,
  `explanation`, and `evidence` is needed so the claim and the citation agree.
  Keep the same file and `id` (ids are "assigned once, never changed, never
  reused" per the schema). Update `authored.at` and `reviewed.at` to real
  timestamps for the actual rewrite/review pass. If 25 words cannot support
  the claim, narrow the claim or cite twice, per the schema's own guidance —
  do not paraphrase to fit.
- **Quarantine**: if no approved source defensibly supports a claim worth
  keeping, set `status: needs_review`. This is a one-field change, requires
  no schema/tooling change, and immediately removes the item from
  `build-content-bundle.mjs` and `build-mock-bundle.mjs` selection while
  `verify-evidence.mjs` continues to enforce it (so a quarantined item can't
  quietly drift further while it waits for repair).

This directly resolves the three live `verify-evidence.mjs` failures (they
get repaired, not special-cased) and the broader semantic-mismatch findings,
without touching the verifier itself.

**2. Make the evidence check an actual hard merge gate.** Two independent
failure modes are possible for "PR #64 merged despite a red required check,"
and the fix differs:

- The check was never configured as *required* on `main`'s branch protection
  / ruleset. Fix: add "Content evidence / Verify citations" (workflow job
  `evidence` in `content-evidence.yml`) as a required status check, alongside
  whatever `ci.yml` checks are already required.
- The check was required, but an admin merged past it (GitHub allows repo
  admins to bypass required checks unless "Do not allow bypassing the above
  settings" / the ruleset's bypass list is explicitly locked down). Fix:
  restrict or remove that bypass allowance for `main`, at least for the
  actors who can merge content PRs.

Because this sandbox cannot read the current ruleset, both are written as
verification + remediation tasks for an implementer with admin scope, with
the desired end state specified precisely enough to apply either through the
UI or the API.

**3. Code-only PR ergonomics, gated on 1 and 2 landing first.** The issue is
explicit that a naive `on.pull_request.paths:` filter is the wrong tool here
— GitHub renders a required check as permanently "Expected" on any PR whose
diff never triggers the workflow, which silently defeats the gate this
proposal just restored. Instead, keep `content-evidence.yml`'s `evidence` job
triggering on every same-repo PR (as it does today, no workflow-level path
filter), but make the job itself conditional internally: compute whether the
PR's diff touches `content/**`, `content/schemas/**`,
`scripts/verify-evidence.mjs`, or `scripts/lib/snapshot-store.mjs` (e.g. via
`git diff --name-only ${{ github.event.pull_request.base.sha }}...${{ github.sha }}`
or a `paths-filter`-style step *inside* the job), and skip only the R2 fetch
work when it does not — still exiting 0 and posting a completed status either
way. `push: branches: [main]` keeps running full verification unconditionally
regardless of paths, which the issue requires explicitly ("keep a full-bank
evidence verification on pushes to `main`").

## Alternatives

- **Add an LLM semantic-similarity pass as (part of) the CI gate.** Rejected:
  `CLAUDE.md` states "An LLM is never the gate. The mechanical check is," and
  the issue explicitly forbids using an LLM judgment to decide what stays
  published. An LLM can help a human draft/spot-check during authoring, but
  cannot be the pass/fail signal in CI.
- **Delete/retire the 15 flagged files instead of repair-or-quarantine.**
  Rejected: destroys the objective coverage those files represented for no
  benefit over `needs_review`, which already exists precisely for "was
  published, now withdrawn pending re-verification" (see `SOURCES.md`'s drift
  description) and keeps the id/audit trail intact per the schema's own
  rationale for id stability.
- **Use `on.pull_request.paths:` at the workflow level for the CI ergonomics
  fix.** Rejected per the issue's explicit acceptance criterion: this is the
  filter shape that leaves a required check stuck "Expected" forever on
  non-matching PRs, which is functionally the same as making it
  non-blocking — exactly what the issue says not to do.

## Platform impact

- No database migrations; content is git-tracked YAML, no schema/DB changes.
- Backward compatible: `content/schemas/question.schema.json` and item ids
  are unchanged; only item bodies, `status` fields, and CI workflow internals
  change.
- Resource impact is negligible (CI job runtime only). Selectable bank size
  may drop below the Phase 1 target of 80 (`PLAN.md`) if some of the 15 items
  end up quarantined rather than repaired before this lands — the issue
  explicitly accepts that trade-off ("correctness beats the Phase-1 >=80
  target").
- Risk: the branch-protection/ruleset change needs GitHub repo-admin
  credentials this investigation does not have access to (confirmed via the
  403 above). Mitigation: specify the exact desired state (required check
  name, bypass restriction) precisely in `tasks.md` so a human admin can apply
  it via the Settings UI if the implementer's own token also lacks the scope.
- Risk: repairing the 15 items requires reading the actual private R2
  snapshot text (or refetching the public doc pages on the `SOURCES.md`
  allowlist), which this read-only, no-secrets investigation could not do.
  The implementer must run with real `R2_*` credentials (the same ones
  `content-evidence.yml` already uses) or refetch via
  `scripts/capture-source.mjs`-equivalent logic against the allowlisted
  hosts, and must never invent or approximate an excerpt to make the checker
  pass.
- Risk: re-authoring must stay clean-room per `CONTENT-POLICY.md` — no use of
  "resembles the real exam" as a signal, and the resulting PR description
  must carry the `.github/pull_request_template.md` clean-room attestation,
  checked truthfully.
