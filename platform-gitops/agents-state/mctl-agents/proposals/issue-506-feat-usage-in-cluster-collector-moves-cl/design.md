# Design: issue-506-feat-usage-in-cluster-collector-moves-cl

## Current state

**mctl-agents produces its own usage records, in-process.**
`orchestrator/usage_ledger.py` holds `UsageRecorder`, fed from
`tracing.agent_run`'s observer. It posts to
`{MCTL_API_BASE_URL}/api/v1/usage/records` with `MCTL_USAGE_WRITER_TOKEN`
(`usage_ledger.TOKEN_ENV`, `BASE_URL_ENV`, `INGEST_PATH`, `SCHEMA_VERSION` at
`orchestrator/usage_ledger.py:97-101`). Three of its properties matter here:

- It sends **deltas**, not totals, because `ResultMessage.model_usage` is
  cumulative per SDK session (module docstring, and ADR-012's 2026-09-24
  amendment at `docs/adr/012-model-usage-cost-attribution-contract.md:336`).
  The delta baseline in `UsageRecorder._baseline` and the sticky
  "may-have-landed" logic in `UsageRecorder._deliver`
  (`orchestrator/usage_ledger.py:499`) exist entirely to serve that baseline.
- It refuses to send the bearer over a non-https `MCTL_API_BASE_URL`
  (`usage_ledger.py:348-354`), and it never falls back to the admin
  `MCTL_TOKEN`.
- It records **no** `devloop_stage` today. ADR-012 lists the field
  (`012-…md:147`); populating it on the producer is mctlhq/mctl-agents#504, a
  sibling proposal in `proposals/issue-504-feat-usage-populate-devloop-stage-with-t/`
  currently `status: proposed`.

**The reviewer produces its records in GitHub Actions, and publishes them as an
artifact.** `.github/workflows/claude-review.yml` in this repo is only a caller;
the logic lives in `mctlhq/.github/.github/workflows/claude-review.yml`
(mctlhq/.github#126). Read on 2026-09-26 at `main`, it:

- builds ADR-012 records with `USAGE_RECORDS_JQ` (line ~408), one per
  `(run, model)`, setting `agent: "claude-review"`,
  `devloop_stage: "reviewer"`, `target_repo`, `pr_number`, the five token
  counters, `outcome`, `stop_reason`, `terminal_reason`, `num_turns`,
  `duration_api_ms`, `retry_attempt`, `recorded_at`, `session_id`,
  `result_uuid`, `model_key`, `canonical_model`, `provider` — and deliberately
  no `id`, no cost, and no field that could hold prose;
- merges the per-attempt files with `USAGE_MERGE_JQ` on the ledger's own dedupe
  key, keeping the first occurrence;
- writes `{"records": [...]}` — **byte-identical to the POST body** — to
  `$RUNNER_TEMP/model-usage/model-usage-records.json`;
- uploads it as artifact `model-usage-records` with `retention-days: 90`;
- states in a comment why it does not post: "that endpoint is admin-only and an
  admin credential does not belong in every caller repository."

**mctl-api derives the row id itself and refuses a supplied one.** Read from
`mctlhq/mctl-api` `internal/usage/types.go`: `DeterministicID` hashes
length-prefixed `(session_id, result_uuid, model_key)`, or
`(session_id, model_key, num_turns)` when `result_uuid` is absent.
`Record.EnsureID` recomputes it unconditionally and returns
`ErrInvalidRecord` when a supplied `id` disagrees — "a producer that sends its
own id would otherwise opt out of the entire idempotency guarantee."
`internal/api/handlers_usage.go` bounds a request to `maxIngestBatch = 500`
records and `usageMaxBodyBytes = 1 MiB`, confines the usage-writer principal to
`POST /api/v1/usage/records` (`usageWriterGate`), and answers with
`accepted_count` and `deduped_count`.

**Both credentials are already in-cluster.** The implement CWFT in mctl-gitops
(`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml:649`)
wires `MCTL_USAGE_WRITER_TOKEN` from `mctl-agents-secrets/usage-writer-token`
(`optional: true`), and every runner CWFT wires `GITHUB_TOKEN` from
`mctl-agents-secrets/github-token`. That secret is fed from Vault
`platform/mctl-agents` by `cwft-rotate-github-token.yaml`, whose `mctl-agents`
target is minted **unscoped** from the `mctl-agents` App installation, which
carries `actions: write` (hence read) across every repository it covers.

**There is an established shape for a model-free periodic sweep.**
`orchestrator/run_issue_poller.py` is the closest precedent: `gh`-based
discovery, `argparse` with `--dry-run`, per-item failures logged and counted
while the process exits non-zero only on a global failure (module docstring
lines 31-37), a `--max-issues` cap so one bad tick cannot fan out.
`orchestrator/proc.py::run_capturing` is the subprocess helper (it surfaces
captured stderr in the raised `CommandFailed`, and can bound how much output it
reads). `orchestrator/github_token.py::refresh_github_token` re-reads a rotated
token mid-process, and is a no-op for short crons.

**Measured reality of the artifacts (2026-09-26, with the real credential):**

- `GET /repos/mctlhq/.github/actions/artifacts?name=model-usage-records` →
  `total_count: 21`, each entry carrying `id`, `created_at`, `expired`,
  `expires_at` and `workflow_run.{id, repository_id, head_sha, head_branch}`.
  `size_bytes` came back **null**, so it cannot be used as a size guard.
- `GET /repos/mctlhq/.github/actions/artifacts/10894371011/zip` → a 623-byte
  zip with one member, `model-usage-records.json`, containing 2 records for
  `mctlhq/.github#139`: Haiku and Opus, same `session_id` and `result_uuid`,
  `devloop_stage: "reviewer"`, `retry_attempt: 0`, 3,123,860 cache-read tokens
  on Opus.
- Every caller repository **except `mctlhq/.github` itself** pins the reusable
  workflow at `b0fc8003…` (or `f25ff6a4…` for mctl-telegram), both of which
  predate the usage capture. `mctlhq/.github` calls it locally
  (`uses: ./.github/workflows/claude-review.yml` from `pr-review.yml`), which
  is why only that repository has artifacts today. The collector is therefore
  correct-but-quiet for the other repositories until their pin is bumped.

## Proposed solution

One new module, `orchestrator/run_usage_collector.py`, runnable as
`python -m orchestrator.run_usage_collector` on the existing image. No model,
no SDK session, no gitops write, no GitHub write. One tick is:

```
for repo in repos:                       # mctlhq/<svc> for svc in SERVICES
    for artifact in list_artifacts(repo):    # name=model-usage-records, paged
        if artifact.expired or artifact.created_at < cutoff: continue
        records = read_zip(download(artifact))    # bounded, allowlisted
        buffer.extend(records)
deliver(buffer)                          # chunked POST, https + writer token
print(summary)
```

**Discovery by artifact name, not by workflow file.** The collector calls
`GET /repos/{repo}/actions/artifacts?name=model-usage-records&per_page=100`
rather than enumerating `claude-review.yml` runs. Verified above, and it is the
robust choice: the caller workflow's *file name* is not stable across the org —
`mctlhq/.github` calls the reusable workflow from `pr-review.yml`, everyone else
from `claude-review.yml` — whereas the artifact name is fixed by the reusable
workflow itself. It is also one request per repository instead of one per run.
Paging is bounded by `--max-pages` (default 5, i.e. up to 500 artifacts per
repository per tick) and the window filter is applied per entry rather than as
an early break, because the listing is ordered by artifact id, which is upload
order and not exactly `created_at` order (observed: 23:43 listed before 23:51).

**Download is binary-safe and bounded.** `gh api …/zip` follows the 302 and
writes the zip to stdout, so the collector runs it with
`subprocess.run(..., stdout=<file handle>)` into a `tempfile` rather than
through `run_capturing`, whose text mode would corrupt the bytes with
`errors="replace"`. Before reading, it refuses a file over
`--max-artifact-bytes` (default 1 MiB, the server's own body cap) and refuses a
`zipfile.ZipInfo.file_size` over the same bound, so neither a large artifact nor
a zip bomb is ever expanded into memory. It reads exactly the
`model-usage-records.json` member and ignores any other member. An artifact is
influenced by whatever ran the reviewer workflow, so it is treated as untrusted
input even though it is our own workflow that writes it.

**Record sanitising is an allowlist, and it never mints an id.** A candidate
record is projected onto the ADR-012 field names the ledger accepts
(`schema_version`, `session_id`, `result_uuid`, `model_key`, `canonical_model`,
`provider`, `agent`, `devloop_stage`, `target_repo`, `issue_number`,
`pr_number`, `work_item_id`, `trace_id`, `span_id`, the six usage counters,
`outcome`, `api_error_status`, `stop_reason`, `terminal_reason`, `num_turns`,
`duration_api_ms`, `retry_attempt`, `recorded_at`). Everything else — including
an `id`, a cost field, or any future key — is dropped. Dropping `id` is not
defensive style, it is required: `EnsureID` errors on a supplied id that
disagrees with the derived one, and one such record fails the whole
single-transaction batch.

This is also where the issue's phrasing is deliberately reinterpreted. The
issue asks for "a stable record id per (run id, run attempt, model)". That is
not implementable and not needed: mctl-api owns the id and derives it from
`(session_id, result_uuid, model_key)`, which the artifact already carries.
That key is strictly *better* than `(run id, run attempt, model)` — it also
collapses the primary/fallback reviewer attempts that re-record one result,
while keeping a fallback that genuinely re-ran the model (new `session_id`) as
the second real charge it is. So idempotency is achieved by the collector
forwarding the artifact's identity unchanged and minting nothing, and a
collector-side `(run, attempt, model)` id would in fact *break* it.

**Statelessness is the idempotency design.** The collector keeps no cursor, no
seen-set and no durable state. Re-collection is a no-op because the server
dedupes, which makes "re-read the same artifact" and "re-run the whole sweep"
the same operation, and makes a widened `--lookback-days` a safe backfill
rather than a double count. `accepted_count`/`deduped_count` from each response
is logged, so an operator can see a re-collection cost nothing.

**Delivery reuses the ledger's constants but not its `_deliver`.** The
collector imports `TOKEN_ENV`, `BASE_URL_ENV`, `DEFAULT_BASE_URL`,
`INGEST_PATH` and `SCHEMA_VERSION` from `orchestrator.usage_ledger` so the two
producers cannot drift on the endpoint, the env var names or the https rule. It
does **not** reuse `UsageRecorder._deliver`: that method's sticky
"may-have-landed" return value exists only to decide whether to advance the
delta baseline, and the collector has no baseline — its records are absolute
totals read from a file, so a lost answer simply means "re-collect next tick".
Folding the collector into `_deliver` would drag baseline semantics into a
caller that has none. Chunking is at 500 records and ~1 MiB of serialised body,
matching `maxIngestBatch` and `usageMaxBodyBytes`.

**It refuses to attribute reviewer spend to itself.** `WORKFLOW_NAME`,
`WORKFLOW_TEMPORAL_WORKFLOW_ID` and `WORKFLOW_WORK_ITEM_ID` in the collector's
pod describe the *collector's* Argo run, not the review. `UsageRecorder`
reads them via `_CORRELATION_ENV` because there they are correct; the collector
must not, or every reviewer row would join to the collector's execution instead
of the reviewer's PR. This is called out explicitly because it is the easy
mistake to make while reusing the module.

**Exit code follows the poller.** Per-repository and per-artifact failures are
logged with the repository and artifact id, counted, and skipped. A failed
delivery chunk is logged and counted; the next tick re-collects it. The process
exits non-zero only when `gh` cannot authenticate at all, so a real credential
outage goes red while one bad repository does not. An absent
`MCTL_USAGE_WRITER_TOKEN` logs one warning and exits zero, matching
`UsageRecorder`'s "no token, no records, one warning" and the `optional: true`
secret reference that is already in the CWFTs.

**The scheduling half is an owner step, written down and not performed.** The
implementer works in mctl-agents and cannot commit to mctl-gitops, and the
issue's third acceptance criterion asks for exactly this. The proposal ships
`docs/operations/usage-collector.md` containing: the
`ClusterWorkflowTemplate` + `CronWorkflow` manifests to apply in
`platform-gitops/argo-workflows/cluster-templates/` (modelled on
`cwft-mctl-agents-reconcile.yaml` for the container/env shape and
`cronworkflow-mctl-agents-incidents.yaml` for the wrapper, with
`suspend: true` on first apply, `concurrencyPolicy: Forbid`, an `emptyDir`
workdir and no gitops clone or mutex — it writes nothing to git); the
`:21` hourly offset and why; the one-shot `--lookback-days 90` backfill; the
per-repository `uses:` SHA bump that makes the other repositories produce
artifacts at all; and the optional narrowed rotation target
(`permissions: {actions: read, metadata: read}`) for a dedicated
`usage-collector-github-token`.

## Alternatives

**Push from the reviewer workflow.** The reusable workflow already holds the
records; a `curl` at the end of the job would be three lines. Dropped by the
standing 2026-09-24 constraint and by owner decision 1 on mctlhq/.github#50: it
needs the usage-writer bearer as a secret in every caller repository — a new
long-lived GitHub secret, in the widest possible place, for a credential whose
whole point is confinement. GitHub OIDC (`id-token: write` is already granted)
would avoid the static secret, but requires an OIDC trust path and token
exchange in mctl-api that does not exist; that is a much larger change than a
puller, and the puller does not block it later.

**A Temporal schedule and activity instead of an Argo CronWorkflow.** The
family's other read-mostly reconcilers (reconcile, issue-poll) moved to Temporal
schedules, so this would be the more modern shape. Dropped for this slice: it
adds the collector to the worker's deployment surface and its queue capacity
(ADR-008) for a job that is a bounded HTTP sweep with no durable state, no
signals and no long-running steps — Temporal's durability buys nothing here,
because the ledger's dedupe already makes a lost tick free. The issue also names
a CronWorkflow explicitly. `run_usage_collector.py` is a plain `main()`, so
wrapping it in an activity later is a small change if the schedule surface is
consolidated.

**Parse the job summary instead of the artifact.** The summary table is also
published and is fetchable via the jobs API. Dropped: it is a lossy rendering
built for humans — it prints absent counters as `—`, drops `session_id`,
`result_uuid` and `provider` entirely, and would therefore make the ledger's
dedupe key unreconstructible. The artifact is the POST body verbatim.

**Persist a per-repository high-water mark so each tick reads only new
artifacts.** Fewer downloads. Dropped: it re-introduces durable state whose
loss or corruption silently skips records, in exchange for bandwidth measured
in hundreds of bytes per artifact, and it would make a backfill a state-editing
operation instead of a flag. Statelessness plus server-side dedupe is the whole
reason this is safe to run at any cadence.

## Platform impact

**Migrations.** None. No schema change in mctl-api (`devloop_stage`,
`retry_attempt` and every field the artifact sends already exist in
`internal/usage/types.go`), no new table, no new endpoint, no new principal,
no new secret anywhere. mctl-agents gains one module, one doc and its tests.

**Backward compatibility.** Additive. `orchestrator/usage_ledger.py` is only
imported for constants; `UsageRecorder` behaviour is unchanged, so
mctlhq/mctl-agents#504 (which edits `UsageRecorder` to add `devloop_stage`) and
this proposal do not conflict — the collector must keep forwarding the
artifact's own `devloop_stage=reviewer` either way. Records arriving from the
collector are indistinguishable in shape from any other ADR-012 record except
for `agent=claude-review`, and `ingested_by`/`ingested_by_principal_id` are
stamped server-side by the same usage-writer principal.

**Resource impact.** One short-lived pod per tick, no PVC (`emptyDir`), no
gitops clone and no `mctl-gitops-main-writes` mutex, so it does not join the
contention the shepherd CronWorkflow's comments describe. GitHub API cost per
tick is roughly one list call per repository plus one download per in-window
artifact: with `SERVICES` at 15 repositories and `--max-pages 5`, the floor is
15 requests and the realistic ceiling a few dozen, against a 5,400/hour budget
shared with the rest of the platform (measured `rate.limit: 5400`). mctl-api
sees a handful of small POSTs per tick.

**Risks and mitigations.**

- *Double-counting reviewer spend.* The failure this whole design is shaped
  against. Mitigated structurally: the collector mints no id, forwards the
  artifact's `(session_id, result_uuid, model_key)` unchanged, and
  `Record.EnsureID` recomputes the key server-side with
  insert-or-ignore. Tested by collecting the same fixture twice and asserting
  the second delivery reports every record deduped and adds no row.
- *One malformed record failing a whole batch.* The ingest is one transaction.
  Mitigated by dropping records without `session_id`/`model_key` or with an
  unsupported `schema_version` before the POST, and by the field allowlist.
- *Silent zero.* A collector that finds nothing looks identical to one that is
  broken — and today it genuinely finds nothing outside `mctlhq/.github`,
  because of the pinned SHAs. Mitigated by the summary line always naming
  repositories swept and artifacts found per repository, and by the doc stating
  the expected state ("only `mctlhq/.github` produces artifacts until the
  callers' pins are bumped") so an operator reading a zero can tell
  expected-quiet from broken.
- *Untrusted artifact content.* Mitigated by the size cap before download,
  the declared-uncompressed-size cap before reading, the single-member read,
  and the field allowlist — there is no record field that can hold prose, and
  the collector never logs artifact content, only counts and ids.
- *Over-broad GitHub token.* The existing `github-token` can write. Mitigated in
  code by the collector issuing only `GET` requests, and recorded as an optional
  owner step to mint a narrowed `actions:read, metadata:read` target.
- *Rate-limit pressure from a wide backfill.* Mitigated by `--max-pages`, by
  the per-repository artifact cap, and by the backfill being an explicit
  operator invocation rather than the scheduled default.
