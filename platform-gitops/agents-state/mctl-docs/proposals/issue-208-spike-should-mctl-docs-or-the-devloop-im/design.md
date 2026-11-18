# Design: issue-208-spike-should-mctl-docs-or-the-devloop-im (narrowed)

Proposal only; no implementation approval. This is the operator-selected narrow follow-up of 2026-11-17 and
supersedes the earlier experiment-first design (scratch repo, Actions jobs, PostgreSQL/Docker runs, five
repeats). That design was never executed and none of its results is claimed. PR #211 research is reused as
provenance; it is open and unmerged, with SQL examples and results `NOT_RUN`.

## Current state (mctl-docs `main` 59cf0d2ef97ab86d0a5513c8f6e330a9606e8f80, source only)

- `docs/guides/databases.md`: front matter, then `# Database Provisioning`, `## Provision a Database`,
  `## Configuration`, `## Supported Databases`. Describes `mctl_provision_database`, the `DB_HOST/DB_PORT/
  DB_NAME/DB_USER/DB_PASSWORD` variables and that `DATABASE_URL` is not guaranteed. No migration content.
- `docs/guides/scaffolding.md` headings: `# Scaffolding a service for mctl deploy`, `## Platform health
  checks`, `## Container requirements`, `## Pick a template by language`, `## Node.js`, `## Python`,
  `## Go`, `## Static (Vue / React build → nginx) {#static}`, `## When does the deploy fire?`,
  `## Pre-merge docker build (recommended)`, `## CI auto-deploy job`, `## First-time onboard checklist`.
  It has PR-only docker build guidance and warns not to put skipped PR-only jobs into deploy `needs:`. That
  distinction can be reused as prose.
- Earlier GitOps reads (chart `dbInitJob` is an optional PostSync hook that waits for a table; some services
  migrate on start under an advisory lock) show the platform does not order tenant migrations. These are
  desired-configuration observations, not proof of runtime behaviour, and the migration tool per service is
  unknown.

## Proposed guide (not approved)

Primary page: `docs/guides/databases.md`, new section (proposed heading `## Schema migrations and parallel
PRs`), appended after existing sections so existing anchors are unchanged. Content, in order:

1. **Why Git-clean is not apply-clean.** Two PRs branch from one schema state; each is tested alone. Hazards:
   duplicate or colliding versions; ordering differing between environments; two changes that each assume the
   pre-merge schema (for example both add `NOT NULL` columns, or one renames what the other indexes); a merge
   that applies without error but yields a schema neither author tested (last writer wins).
2. **Unique versions and order.** Use collision-resistant version identifiers and one place that runs
   migrations; advisory locks serialize concurrent runs but do not detect logical conflicts.
3. **Expand/contract and old/new compatibility.** During a rollout old and new app versions overlap, so the
   schema must serve both: add compatible structure first, switch the app, remove old structure in a later
   change.
4. **Two different verifications.** Deployment onto an empty database shows the migration set applies from
   scratch. Upgrading the supported previous schema populated with synthetic data shows the real upgrade
   path. The first does not prove the second.
5. **Recovery.** Rolling back the application image does not roll back the database. Choose a coordinated
   forward fix, or a schema/data rollback that was verified separately beforehand (backup and restore
   support is not assumed here).
6. **Role split.** The application (or tenant tooling) owns its migrations; the platform provisions the
   database and credentials and does not run, order or check tenant migrations.
7. **Opt-in merge-result check (idea, recommendation only).** A tenant may run, in its own CI on pull
   requests, a job that evaluates the merge result rather than the branch alone: apply migrations on an empty
   database and, separately, on the previous supported schema with synthetic data. Limits to state: the merge
   result goes stale when the target branch moves, unless branches must be up to date or a merge queue is used;
   it needs a deterministic ordering rule; it runs only if the tenant adds it. No snippet, SQL, runner or
   reusable action is included; the idea is not measured or deployed.
8. **Conflict versus legitimate merge.** Independent changes to different objects can merge legitimately. A
   schema diff is not an oracle: reviewers must know the expected semantics, and any committed snapshot needs a
   reviewed refresh procedure (a snapshot refreshed to match a failing result proves nothing).
9. **Not measured.** Explicit list: coverage of conflict classes, latency, CI cost, false-positive rate, and
   which tool each tenant uses. No savings or coverage claim.

Secondary: at most a short pointer in `docs/guides/scaffolding.md` (for example one sentence near
`## Pre-merge docker build (recommended)`) linking to the databases section, reusing the PR-only wording as
prose. No new section with a runnable workflow.

Reference alignment: the canonical research report (PR #211's `context/spikes/migration-conflicts-208.md`, or
wherever it lands if merged) is touched only to align links, not rewritten.

### Allowlist (to be confirmed before implementation)

- `docs/guides/databases.md`
- `docs/guides/scaffolding.md` (one short link or sentence, only if needed)
- The existing canonical report, links only
- `docs/public/llms-full.txt` only if it is actually tracked and regenerated by the installed procedure
  (`bun run generate:llms`); otherwise untouched.
- Not allowed: charts, tenant values, CI/workflows, scripts, and `.vitepress` config (navigation and sidebar
  included). Links use existing pages and anchors only; a new page or path, if ever truly necessary, needs
  separate owner approval and is not authorized by this proposal. The plan stays guidance-only.

## Alternatives

- **Run the PostgreSQL experiment first.** Dropped by the owner. Guidance can be written from known failure
  modes and stated honestly as unmeasured.
- **Ship a runnable CI snippet.** Dropped: no workflow, runner, SQL or action; the idea is prose only.
- **Platform-side check in `deploy-service` or `dbInitJob`.** Dropped: runs at apply time, needs per-tool
  knowledge, and is a new platform capability.
- **DevLoop implementer check.** Left as an owner decision outside this proposal (adjacent to
  mctl-agents#918).

## Platform impact

- Additive Markdown. Existing anchors in both guides are preserved. No migrations, chart, values, CI, release
  or deploy changes.
- Risks and mitigations:
  - Readers may think mctl enforces the check. Wording states it is optional, runs in the tenant's CI and
    mctl does not run it.
  - The guide could be read as measured. It lists unmeasured parameters and calls the check an idea.
  - Link or anchor breakage. Confirm default heading anchors through the existing doc build before merging;
    this proposal does not claim a link test was run.
- Verification when implemented: content and link review, and the existing docs build (`bun run build`) from
  already-installed dependencies. If the build cannot run in the environment, say so. No package install, no
  database run.
