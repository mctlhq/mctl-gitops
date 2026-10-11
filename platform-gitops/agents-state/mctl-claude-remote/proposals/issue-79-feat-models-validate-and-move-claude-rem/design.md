# Design: issue-79-feat-models-validate-and-move-claude-rem

## Current state

- **Model selection.** `entrypoint.sh` (around lines 194-232) reads
  `CLAUDE_REMOTE_MODEL` (default `haiku`), rejects values containing characters outside
  `A-Za-z0-9._-` (falling back to `haiku` with a WARN), and uses `ensure_json` to force
  `.model` in `/workspace/.claude/settings.json` on every start. Because the guard
  compares `.model == "$CLAUDE_REMOTE_MODEL"`, changing the env var re-pins the model on
  the next start, which is what makes a one-variable rollback work. `claude-haiku-5-5`
  already passes the guard. The comment above the block says Channel deployments
  "must set this to sonnet" because of #66.
- **CLI version.** `Dockerfile` pins `ARG CLAUDE_CODE_NPM_VERSION=2.1.280`; the session
  runs that binary (`DISABLE_AUTOUPDATER=1` in labs keeps it so).
- **pr-steward** uses `STEWARD_MODEL="${PR_STEWARD_MODEL:-sonnet}"` with explicit
  `--model` (entrypoint.sh ~line 631) and is independent of this change.
- **Events Channel.** `events/mctl_events/channel.py` reads Valkey Streams, pushes
  `notifications/claude/channel` turns (`notification_for`, ending with
  "Then call ack_event."), bounds in-flight entries by `policy.max_inflight` (default 5,
  `policy.py`), and XACKs only in `Adapter.ack` via the `ack_event` MCP tool. Each stage
  is audited to `mctl:events:audit` (`received`, `delivered`, `delivery_failed`,
  `duplicate`, `acked` with `outcome`+`note`, `skipped`, `rejected`). Stale in-flight
  events are re-pushed (`redeliver_stale`) and rejected after `max_attempts`.
- **Contract delivery.** Because Claude Code marks channel content untrusted,
  `ensure_events_contract` in `entrypoint.sh` writes a managed section into
  `/workspace/CLAUDE.md` stating the five-point contract (hydrate via `gh pr view` /
  `mctl-telegram get_messages`; end with `mcp__mctl-events__ack_event`; text, shell or
  files acknowledge nothing). `events/tests/test_entrypoint_events_contract.py` keeps its
  vocabulary in sync with `channel.py`.
- **Operations.** `docs/events-operations.md` documents reading the audit stream with the
  read-only `events-observer` user and interpreting `pending`/`lag`; transcripts are
  persisted under `/workspace/.claude/projects/*.jsonl`.
- **Labs override.** `mctl-gitops/platform-gitops/services/labs/claude-remote/values.yaml`
  sets `CLAUDE_REMOTE_MODEL: "sonnet"` with a comment describing #66.

There is no tool today that correlates the audit stream with the session transcript, so
"did the model really call ack_event for every handled event" can only be answered by
hand. That is the gap this proposal fills before any rollout.

## Proposed solution

Three deliverables in this repo, then an operator-run validation, then a gated GitOps PR.

### 1. Offline evaluator: `events/mctl_events/model_eval.py`

A stdlib-only module (same style as the rest of `mctl_events`, no new deps) runnable as
`python -m mctl_events.model_eval --audit audit.jsonl --transcript session.jsonl
[--transcript ...] --model <label> --out report.json`.

Inputs:
- an export of `mctl:events:audit` entries for the run window (one JSON object per line,
  as produced by `XRANGE` through the observer user; a helper shell one-liner is in the
  runbook);
- one or more Claude Code transcript JSONL files from `/workspace/.claude/projects/`.

Per `event_id` seen as `delivered` it computes:
- `acked`: an `acked` audit record exists (its `outcome` is recorded);
- `real_ack_call`: a transcript `tool_use` with name `mcp__mctl-events__ack_event` whose
  input `event_id` matches, and whose `tool_result` is not an error;
- `hydration_calls`: `tool_use` entries of Bash `gh pr view ...` or
  `mcp__mctl-telegram__get_messages` in the same turn;
- `fake_ack`: any Bash/Write/Edit tool_use in the turn whose command/path/content matches
  acknowledgement simulation patterns (`/tmp/*ack*`, `ack_event` in a shell command,
  JSON with `"outcome"` written to a file) - the exact #66 signature;
- `fabricated_success`: assistant text claiming acknowledged/hydrated while the matching
  tool_use is missing or its result is an error;
- latency (`delivered` timestamp to `acked` timestamp) and token usage from the
  transcript's per-message `usage` blocks, attributed to the turn.

Aggregates: handled+acked rate, missing ack count, fake ack count, fabricated success
count, malformed tool input count, p50/p95 latency, input/output/cache tokens, and an
estimated cost from a small price table passed by flag (`--price-in`, `--price-out`
per MTok) so no prices are hard-coded. Exit status is non-zero when any of
`fake_ack`, `handled_unacked`, `fabricated_success` is non-zero - this is the GO gate.

Pending/drain is not in the transcript; the runbook captures `XINFO GROUPS` before and
after and the evaluator accepts `--pending-after N` to include it in the gate.

### 2. Runbook and results record: `docs/model-validation.md`

- Environment: a validation session started with `MCTL_EVENTS_ENABLED=true`,
  `CLAUDE_REMOTE_MODEL=<candidate>`, and a policy pointing at a dedicated consumer group
  (e.g. `claude-remote-eval`) so labs' group is untouched.
- Event set (identical for both models): at least 20 consecutive allowed events mixing
  `github.pull_request.*` (real PR refs) and `telegram.message.*` hydrated via the
  configured Telegram MCP; plus failure cases: Telegram MCP unreachable / token file
  missing, a `gh` hydration that errors (nonexistent PR number), a malformed envelope
  (expect adapter `rejected`, model never sees it), and a redelivery (`attempt > 1`).
- Procedure: model check (`claude --model claude-haiku-5-5 -p "ok"` on the pinned image),
  run Sonnet baseline, run Haiku 5.5, export audit + transcripts, run the evaluator,
  capture `XINFO GROUPS` showing `pending=0` and continued reads, fill the comparison
  table.
- A results section (GO/NO-GO, date, image tag, CLI version, both reports) that the
  operator fills in; NO-GO records exact event ids and transcript excerpts.
- Rollout and rollback steps (below), and the post-rollout soak checklist.

### 3. Comment and README updates

- `entrypoint.sh` model comment: replace "Deployments that run the inbound events
  Channel must set this to sonnet" with: Channel deployments must run a model validated
  per `docs/model-validation.md`; #66 kept as history (previous Haiku generation faked
  the ack); validated values listed with the evidence date. No behaviour change; the
  default stays `haiku`. If validation is NO-GO the comment simply names the failed
  model id and keeps `sonnet`.
- `README.md` events section: one paragraph pointing at the runbook and stating that
  `CLAUDE_REMOTE_MODEL` is the single rollback variable.

### 4. Companion GitOps change (operator, after GO only)

In `platform-gitops/services/labs/claude-remote/values.yaml`: set
`CLAUDE_REMOTE_MODEL: "claude-haiku-5-5"` and rewrite the comment to: validated on
<date> per mctl-claude-remote#79 (link results), #66 as history, rollback = `"sonnet"`.
After sync, soak 72 h watching `acked` vs `delivered` in the audit stream and
`pending` per `docs/events-operations.md`; attach the evaluator report over the soak's
real events to #79 and only then close #66.

Explicit id rather than alias: the alias floats to future Haiku releases, which would
re-open #66 without review; the explicit id makes every future model change a
reviewable GitOps diff, which is what the issue requires.

## Alternatives

- **Flip labs to `haiku`/`claude-haiku-5-5` directly and watch the audit stream.** Dropped:
  this is exactly how #66 went undetected for four days; the failure mode is silent
  until `max_inflight` saturates.
- **Detect fake acks at runtime in the adapter (e.g. auto-ack on timeout, or watch for
  `/tmp/ack*` files).** Dropped: it weakens the protocol to accommodate the model, which
  the issue forbids; existing `redeliver_stale`/`max_attempts` already bound damage.
- **Manual transcript review without an evaluator.** Dropped: not repeatable, error-prone
  over 20+ events per model, and does not give a mechanical GO gate for future model
  changes (e.g. the next Haiku/Sonnet release).
- **Pin the image default to `claude-haiku-5-5`.** Dropped as out of scope: the issue
  keeps the generic default on the alias; the deliberate pin belongs to the deployment.

## Platform impact

- **Migrations / compatibility:** none. The evaluator is an offline tool; no runtime code
  path, env var, or settings key changes. Existing images and the `sonnet` override keep
  working.
- **Resources:** the validation session costs two bounded runs of model usage (~40+ events)
  and a temporary consumer group on Valkey; delete the group after the run.
- **Risks and mitigations:**
  - Evaluator false negatives (a fake ack pattern it does not recognise): the gate also
    requires an `acked` audit record per handled event, which only `Adapter.ack` writes,
    so an unrecognised fake still shows as handled-unacked.
  - Transcript format drift across Claude Code versions: the parser targets the
    `type: assistant` / `tool_use` / `tool_result` / `usage` fields and is tested on
    fixtures; unknown lines are counted and reported, not ignored silently.
  - Model id unsupported on 2.1.280: detected in the first runbook step; then a CLI bump
    PR precedes the validation.
  - Post-rollout regression: one-line revert to `sonnet`; `ensure_json` re-pins on the
    next pod start; in-flight events are redelivered by `recover_pending` after restart.
  - Audit notes contain short hydrated content (`docs/events-operations.md`); exported
    audit files and transcripts attached to issues must be redacted or summarised.
