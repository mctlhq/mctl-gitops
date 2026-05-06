# Tasks: wrangler-interactive-prompt-ci-guard

- [ ] 1. Audit `cloudflare-worker/wrangler.toml` for required fields — DoD:
  confirm `name` and `compatibility_date` are present as top-level keys;
  if either is missing, add it with the correct value (`name` = the canonical
  Worker name, `compatibility_date` = today's ISO-8601 date); the file must
  parse without errors under `wrangler deploy --dry-run`.

- [ ] 2. Add `CI=true` to the wrangler deploy step in `deploy.yml` (depends on 1)
  — DoD: the deploy step in `deploy.yml` has `env: CI: "true"` (or equivalent
  `--no-interactive` flag) explicitly set; the workflow YAML is valid and passes
  `actionlint` or equivalent syntax check; a local dry-run with
  `CI=true npx wrangler deploy --dry-run` exits 0.

- [ ] 3. Add a `wrangler.toml` validation step to the CI workflow (depends on 1)
  — DoD: a step in `deploy.yml` (or a dedicated `ci.yml` triggered on PRs)
  runs before the deploy step and greps for `^name\s*=` and
  `^compatibility_date\s*=` in `cloudflare-worker/wrangler.toml`; the step
  exits 1 with a clear error message if either key is absent; the step exits 0
  on the current file.

- [ ] 4. Verify end-to-end in a dry-run PR (depends on 2, 3) — DoD: open a draft
  PR that includes all changes; confirm the validation step passes; confirm the
  deploy step (dry-run or skipped on non-main branch) does not hang; no job
  timeout is observed within 5 minutes of the workflow start.

## Tests

- [ ] T1. Positive path — with `name` and `compatibility_date` present in
  `wrangler.toml` and `CI=true` set, `wrangler deploy --dry-run` exits 0 and
  produces no interactive prompt output.

- [ ] T2. Negative path (missing `name`) — temporarily remove `name` from
  `wrangler.toml` in a local test; confirm that `CI=true npx wrangler deploy`
  exits non-zero within 10 seconds with a message referencing the missing field,
  rather than blocking.

- [ ] T3. Negative path (missing `compatibility_date`) — same as T2 but for
  `compatibility_date`; confirm fast non-zero exit.

- [ ] T4. Lint step regression — manually remove `compatibility_date` from
  `wrangler.toml` in a branch; confirm the validation step in CI fails and
  prints the expected error string before the deploy step is reached.

- [ ] T5. Lint step false-positive check — confirm the grep pattern does not
  match a key inside an `[env.staging]` section when the top-level key is absent
  (i.e., the grep is anchored correctly to top-level declarations).

## Rollback
All changes are configuration-only (two text files). To roll back:

1. Revert the `deploy.yml` commit — removes the `CI=true` env var and the
   validation step. The deploy pipeline returns to its previous state.
2. Revert the `wrangler.toml` commit — removes any added fields. Note: if
   `name` or `compatibility_date` were genuinely missing before this proposal,
   reverting them re-introduces the hang risk with wrangler 4.88.0+.

No infrastructure changes, no secrets, no migrations, and no Kubernetes
resources are involved, so the rollback blast radius is limited to the
GitHub Actions workflow behaviour.
