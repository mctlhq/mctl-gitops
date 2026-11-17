# Design: issue-208-spike-should-mctl-docs-or-the-devloop-im

## Current state

mctl-docs is a VitePress 1.6 site (`package.json`: `vitepress ^1.6.0`). Pages live
under `docs/` and the sidebar is in `docs/.vitepress/config.ts`. `bun run build`
runs the tests, then `scripts/generate-llms-full.ts` (which regenerates
`docs/public/llms-full.txt`), then `vitepress build docs`.

Relevant pages:

- `docs/guides/databases.md` ("Database Provisioning") documents
  `mctl_provision_database`, the injected `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`
  variables, and that `DATABASE_URL` is not guaranteed. It does not mention schema
  migrations, their ordering, or concurrency.
- `docs/guides/scaffolding.md` has a "Pre-merge docker build (recommended)" section
  (an opt-in PR-only CI job with a warning about `needs:`) and the "CI auto-deploy
  job". This is the natural home and style template for an opt-in pre-merge
  migration check.
- A grep for "migrat" across `docs/` finds only unrelated hits (image migration in
  `scaffolding.md`, the `MCTL_GITHUB_TOKEN` migration note, and the VitePress
  upgrade FAQ entry in `docs/reference/faq.md`). No docs page covers this topic,
  so there is no existing docs owner to reuse.
- `context/decisions/README.md` says ADRs are for the docs site itself.
  `context/plans/` holds internal working plans (`site-docs-alignment.md`). A spike
  report about tenant guidance belongs in `context/plans/`, not in `decisions/`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml`: image tag `0.1.68`,
  which matches `package.json` version `0.1.68`. The docs site itself has no
  database.
- `$MCTL_GITOPS_ROOT/helm-charts/base-service/templates/job-db-init.yaml`: an
  optional `dbInitJob` that runs as an Argo CD `PostSync` hook on
  `postgres:17-alpine`. It polls for a `waitTable` ("Wait for migrations to
  finish") for up to 30 x 10 s, then runs `dbInitJob.sql`. It is disabled by
  default (`helm-charts/base-service/values.yaml`: `dbInitJob.enabled: false`).
  It assumes migrations are run by the app, not by the platform.
- `grep dbInitJob services/*/*/values.yaml`: enabled for `labs/mctl-academy`,
  `labs/mctl-telegram`, and `labs/mctl-telegram-preview`.
- `services/admins/mctl-support/values.yaml`: "The service migrates its own
  schema on start (advisory-locked, so two replicas starting together are safe);
  no db-init job." An advisory lock serializes concurrent runs but does not
  detect logically conflicting migrations.
- `services/labs/pfeifenpatenschaft-backend/values.yaml`: "migrations go to
  Postgres".
- `vaultPath: teams/<tenant>/<svc>/database` appears in about 12 service values
  files (admins/mctl-support, admins/umami, karabu/draw-with-friends,
  labs/kuptsi-app, labs/mctl-academy, labs/mctl-alice, labs/mctl-loyalty,
  labs/mctl-pairdesk, labs/mctl-rules, labs/mctl-telegram(-preview), and others),
  so DB-backed tenant services exist. Which migration tool each uses is not
  visible in gitops: could not observe, recorded under Open questions.
- `gh issue view` on the Related issues: mctl-gitops#1044 "spike(gitops): evaluate
  KYAML canonicalization for machine-generated manifests" (OPEN), mctl-agents#918
  "spike: Which DevLoop finding classes should be promoted only after
  deterministic validation..." (OPEN), mctl-gitops#2506 "spike(temporal): evaluate
  ZITADEL vs Vault as Temporal workload JWT issuer" (OPEN). None of them
  duplicates this question. #918 is adjacent: a deterministic migration-apply
  check would be one candidate "deterministic validation" class.
- The mctl MCP tools were not called for live status. The gitops checkout was
  enough for this read, and nothing here asserts runtime behaviour.
- The issue's Source URL (postgr.es/p/9Bm) was not fetched: could not observe.

## Proposed solution

This is a spike with a gated docs change. There are three parts, in order.

1. **Duplicate map** (in `context/plans/migration-conflict-spike.md`). Classify
   the three Related issues, the docs pages above, the chart's `dbInitJob`, and
   the per-service migration patterns observed in gitops. Recorded result:
   no existing owner covers "Git-clean but apply-time-conflicting migrations".
   mctl-agents#918 is the closest adjacent owner for any agent-side check.

2. **Bounded falsifying experiment** (outside the clone, in a throwaway public or
   personal scratch repo with GitHub Actions, never on the shared CNPG cluster).
   - Base: one table plus migration `0001`. Use a plain-SQL runner (numbered
     `.sql` files applied in lexical order and recorded in a
     `schema_migrations` table) so that tool behaviour does not confound the
     result. Optionally repeat with one common tool, golang-migrate, as a second
     data point.
   - Scenarios, each as two branches that `git merge` cleanly:
     (a) both add `0002_*.sql` with different names (duplicate version);
     (b) A adds a `NOT NULL` column without a default and B inserts rows assuming
         the old shape, or A renames a column that B indexes, so the result
         depends on order;
     (c) both apply without error but the merged schema differs from each
         branch's tested schema (for example both `ALTER ... SET DEFAULT` on the
         same column, so the last one wins).
   - Baseline: per-branch CI that applies migrations to an empty `postgres:17`
     service container. This is what a tenant gets today if they test at all.
   - Candidate: a PR-only job that checks out the merge ref
     (`refs/pull/N/merge`, which GitHub Actions does by default), applies all
     migrations to an empty `postgres:17`, dumps the schema with
     `pg_dump --schema-only`, and fails on (i) apply error, (ii) a duplicate
     version prefix, or (iii) a schema dump diff against a committed
     `schema.sql` snapshot. The snapshot check is what catches scenario (c).
   - Measurements per scenario, 5 runs each: detected yes/no (success), job
     wall-clock (latency), Actions minutes (cost), false positives and
     negatives (reliability). Anything not measured is written as `unknown`.
   - Known limit to record: the merge ref is computed against the base at PR
     time. If B merges after A without a re-run, the check is stale unless the
     repo requires branches to be up to date or uses a merge queue. Record this
     as a finding, not a fix.

3. **Gated docs change** (only if at least one scenario escapes the baseline and
   is caught by the candidate):
   - `docs/guides/databases.md`: new `## Schema migrations and parallel PRs`
     section. It explains the three failure shapes and states plainly that the
     platform does not run or order tenant migrations (the app does, on start or
     via its own job, and `dbInitJob` only waits for a table). It recommends
     (1) timestamp or unique version names, (2) running migrations from one
     place under an advisory lock, (3) a committed schema snapshot, and
     (4) "require branches to be up to date" or a merge queue. It links to the
     scaffolding snippet.
   - `docs/guides/scaffolding.md`: new `## Pre-merge migration check (optional)`
     section right after "Pre-merge docker build (recommended)". It holds a
     PR-only job with a `postgres:17` service container and the same `needs:`
     caveat. The tool-specific apply command is a placeholder, since mctl does
     not mandate a tool.
   - No sidebar change: both pages are already in `docs/.vitepress/config.ts`.
   - Regenerate `docs/public/llms-full.txt` via `bun run generate:llms`.

4. **Recommendation and follow-ups.** Record exactly one recommendation, either
   "Migration-conflict guidance and check idea (docs, opt-in tenant CI)" or
   "no change". If evidence supports an agent-side check, draft one follow-up
   issue for mctl-agents (linked to #918) that proposes the implementer run the
   tenant's own migration check when it is present. It must not add authority.

Why this shape: the docs repo can only publish guidance, the platform does not own
tenant migrations (per the chart and service values), and the issue forbids
implementation before the decision. Opt-in tenant CI keeps authority where it is.

## Alternatives

- **Build a DevLoop implementer check now.** Dropped. It is out of scope for
  mctl-docs, the issue forbids implementation before the decision, and it would
  expand agent behaviour without evidence. It is kept as a follow-up draft.
- **Platform-side check in `deploy-service` or the `dbInitJob` hook.** Dropped. It
  runs after merge, at apply time, which is exactly when the failure already
  happens. It would also need the platform to understand each tenant's migration
  tool, which is a new capability for parity.
- **Docs-only guidance with no experiment.** Dropped. The issue requires evidence
  on current workload rather than vendor claims, and the snapshot-diff part of
  the check is only worth recommending if it actually catches scenario (c).

## Platform impact

- Migrations: none. No schema, chart, or values change.
- Backward compatibility: purely additive Markdown sections. Existing anchors in
  `databases.md` and `scaffolding.md` are unchanged.
- Resources: the experiment uses GitHub Actions minutes in a scratch repo only.
  The docs build cost is unchanged.
- Risks and mitigations:
  - Readers may believe mctl enforces the check. Mitigation: explicit
    "opt-in, runs in your CI, mctl does not run it" wording, which is an
    acceptance criterion.
  - Stale merge-ref false negatives. Mitigation: document the
    up-to-date-branch or merge-queue requirement next to the snippet.
  - Snapshot-diff false positives from `pg_dump` formatting differences across
    versions. Mitigation: pin `postgres:17` for both the dump and the snapshot,
    and measure the false-positive rate in the experiment.
