# In-cluster collector moves claude-review model-usage-records artifacts into the usage ledger

## Context

The reviewer is the one DevLoop stage whose model call does not run inside
mctl-agents. It runs in GitHub Actions, in the reusable workflow
`mctlhq/.github/.github/workflows/claude-review.yml` (mctlhq/.github#126),
which already captures ADR-012 model-usage records at the model-call boundary
and publishes them as the `model-usage-records` workflow artifact plus a job
summary table. That workflow deliberately does not post them: the ingest
endpoint was admin-only when it was written, and an admin credential does not
belong in every caller repository. So reviewer spend is measured but never
lands in the ledger, and every "what did this DevLoop cost" answer is short by
the reviewer's share — which, measured on a real artifact
(`mctlhq/.github` run 36206815658), is 22381 output tokens and 3.1M cache-read
tokens on Opus for a single PR review.

Owner decision 1 on mctlhq/.github#50 (comment 5844714851) is that the reviewer
stage must reach the ledger **through a collector** — artifact-only reviewer
usage is not final acceptance. The standing constraint from 2026-09-24 is that
no new long-lived secret may be added to GitHub, so the collector must **pull**
from inside the cluster, where both credentials it needs already live: the
`mctl-agents` GitHub App installation token (Vault `platform/mctl-agents` →
`mctl-agents-secrets/github-token`, which carries `actions` access across the
installation) and the confined usage-writer bearer (Vault
`platform/mctl-agents#usage-writer-token` →
`mctl-agents-secrets/usage-writer-token`, the `service:mctl-agents-usage`
principal that mctl-api confines to `POST /api/v1/usage/records`,
mctl-api#385). This proposal adds that collector to mctl-agents as a periodic,
model-free sweep on the existing image: list the `model-usage-records`
artifacts of the mctlhq caller repositories, download them read-only, and post
their records to the ledger.

## User stories

- AS a platform FinOps analyst I WANT reviewer-stage model usage in the same
  ledger as investigator, implementer and shepherd usage SO THAT a per-PR or
  per-repository spend figure is complete instead of silently missing the
  review.
- AS a platform FinOps analyst I WANT reviewer records to carry
  `devloop_stage=reviewer`, `target_repo` and `pr_number` SO THAT I can filter
  reviewer spend by stage and attribute it to the pull request that caused it.
- AS a platform operator I WANT the collector to be re-runnable at any cadence
  and over any lookback window SO THAT a missed tick, a restart or a deliberate
  backfill never double-counts a paid invocation.
- AS a security owner I WANT the collector to add no secret to GitHub and to
  only read artifacts SO THAT capturing reviewer usage does not widen the
  platform's GitHub credential surface.
- AS a reviewer of a pull request I WANT usage collection to be completely
  detached from the review SO THAT a collector outage never delays, blocks or
  fails a PR review.

## Acceptance criteria (EARS)

Discovery and download

- WHEN the collector runs THE SYSTEM SHALL, for each configured mctlhq
  repository, list that repository's artifacts named `model-usage-records` via
  `GET /repos/{owner}/{repo}/actions/artifacts?name=model-usage-records`, using
  the in-cluster GitHub App token from `GITHUB_TOKEN`.
- WHILE listing artifacts THE SYSTEM SHALL consider only artifacts whose
  `created_at` falls inside the configured lookback window and whose `expired`
  field is false, and SHALL bound the number of result pages it reads per
  repository.
- WHEN an artifact is in window THE SYSTEM SHALL download it with
  `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` and read the
  single `model-usage-records.json` member out of the returned zip.
- IF a downloaded zip exceeds the configured maximum size, or declares an
  uncompressed member larger than that maximum, THEN THE SYSTEM SHALL skip that
  artifact with a warning and SHALL NOT read it into memory.
- WHILE running THE SYSTEM SHALL perform only read operations against GitHub
  and SHALL NOT write a comment, label, status, artifact or any other GitHub
  object.

Record handling

- WHEN a `model-usage-records.json` member parses as an object with a
  `records` list THE SYSTEM SHALL treat each list element that is an object as
  a candidate usage record.
- WHEN building the body it posts THE SYSTEM SHALL keep only the ADR-012 record
  fields it recognises, from an explicit allowlist, and SHALL drop every other
  key.
- WHILE building the body THE SYSTEM SHALL drop any `id` field present on a
  candidate record, because mctl-api derives the row id itself from
  `(session_id, result_uuid, model_key[, num_turns])` and rejects a supplied id
  that disagrees with the derived one.
- IF a candidate record has no non-empty `session_id` or no non-empty
  `model_key` THEN THE SYSTEM SHALL drop it with a warning rather than post it,
  because mctl-api rejects such a record and the ingest is one transaction.
- IF a candidate record declares a `schema_version` other than 1 THEN THE
  SYSTEM SHALL drop it with a warning naming the version it saw.
- WHILE building the body THE SYSTEM SHALL preserve `agent`, `devloop_stage`,
  `target_repo`, `pr_number`, `retry_attempt` and every token counter exactly as
  the artifact reports them, SHALL NOT substitute a default for an absent
  counter, and SHALL NOT add `argo_workflow_name`, `temporal_workflow_id`,
  `work_item_id` or `execution_id` from its own pod environment.
- WHILE building the body THE SYSTEM SHALL NOT set `calculated_cost`,
  `pricing_version` or `provider_reported_cost`.

Delivery and idempotency

- WHEN it has records to deliver THE SYSTEM SHALL POST them to
  `{MCTL_API_BASE_URL}/api/v1/usage/records` with the
  `MCTL_USAGE_WRITER_TOKEN` bearer, in chunks of at most 500 records and at
  most 1 MiB of body, matching mctl-api's ingest limits.
- IF `MCTL_API_BASE_URL` is not an `https://` URL THEN THE SYSTEM SHALL send
  nothing and SHALL log one warning naming the URL.
- IF `MCTL_USAGE_WRITER_TOKEN` is unset or empty THEN THE SYSTEM SHALL log one
  warning, post nothing, and exit successfully.
- WHEN a chunk is accepted THE SYSTEM SHALL log that chunk's `accepted_count`
  and `deduped_count` as reported by mctl-api.
- WHEN the same artifact is collected a second time THE SYSTEM SHALL produce a
  body identical to the first delivery, so that mctl-api's insert-or-ignore on
  the derived id makes the second delivery add no row and report every record
  as deduped.
- WHILE collecting THE SYSTEM SHALL keep no local high-water mark or other
  durable cursor, so that correctness never depends on state surviving between
  ticks.

Failure handling and operability

- IF listing, downloading or parsing fails for one repository or one artifact
  THEN THE SYSTEM SHALL log the failure with the repository and artifact id,
  count it, and continue with the next repository or artifact.
- IF a delivery chunk fails THEN THE SYSTEM SHALL log the failure, count the
  undelivered records, and continue with the next chunk, relying on the next
  tick to re-collect them.
- WHEN a run finishes THE SYSTEM SHALL print one summary line naming
  repositories swept, artifacts read, artifacts skipped, records posted,
  records deduped and failures.
- IF the GitHub CLI cannot authenticate at all THEN THE SYSTEM SHALL exit
  non-zero, so the CronWorkflow surfaces a genuine credential outage.
- IF only individual repositories or artifacts failed THEN THE SYSTEM SHALL
  exit zero, so one bad repository does not turn the sweep red.
- WHEN invoked with `--dry-run` THE SYSTEM SHALL do everything except the POST
  and SHALL report what it would have posted, without requiring
  `MCTL_USAGE_WRITER_TOKEN`.

Ownership boundary

- WHILE this proposal is implemented THE SYSTEM SHALL NOT create, enable or
  modify any Argo `CronWorkflow` or `ClusterWorkflowTemplate`; the scheduling
  half SHALL be delivered as a documented owner step in the mctl-agents repo
  with the manifest content the owner applies to mctl-gitops.

## Out of scope

- The agy reviewer (`.github/workflows/agy-review.yml`,
  `mctlhq/.github/.github/workflows/agy-review.yml`). It emits no usage record
  today, so there is nothing for a collector to read.
- Changing `mctlhq/.github/.github/workflows/claude-review.yml`. The artifact
  contract it publishes is consumed as-is.
- Bumping the pinned `uses:` SHA in any caller repository's
  `.github/workflows/claude-review.yml`. As measured on 2026-09-26 every caller
  except `mctlhq/.github` itself pins a reusable-workflow revision that predates
  the usage capture, so those repositories currently publish no artifact. The
  bump is a per-repository change and is recorded here as an owner step, not
  performed.
- Creating or applying the Argo `CronWorkflow` / `ClusterWorkflowTemplate` in
  mctl-gitops, and provisioning any Vault secret. Both are owner steps.
- Populating `devloop_stage` on mctl-agents' own producer. That is
  mctlhq/mctl-agents#504, a separate proposal against
  `orchestrator/usage_ledger.UsageRecorder`; this collector only forwards the
  `devloop_stage` the artifact already carries.
- Cost computation. mctl-api prices the token counts from its own versioned
  catalog at ingest (ADR-012), and this collector sends no cost field.
- Dashboards, budget enforcement, and any read-side query surface.
- Backfilling reviewer usage older than GitHub's 90-day artifact retention. It
  is unrecoverable: the records only ever existed in the artifact.

## Open questions

- **Lookback default versus retention.** The issue asks for "a bounded lookback
  window [that] covers the artifact retention", and retention is 90 days
  (`retention-days: 90` in the reusable workflow; a 2026-09-26 artifact reports
  `expires_at: 2026-12-25`). Re-downloading 90 days of artifacts on every tick
  is correct but wasteful. Proceeding with a `--lookback-days` flag defaulting
  to 3 for the scheduled tick — enough slack for a multi-tick outage — and
  documenting `--lookback-days 90` as the one-shot backfill an owner runs once
  after enabling the cron. Both are safe because the ledger dedupes.
- **Cadence.** The issue says "periodic" without a number. Proceeding with
  hourly at a minute offset that avoids the existing cron family
  (`:03` reconcile, `:07` issue-poll, `:09` shepherd, `:11`/`:15` incidents,
  `:00` token rotation), proposed `:21`. The collector takes no gitops mutex
  and pushes nothing, so the offset is only about GitHub API rate budget.
- **Token narrowing.** The collector needs `actions:read` and `metadata:read`
  only, but `mctl-agents-secrets/github-token` is minted unscoped and carries
  `contents:write`, `actions:write`, `issues:write`, `pull_requests:write`
  across the installation (see `docs/runbooks/github-app-scope-audit.md` in
  mctl-gitops). Proceeding with the existing secret, because the issue's
  constraint is "no new secret in GitHub" and a narrowed in-cluster token is a
  mctl-gitops rotation-target change. A narrowed target
  (`permissions: {actions: read, metadata: read}`) is recorded as a recommended,
  optional owner step.
- **Repository set.** Proceeding with `config.settings.SERVICES` mapped to
  `mctlhq/<service>`, which is the list every other sweep in this repo already
  uses, plus a `--repo` override for a one-off. A caller repository outside
  `SERVICES` would not be swept; no such repository exists today.
