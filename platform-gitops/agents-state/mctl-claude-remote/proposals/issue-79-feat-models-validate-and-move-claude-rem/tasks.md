# Tasks: issue-79-feat-models-validate-and-move-claude-rem

- [ ] 1. Add `events/mctl_events/model_eval.py` (stdlib only): parse an audit-stream
  JSONL export and one or more Claude Code transcript JSONL files; per delivered
  `event_id` compute `acked`, `real_ack_call`, `hydration_calls`, `fake_ack`,
  `fabricated_success`, latency, tokens; aggregate rates, p50/p95 latency, token totals,
  cost from `--price-in/--price-out`; accept `--pending-after`; write JSON report and a
  Markdown summary table; exit non-zero when fake acks, handled-unacked, fabricated
  success or `pending-after > 0`. — DoD: `python -m mctl_events.model_eval --help` works;
  module has no third-party imports; tests T1-T6 pass.
- [ ] 2. Add test fixtures under `events/tests/fixtures/model_eval/` (depends on 1):
  a clean run, the #66 signature (Bash writing `/tmp/ack.json`, no `ack_event`), a
  handled-but-unacked turn, an `ack_event` call that returned an error followed by a
  "done" claim, a failed hydration acknowledged as `failed`, and an unknown-line case.
  — DoD: fixtures are synthetic (no real message content) and drive `events/tests/test_model_eval.py`.
- [ ] 3. Add `docs/model-validation.md` (depends on 1): environment (dedicated consumer
  group, `MCTL_EVENTS_ENABLED=true`, `CLAUDE_REMOTE_MODEL=<candidate>`), model-id smoke
  check on `CLAUDE_CODE_NPM_VERSION`, the bounded event set (>= 20 consecutive allowed
  events mixing `github.pull_request.*` and `telegram.message.*`, plus failure cases:
  Telegram MCP unavailable, `gh` hydration error, malformed envelope, `attempt > 1`),
  audit export command via the `events-observer` user, `XINFO GROUPS` before/after,
  evaluator invocation, comparison table template (Sonnet vs Haiku 5.5), GO/NO-GO rule
  (zero fake acks, zero handled-unacked, zero fabricated success, pending drained),
  rollout, rollback and 72 h soak checklist, redaction note. — DoD: linked from
  `docs/events-operations.md` and README.
- [ ] 4. Update the model comment in `entrypoint.sh` (~lines 194-207) (depends on 3):
  Channel deployments must run a model validated per `docs/model-validation.md`; keep
  #66 as historical context; state `sonnet` as the known-good rollback. No code change;
  default remains `haiku`. — DoD: diff touches comments only; existing entrypoint tests pass.
- [ ] 5. Add a README paragraph in the events section (depends on 3) naming
  `CLAUDE_REMOTE_MODEL` as the single rollback variable and linking the runbook. — DoD:
  README renders; no other sections changed.
- [ ] 6. Add a test that the model block accepts `claude-haiku-5-5` and re-pins `.model`
  when switched back to `sonnet` (depends on 4), cutting the block out of `entrypoint.sh`
  the same way `test_entrypoint_events_contract.py` does. — DoD: T7 passes in CI
  (`pr-checks.yml`).
- [ ] 7. Operator: run the validation per `docs/model-validation.md` for `sonnet` and
  `claude-haiku-5-5`; append results (image tag, CLI version, reports, GO/NO-GO) to the
  runbook's results section in a follow-up PR and summarise on #79. (depends on 1-3)
  — DoD: both evaluator reports attached (redacted); decision recorded with failing
  event ids if NO-GO.
- [ ] 8. Operator, only if GO: open the `mctl-gitops` PR changing
  `platform-gitops/services/labs/claude-remote/values.yaml` to
  `CLAUDE_REMOTE_MODEL: "claude-haiku-5-5"` with a rewritten comment (validated date,
  link to #79 results, #66 history, rollback `"sonnet"`). (depends on 7) — DoD: PR
  reviewed and merged; ArgoCD synced; settings.json shows the new model after restart.
- [ ] 9. Operator: 72 h soak after task 8; run the evaluator over the soak window's real
  events; attach report to #79; close #66 only if the gate passes. Exercise the rollback
  once (task Rollback) and record it. (depends on 8) — DoD: soak report attached;
  rollback tested and documented.

## Tests

- [ ] T1. Clean fixture: every delivered event has `acked` + real `ack_event` call; exit 0;
  handled+acked rate 100%.
- [ ] T2. #66 fixture (Bash writes `/tmp/ack.json`, no `ack_event`, no `acked` record):
  `fake_ack=1`, `handled_unacked=1`; exit non-zero.
- [ ] T3. `ack_event` tool_result is an error and the assistant then claims success:
  `fabricated_success=1`; exit non-zero.
- [ ] T4. Hydration fails and the event is acked with `outcome=failed`: counted as correct,
  exit 0.
- [ ] T5. Token/latency aggregation: known usage numbers and timestamps produce exact
  totals, p50/p95 and cost for given prices.
- [ ] T6. `--pending-after 2` makes an otherwise clean run exit non-zero; unknown
  transcript lines are counted in the report.
- [ ] T7. Entrypoint model block: `CLAUDE_REMOTE_MODEL=claude-haiku-5-5` writes
  `"model": "claude-haiku-5-5"`; rerun with `sonnet` re-pins `.model` to `sonnet`; an
  invalid value still falls back to `haiku` with the WARN.
- [ ] T8. Existing suite (`events/tests`) remains green.

## Rollback

- Repo changes (evaluator, docs, comments, tests) have no runtime effect; revert the PR
  if needed.
- Labs rollout: revert the `mctl-gitops` commit or set
  `CLAUDE_REMOTE_MODEL: "sonnet"` in `platform-gitops/services/labs/claude-remote/values.yaml`.
  On the next pod start `ensure_json` re-pins `/workspace/.claude/settings.json` `.model`
  to `sonnet`; unacknowledged entries are redelivered by `recover_pending`. If
  `max_inflight` was saturated, confirm `pending` drains per `docs/events-operations.md`
  after the restart.
