# Tasks: issue-506-feat-usage-in-cluster-collector-moves-cl

- [ ] 1. Add the module skeleton `orchestrator/run_usage_collector.py` with a
      docstring that states the contract: pulls `model-usage-records` artifacts,
      mints no record id, adds no correlation from its own pod environment, and
      never writes to GitHub. Define the constants — `ARTIFACT_NAME =
      "model-usage-records"`, `ARTIFACT_MEMBER = "model-usage-records.json"`,
      `DEFAULT_LOOKBACK_DAYS = 3`, `DEFAULT_MAX_PAGES = 5`,
      `MAX_ARTIFACT_BYTES = 1 << 20`, `MAX_BATCH = 500`,
      `MAX_BODY_BYTES = 1 << 20` — and import `TOKEN_ENV`, `BASE_URL_ENV`,
      `DEFAULT_BASE_URL`, `INGEST_PATH`, `SCHEMA_VERSION` from
      `orchestrator.usage_ledger` rather than restating them.
      — DoD: module imports cleanly; `uv run ruff check orchestrator` and
      `uv run mypy` pass; no constant duplicated from `usage_ledger.py`.

- [ ] 2. Implement artifact discovery (depends on 1): `list_artifacts(repo,
      cutoff, max_pages)` calling `gh api
      "repos/{repo}/actions/artifacts?name=model-usage-records&per_page=100&page=N"`
      through `orchestrator.proc.run_capturing`, returning
      `(artifact_id, created_at, expired)` tuples. Skip `expired=true` and
      `created_at < cutoff` per entry — never break early on the first
      out-of-window entry, because the listing is ordered by artifact id (upload
      order), not by `created_at`. Stop after `max_pages` or a short page.
      — DoD: unit tests with a faked `gh` reader cover pagination, the page cap,
      an expired artifact, an out-of-window artifact followed by an in-window
      one, and an empty listing.

- [ ] 3. Implement the bounded, binary-safe download (depends on 1):
      `download_records(repo, artifact_id, max_bytes)` runs `gh api
      "repos/{repo}/actions/artifacts/{id}/zip"` with `stdout=` a
      `tempfile.NamedTemporaryFile` handle — not `run_capturing`, whose text
      mode would corrupt the zip bytes. Refuse a file larger than `max_bytes`
      before opening it; refuse any `zipfile.ZipInfo.file_size` above
      `max_bytes` before reading; read only the `model-usage-records.json`
      member; delete the temp file in a `finally`.
      — DoD: tests build real zips with `zipfile` and cover the happy path, an
      oversize zip, a member declaring an oversize uncompressed size, a zip with
      no `model-usage-records.json` member, and a non-zip payload — each skipped
      with a warning and never raising.

- [ ] 4. Implement record sanitising (depends on 1): `sanitise(raw) ->
      dict | None`, projecting a candidate record onto the explicit ADR-012
      field allowlist. Drop `id` and every unlisted key. Return `None` (with a
      warning) when `session_id` or `model_key` is missing/blank or when
      `schema_version` is present and not `SCHEMA_VERSION`. Preserve `agent`,
      `devloop_stage`, `target_repo`, `pr_number`, `retry_attempt` and every
      counter exactly as given — never substitute zero for an absent counter.
      Never add `argo_workflow_name`, `temporal_workflow_id`, `work_item_id` or
      `execution_id`.
      — DoD: tests assert the real artifact fixture from task 9 round-trips
      unchanged; that an injected `id`, `calculated_cost` and an unknown
      `review_text` key are all dropped; that a record with
      `schema_version: 2`, a blank `session_id` or a missing `model_key` is
      dropped; and that a record with no `cache_read_tokens` key stays without
      one.

- [ ] 5. Implement delivery (depends on 1, 4): `deliver(records, *, token,
      base_url, post=…)` chunking at `MAX_BATCH` records and `MAX_BODY_BYTES`
      of serialised body, POSTing `{"records": [...]}` with the
      `Authorization: Bearer` header via `httpx`, refusing any non-`https`
      `base_url` with one warning, and returning accepted/deduped/undelivered
      counts read from the response's `accepted_count` and `deduped_count`. A
      failed chunk is logged and counted, never raised; remaining chunks still
      go. Do not reuse `UsageRecorder._deliver` — its sticky may-have-landed
      return exists for the delta baseline this caller does not have.
      — DoD: tests with an injected `post` cover chunking at the record cap,
      chunking at the byte cap, a non-https base URL sending nothing, a 400 on
      one chunk not stopping the next, and accepted/deduped counts being
      surfaced in the return value.

- [ ] 6. Implement the sweep and CLI (depends on 2, 3, 4, 5): `collect(...) ->
      CollectResult` over `mctlhq/<svc>` for `svc in config.settings.SERVICES`,
      and `main()` with `argparse` flags `--repo` (repeatable override),
      `--lookback-days` (default 3), `--max-pages`, `--max-artifact-bytes`,
      `--dry-run`. Per-repository and per-artifact failures are logged with the
      repository and artifact id, counted, and skipped. Print one summary line:
      repositories swept, artifacts found, artifacts read, artifacts skipped,
      records posted, records deduped, failures. Exit non-zero only when `gh`
      cannot authenticate at all; exit zero for per-item failures and for an
      absent `MCTL_USAGE_WRITER_TOKEN` (one warning, nothing posted).
      `--dry-run` requires no writer token.
      — DoD: `python -m orchestrator.run_usage_collector --help` works;
      `--dry-run` against a faked `gh` reader posts nothing and prints the
      counts; a repository whose listing raises does not abort the sweep; a
      broken-auth `gh` failure exits non-zero.

- [ ] 7. Call `orchestrator.github_token.refresh_github_token()` before each
      `gh` invocation (depends on 6), matching the other runners, so a
      long backfill outliving the installation token's TTL keeps working.
      — DoD: a test asserts the refresh helper is called before a `gh`
      invocation; the sweep still works when `GITHUB_TOKEN_FILE` is unset.

- [ ] 8. Write `docs/operations/usage-collector.md` (depends on 6) — the owner
      steps this change does not perform: (a) the `ClusterWorkflowTemplate`
      `mctl-agents-usage-collector` manifest for
      `platform-gitops/argo-workflows/cluster-templates/`, modelled on
      `cwft-mctl-agents-reconcile.yaml`, running
      `python -m orchestrator.run_usage_collector`, with `GITHUB_TOKEN` from
      `mctl-agents-secrets/github-token` and `MCTL_USAGE_WRITER_TOKEN` from
      `mctl-agents-secrets/usage-writer-token` (`optional: true`), an
      `emptyDir` workdir, no gitops clone and no `mctl-gitops-main-writes`
      mutex; (b) the `CronWorkflow` wrapper modelled on
      `cronworkflow-mctl-agents-incidents.yaml` with `schedules: ["21 * * * *"]`,
      `timezone: UTC`, `concurrencyPolicy: Forbid` and `suspend: true` on first
      apply, plus why `:21` avoids the `:00/:03/:07/:09/:11/:15` family; (c) the
      one-shot `--lookback-days 90` backfill after un-suspending; (d) the
      per-repository `uses:` SHA bump in each caller's
      `.github/workflows/claude-review.yml` — as of 2026-09-26 every caller
      except `mctlhq/.github` pins a revision that predates the usage capture,
      so the collector is expected to find artifacts only there until then;
      (e) the optional narrowed rotation target
      (`permissions: {actions: read, metadata: read}`) in
      `cwft-rotate-github-token.yaml`.
      — DoD: the manifests are complete enough to apply verbatim; the doc states
      explicitly that no manifest in this change is applied and that the
      collector is expected to report zero artifacts for most repositories today.

- [ ] 9. Add the real-artifact fixture (depends on 3) —
      `tests/fixtures/model-usage-records.json`, the verbatim body of
      `mctlhq/.github` artifact 10894371011 (run 36206815658, PR 139): two
      records, one Haiku and one Opus, same `session_id`
      `bcdd4386-40ae-471d-b8d1-9e2bb8757c81` and `result_uuid`
      `9d93d631-a52c-41be-833a-aa6515d87aba`, `agent: claude-review`,
      `devloop_stage: reviewer`, `target_repo: mctlhq/.github`, `pr_number: 139`.
      — DoD: the fixture is byte-faithful to the real artifact; the tests in
      tasks 4 and T2/T3 read it rather than hand-rolling a record.

- [ ] 10. Update the ADR and README (depends on 6, 8): add an amendment section
      to `docs/adr/012-model-usage-cost-attribution-contract.md` recording that
      the reviewer stage reaches the ledger through an in-cluster puller, that
      the collector mints no id because mctl-api derives it, and that
      `(session_id, result_uuid, model_key)` — not `(run, attempt, model)` — is
      the reviewer's dedupe key; add the collector to the runner list in
      `README.md` / `LLMS.md`.
      — DoD: the ADR amendment names the artifact, the credential, the owner
      steps and the statelessness decision; no existing ADR section is
      rewritten.

## Tests

- [ ] T1. `tests/test_usage_collector_discovery.py` — pagination, `--max-pages`
      cap, expired artifacts skipped, the lookback cutoff applied per entry
      (including an out-of-window artifact listed *before* an in-window one, the
      real ordering observed on the API), an empty listing, and a listing whose
      JSON is malformed — all handled without raising.
- [ ] T2. `tests/test_usage_collector_records.py` — the task 9 fixture survives
      `sanitise` field-for-field; an injected `id`, `calculated_cost`,
      `pricing_version` and a prose-shaped unknown key are dropped; a
      `schema_version: 2` / blank `session_id` / missing `model_key` record is
      dropped with a warning; an absent counter stays absent rather than
      becoming 0; no `argo_workflow_name`/`temporal_workflow_id`/`work_item_id`
      appears even when those env vars are set in the test environment.
- [ ] T3. `tests/test_usage_collector_idempotency.py` — **the acceptance test.**
      Run the collector twice over the same faked artifact with a fake ingest
      endpoint that implements mctl-api's rule: derive
      `sha256` over length-prefixed `(session_id, result_uuid, model_key)` (and
      the `(session_id, model_key, num_turns)` fallback when `result_uuid` is
      absent), insert-or-ignore, and answer `accepted_count`/`deduped_count`.
      Assert the second run posts a byte-identical body, adds no row, reports
      every record deduped, and that the store holds exactly two rows (one per
      model) — the Haiku and Opus records of one review, not one merged row.
      Also assert a third run with `--lookback-days 90` adds no row either.
- [ ] T4. `tests/test_usage_collector_zip.py` — oversize zip refused before
      read; a member declaring an oversize uncompressed size refused; a zip with
      no `model-usage-records.json` member skipped; a non-zip payload skipped;
      the temp file removed in every one of those paths.
- [ ] T5. `tests/test_usage_collector_delivery.py` — chunking at 500 records and
      at the 1 MiB body cap; a non-https `MCTL_API_BASE_URL` sends nothing and
      warns once; an absent `MCTL_USAGE_WRITER_TOKEN` warns once, posts nothing
      and exits zero; a 400 on one chunk is logged and counted while later
      chunks still go; the `Authorization` header carries the writer token and
      never `MCTL_TOKEN`.
- [ ] T6. `tests/test_usage_collector_resilience.py` — one repository's listing
      failing does not abort the sweep and the summary counts it as a failure;
      a `gh` authentication failure exits non-zero; `--dry-run` posts nothing
      with no writer token present; the summary line names every counter.
- [ ] T7. Read-only guarantee — assert the collector's source issues no
      mutating GitHub call: every `gh` invocation it builds is `gh api` with a
      path and no `--method`/`-X`/`-f`/`-F`, and the module contains no
      `gh issue`, `gh pr`, `gh run` or `git push` call. A source-level assertion
      in the spirit of the existing `ast`-based checks in
      `tests/test_usage_ledger.py`.

## Rollback

The collector is additive, stateless and write-only against one confined
endpoint, so rollback is cheap and has three independent levels.

1. **Stop collecting, keep the code.** Set `suspend: true` on the
   `mctl-agents-usage-collector` CronWorkflow in mctl-gitops (a one-line gitops
   commit; ArgoCD syncs it). Nothing else in the platform calls
   `run_usage_collector`, so this halts it completely. Because it is suspended
   rather than deleted, re-enabling it later needs no re-derivation of state —
   the next tick simply re-reads its lookback window.
2. **Stop writing, keep collecting.** Remove the `MCTL_USAGE_WRITER_TOKEN` env
   entry from the CWFT (it is already `optional: true`). The collector then logs
   one warning, posts nothing and exits zero — useful for isolating whether a
   problem is in discovery or in ingest.
3. **Revert the code.** Revert the mctl-agents PR. It adds one module, one doc,
   one fixture and its tests, and touches `orchestrator/usage_ledger.py` only as
   an importer of existing constants, so the revert cannot affect the
   investigator/implementer/shepherd producer.

**Rows already ingested need no cleanup and should not be deleted.** They are
correct ADR-012 records of real reviewer spend, they carry
`agent=claude-review` so they are trivially identifiable, and the read side can
exclude them with the existing `agent` filter if an operator wants a
pre-collector view. Deleting them would discard the only copy of that spend once
the 90-day artifact retention passes.

**If a double count is ever suspected**, the diagnosis is a query, not a
rollback: group the ledger by `(session_id, result_uuid, model_key)` and assert
one row per group. More than one row for a group would mean mctl-api's
`EnsureID`/insert-or-ignore path changed, not that the collector ran twice —
running twice is exactly what T3 proves is free.
