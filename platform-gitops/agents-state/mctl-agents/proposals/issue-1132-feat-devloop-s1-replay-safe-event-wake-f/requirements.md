# S1: replay-safe, default-off event wake for the existing DevLoop merge watch

## Context

`DevLoopWorkflow._watch_pr` (orchestrator/temporal/workflows/dev_loop.py, main
line 6719) checks an implementation PR every `cadence.poll_interval` (15 min
under `CADENCE`, 30 min under `LEGACY_CADENCE`) for up to 14 days. That gives up
to one full interval of latency between a PR event (a merge, a close, a new head)
and the loop seeing it. Issue mctlhq/mctl-agents#1132 (parent
mctlhq/.github#437) asks for the first bounded slice of event-driven waking. A
versioned Temporal signal carries a small, validated reference to a PR event.
It only marks a coalesced "dirty" hint. The watch then re-reads the
authoritative PR state through the existing `get_pr_state` activity before
anything happens. The event payload never decides anything.

This slice covers only the workflow-local contract and offline tests and
fixtures in this repository. The capability is off by default. Turning it off
must reproduce today's command sequence byte for byte. Turning it on must not
change any time-based semantics: poll counters, grace polls, terminal
confirmation, shepherd tick cadence and budget, ownership heartbeat or refusal
backoff, merge-gate cadence, the absolute deadline, or the 15-minute fallback.
The producer, the transport and the consumer are not part of this slice. So are
the canary, the rollout and any worker bump. Each is a later slice under
mctlhq/.github#437.

## User stories

- AS a platform owner I WANT a merged or closed implementation PR to be noticed within about a minute of a matching event instead of up to 15 minutes later SO THAT deploy observation (stages 6.2-6.4) starts sooner, without new cost or new authority.
- AS a DevLoop maintainer I WANT the wake contract to be replay-safe and off by default SO THAT the 1.117.0 worker and every in-flight 14-day watch keep replaying unchanged.
- AS a reviewer of the dev loop's safety I WANT an event to be able to cause only an extra authoritative read SO THAT no event can start a workflow, mint a paid shepherd tick, take ownership, approve, merge or implement.
- AS the operator of a later canary slice I WANT measured fixture latency, a no-op read count and a query exposing wake counters SO THAT I can judge the canary against a baseline.

## Acceptance criteria (EARS)

Capability gating and replay

- WHILE the module constant `EVENT_WAKE_ENABLED` is False (the shipped default) THE SYSTEM SHALL never call `workflow.patched(EVENT_WAKE_PATCH)`. It SHALL also schedule exactly the commands `_watch_pr` schedules today: same timers, same durations, same activities, same order.
- WHEN a fresh (non-resumed) merge watch starts with `EVENT_WAKE_ENABLED` True THE SYSTEM SHALL evaluate `workflow.patched("merge-watch-event-wake-v1")` exactly once in the fresh-start arm, next to the existing markers. It SHALL store the result as `event_wake`.
- WHEN a merge watch resumes from a `MergeWatchResume` THE SYSTEM SHALL take `event_wake` from the carried `MergeWatchResume.event_wake` field and SHALL NOT re-evaluate the marker. A record written before this field existed SHALL decode as `event_wake=False`.
- WHEN a history recorded by a worker without this change (the committed fixtures, including `dev_loop_full.*`, `dev_loop_resumed.json` and `pre_m1/`) is replayed by the new code THE SYSTEM SHALL replay without `NondeterminismError`.
- WHILE `event_wake` is False for a watch THE SYSTEM SHALL accept the new signal handler's calls but ignore them, counted as `ignored_disabled`. It SHALL add no command to history.

Signal contract

- WHEN signal `pr_event_wake_v1` is delivered THE SYSTEM SHALL parse it defensively and never raise. It SHALL accept only a payload of at most these keys: `event_id` (non-empty str, at most 128 chars, `[A-Za-z0-9._:-]`), `repository` (`owner/name`, at most 200 chars), `pr_number` (int greater than 0), and optional `head_sha` (40 or 64 lowercase hex) and `run_id` (str, at most 64 chars).
- IF the payload is malformed, has unknown keys or exceeds those bounds THEN THE SYSTEM SHALL ignore it with reason `malformed`.
- IF no merge watch loop is currently active in this run (before `_watch_pr`, after it returned, or during the stage 6.2+ observation) THEN THE SYSTEM SHALL ignore the signal with reason `no_active_watch`.
- IF the watch has not yet resolved a PR (`watch.last` is None or not found) THEN THE SYSTEM SHALL ignore the signal with reason `unknown_pr`.
- IF `repository` (case-insensitive) or `pr_number` differs from the last resolved `PRState.repo`/`PRState.number` THEN THE SYSTEM SHALL ignore it with reason `mismatch`.
- IF `run_id` is present and differs from `workflow.info().run_id` THEN THE SYSTEM SHALL ignore it with reason `mismatch_run`.
- IF `event_id` is one of the last `EVENT_WAKE_DEDUPE_MAX` (32) accepted ids THEN THE SYSTEM SHALL ignore it with reason `duplicate`.
- IF `head_sha` is present and equals a previously observed head that is no longer the current head (one of the last `EVENT_WAKE_STALE_HEADS_MAX` (8) superseded heads) THEN THE SYSTEM SHALL ignore it with reason `stale`.
- IF the watch has been abandoned THEN THE SYSTEM SHALL ignore it with reason `abandoned`.
- WHEN a signal is accepted THE SYSTEM SHALL do two things only: record `event_id` in the dedupe ring and set one boolean dirty flag `_wake_pending`. Any number of accepted signals before the next woken read SHALL coalesce into one read.
- THE SYSTEM SHALL NOT start or signal any workflow from the signal handler. It SHALL NOT schedule any activity from it, and SHALL NOT change any approval, grant, merge, implement, ownership or shepherd state.

Woken read (between scheduled polls)

- WHILE `event_wake` is True THE SYSTEM SHALL replace only the bottom-of-loop `await workflow.sleep(cadence.poll_interval)` (main line 7195) with a bounded wait. The scheduled slot SHALL still end at the absolute time `slot_start + cadence.poll_interval`, so the next scheduled poll happens at the same wall-clock time as without events.
- WHEN `_wake_pending` is set during a slot and the watch is not abandoned THE SYSTEM SHALL clear the flag first and then run one `get_pr_state` activity with the existing `PR_STATE_TIMEOUT` and `PR_STATE_RETRY_POLICY` (a "woken read"). The read starts no earlier than `EVENT_WAKE_MIN_SPACING` (60 s) after the slot start or the previous woken read.
- IF a woken read resolves the PR as MERGED or CLOSED THEN THE SYSTEM SHALL end the watch through the same statements as a scheduled terminal poll: `_apply_found_state`, `_terminal_claim`, `return _WatchOutcome(last=state)`, and the unchanged `finally`.
- IF a woken read resolves the PR as OPEN, finds no PR, or raises any `ActivityError` THEN THE SYSTEM SHALL change no watch state other than the wake diagnostics (`_wake_last_head` and the counters). In particular it SHALL NOT touch `poll_index`, `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`, `watch.last`, `_poll_index_for_heartbeat`, shepherd ticks or the merge gate, and SHALL call no ownership activity. It SHALL then keep waiting for the rest of the same slot.
- IF a signal arrives while a woken read is running THEN THE SYSTEM SHALL run at most one more woken read after it completes, still subject to the spacing and per-slot caps.
- THE SYSTEM SHALL run at most `EVENT_WAKE_MAX_READS_PER_SLOT` (3) woken reads per scheduled slot and at most `EVENT_WAKE_MAX_READS_PER_RUN` (192) per workflow run. Past either cap a pending wake SHALL wait for the next scheduled poll.
- WHEN a scheduled poll runs THE SYSTEM SHALL clear `_wake_pending`, because that poll is itself the authoritative read.
- THE SYSTEM SHALL keep the transient-error retry sleep (main line 7017) as a plain `workflow.sleep`.

Unchanged semantics

- WHILE `event_wake` is True THE SYSTEM SHALL observe abandon at the same points as today (the `while` condition at slot boundaries) and SHALL NOT run a woken read once `_abandoned` is set.
- THE SYSTEM SHALL keep the absolute deadline, the hop predicate `_merge_watch_hop_suggested`, the deadline decision `_decide_watch_end`, the grace-poll and terminal-status exits and the `finally` block unchanged.
- THE SYSTEM SHALL never run more than one shepherd tick task or one merge gate task, and SHALL never create either from a woken read.
- WHEN the watch hops via continue_as_new THE SYSTEM SHALL carry `event_wake`, the dedupe ring, the stale-head list, the per-run counters reset to zero, and `_wake_pending` in `MergeWatchResume`. Each list SHALL stay within its cap: at most 32 ids times 128 chars, and 8 heads.
- THE SYSTEM SHALL expose the wake diagnostics through a new read-only query `event_wake_state`: enabled, accepted, ignored per reason, woken reads, woken reads that ended the watch, and the last wake latency in seconds. Queries add no history.

## Out of scope

- Any producer, transport (Valkey or stream) or consumer that sends `pr_event_wake_v1`. Any mctl-api or mctl-gitops change. Any live Temporal or Valkey access, and any new credential.
- Turning `EVENT_WAKE_ENABLED` on in a released worker, a canary, a worker image bump, a rollout or a merge of anything to production.
- Waking the approval park, the stage 6.2/6.3 release and deploy polls, or the incident watch.
- Using events to schedule shepherd ticks, the merge gate or ownership writes, or to cancel a gate on a head move. These are possible later slices that pay separately.
- CI-completion events (the GitHub stream producer does not emit them today, per the issue).
- Editing any `.status.yaml` or using any break-glass path.

## Open questions

- The clone has no git tags, so the 1.117.0 line references in the issue (dev_loop.py:519, 6227, 6505, 6708) could not be checked. The design is grounded on main `eec4fdd` and on the deployed tag read from gitops. The implementer should diff `_watch_pr` between 1.117.0 and main before recording fixtures.
- Turning the capability on: this slice uses a code constant (`EVENT_WAKE_ENABLED = False`). Turning it on is a reviewed code change plus a release. Whether the canary slice instead wants a starter-supplied `IssueRef` flag (which needs mctl-api) is left to that slice.
- Each signal is a history event, even when ignored. Bounding signal volume at the source (debounce at the producer) is a requirement on the future producer slice, not on this one. The workflow can only bound its own reaction.
- Whether a stale-head event (an older head) should be ignored or treated as a plain wake. This proposal ignores it, which is conservative and cheaper.
