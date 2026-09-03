# Design: issue-467-fix-alerts-mctlbridgedaemonsflapping-res

## Current state

- `deploy/alerts/mctl-telegram.rules.yaml` defines `MctlBridgeDaemonsFlapping` as:
  ```yaml
  expr: changes(mctl_bridge_active_daemons[10m]) > 20
  for: 0m
  ```
  It is a plain `PrometheusRule` CRD (`.spec.groups[].rules[]`), validated in CI by the
  `promtool-check` job in `.github/workflows/build.yml`, which extracts `.spec` with
  `yq` into a bare rules file and runs `promtool check rules` on it. That job currently
  only does syntax/lint validation — there is no `promtool test rules` (unit test)
  step for any alert in this repo yet.

- `mctl_bridge_active_daemons` is a `prometheus.Gauge` (`internal/metrics/metrics.go`,
  `r.BridgeActiveDaemons`). It is incremented/decremented only in
  `internal/bridge/hub.go`:
  - `Hub.Register` increments it on a brand-new connection for a user id, but not on an
    eviction of an existing one (`prev` already accounted for) — net change on eviction
    followed by re-register is 0, as the existing code comment states.
  - `Hub.Unregister` and `Hub.UnregisterSend` decrement it when a daemon disconnects.
  So one full disconnect-then-reconnect cycle for one daemon is exactly two gauge
  changes, regardless of how many failed dial attempts happened before the successful
  reconnect (failed dials never reach `Hub.Register`).

- `cmd/local/daemon.go` implements the daemon-side reconnect loop:
  ```go
  const (
      reconnectBase = 2 * time.Second
      reconnectMax  = 60 * time.Second
      ...
  )
  ```
  `runDaemon` doubles `backoff` after every failed `daemonSession` and clamps it to
  `reconnectMax`; it only resets to `reconnectBase` when the just-ended session ran for
  at least `reconnectMax`. A genuinely flapping daemon (session lengths near 0) never
  triggers that reset, so its backoff converges to and stays at 60s. Over a 10-minute
  sliding window that is at most floor(600/60) = 10 completed reconnect cycles once
  settled, i.e. at most 20 gauge changes — never strictly greater than 20. The alert
  only fires during the initial ramp (2s, 4s, 8s, 16s, 32s waits), then goes quiet.

- `docs/runbook.md`, anchor `#mctlbridgedaemonsflapping` (verified present via `grep`
  and covered by `deploy/alerts/runbook_links_test.go`, `TestRunbookURLsResolve`),
  currently documents the threshold as "changes ... more than 20 times in 10 minutes."
  That description is accurate to today's rule but reinforces the same wrong number if
  left unchanged.

- `deploy/alerts/runbook_links_test.go` already establishes the pattern of a plain Go
  test (`package alerts`, `go test ./...`) that inspects the raw rule YAML text with
  regexes rather than parsing/rendering it, specifically because it is a Helm-adjacent
  CRD manifest. This is the natural place to add a second, narrowly-scoped Go test that
  checks the numeric threshold itself does not regress, as a lightweight complement to
  a promtool-based rule unit test (see Proposed solution).

## Proposed solution

This is the issue's "option 1": lower the threshold to match a single daemon, recorded
explicitly as an interim, count-coupled fix.

1. **Change the alert expression** in `deploy/alerts/mctl-telegram.rules.yaml`:
   ```yaml
   expr: changes(mctl_bridge_active_daemons[10m]) > 4
   ```
   Add a rule comment (matching the existing style used for
   `MctlToolAvailabilityFastBurn` and the session-borrow group) explaining the
   derivation: a settled single-daemon flap produces ~20 changes/10min (10 cycles at
   the 60s backoff cap), a normal rollout produces exactly 2, and `> 4` is deliberately
   chosen with margin over the rollout case while staying far below the settled-flap
   floor — and that this is a fleet-size-coupled interim measure, to be replaced by a
   per-daemon connection counter (`mctl_bridge_connections_total`, not yet
   implemented) if/when the pilot grows.

2. **Add a promtool rule unit test** exercising the two acceptance scenarios end to end
   against the real rule expression:
   - A "settled flap" input series for `mctl_bridge_active_daemons` that alternates
     0/1 every 60s for 10+ minutes (the steady state described above) must produce a
     firing `MctlBridgeDaemonsFlapping` alert at `eval_time: 10m`.
   - A "rollout" input series that transitions 1 -> 0 -> 1 exactly once inside the
     window must produce no alert at `eval_time: 10m`.
   This is `promtool test rules`, not a Go test — it is the tool built for asserting
   behavior of a PromQL alerting expression against synthetic time series, and it
   exercises the actual expression Prometheus will evaluate (after the same `.spec`
   extraction the existing check already does), so a future edit to the expression, or
   an edit to `reconnectBase`/`reconnectMax` that changes the settled cycle period, is
   only caught if someone updates the test series to match reality — which is the
   point: the test freezes the *promise* (60s-cycle flap keeps firing), not just
   today's numbers.
   - File: `deploy/alerts/mctl_bridge_daemons_flapping_test.yaml` (promtool test-file
     format: `rule_files`, `evaluation_interval`, `tests[].input_series`,
     `tests[].alert_rule_test`).
   - CI: extend the existing `promtool-check` job in `.github/workflows/build.yml` to
     also run `promtool test rules deploy/alerts/mctl_bridge_daemons_flapping_test.yaml`
     against the same `yq`-extracted `/tmp/rules.yaml` used for `promtool check rules`
     (the test file's `rule_files` entry points at that generated path, consistent with
     the "expects a bare rules file" comment already in the workflow).

3. **Update `docs/runbook.md`** anchor `#mctlbridgedaemonsflapping`:
   - Change "changes more than 20 times in 10 minutes" to "changes more than 4 times
     in 10 minutes."
   - Add one sentence noting the threshold is sized for the current small daemon count
     and is expected to need re-tuning (or replacing with a connection-counter-based
     alert) as the pilot grows, so a future reader is not surprised by a lower number
     than they remember, or tempted to "fix" it back upward without checking the
     backoff math first.
   - The anchor itself, and the `runbook_url` in the rules file, are unchanged, so
     `TestRunbookURLsResolve` continues to pass without modification.

4. **No Go/application code changes.** `internal/bridge/hub.go`,
   `internal/metrics/metrics.go`, and `cmd/local/daemon.go` are read-only references for
   this proposal; the fix is entirely in the alert expression, its test, and its
   documentation.

## Alternatives

- **Option 2 from the issue: add `mctl_bridge_connections_total` and alert on
  `increase(...) > 3` per daemon.** Structurally the better fix — independent of fleet
  size, and per-daemon via labels so one bad daemon doesn't need the whole fleet's
  count factored in. Dropped from this proposal's scope because it requires new
  instrumentation (a counter alongside the existing gauge in `Hub.Register`/
  `Unregister`/`UnregisterSend`), a `internal/metrics/metrics_test.go` update, and
  design decisions this issue doesn't settle (which label(s) identify "a daemon" —
  `user_id` is the only identifier `Hub` has, per `internal/bridge/hub.go`'s
  `map[int64]*daemonConn`). Recorded as explicit follow-up in Out of scope rather than
  silently dropped.
- **Do nothing / leave `> 20`.** Rejected: this is the exact bug the issue reports —
  demonstrated by the backoff-math derivation above and the issue's own production
  observation of the alert resolving at ~10 minutes.
- **Scale the threshold by current daemon count dynamically (e.g.
  `> 2 * count(mctl_bridge_active_daemons)`), instead of a fixed number.** Rejected for
  this proposal: `mctl_bridge_active_daemons` is a single scalar gauge, not a
  per-daemon vector, so `count()` over it is meaningless (there is nothing to count
  across); building a real per-fleet-size threshold needs the same per-daemon
  cardinality that option 2's counter would provide. Not worth building a parallel
  vector gauge just to threshold off it when the counter is the more direct path.
- **Widen or narrow the `[10m]` window instead of changing the comparison threshold.**
  Rejected: the failure mode is that the *rate* of a settled flap (1 pair per 60s) is
  fixed by `reconnectMax`; shrinking the window shrinks both the flap count and the
  rollout-noise floor proportionally and doesn't change the ratio between them, so it
  does not improve separation the way directly correcting the threshold does, and it
  would also change the alert's reaction latency for unrelated reasons.

## Platform impact

- **Migrations:** none. This is a `PrometheusRule` and documentation change plus a new
  CI test step; no schema, no service deploy.
- **Backward compatibility:** the alert name, labels (`severity: warning`,
  `service: mctl-telegram`), and `runbook_url` are unchanged, so any existing
  Alertmanager routing/silences keyed on those fields keep working. The `for: 0m`
  behavior is unchanged.
- **Resource impact:** negligible — a lower `changes() > N` threshold on an
  already-scraped gauge does not add cardinality or scrape load. The new promtool test
  file runs only in CI.
- **Risks + mitigations:**
  - *Risk:* `> 4` is still coupled to daemon count and could become noisy as the Local
    Bridge pilot grows past a handful of accounts (the issue calls this out explicitly
    for option 1). *Mitigation:* the rule comment and runbook update both flag this
    plainly as an interim, count-coupled choice, and Out of scope records option 2 as
    the intended structural fix, so the next person touching this alert has the
    reasoning in front of them instead of having to reconstruct it from a git blame.
  - *Risk:* the promtool test's "settled flap" series (alternating every 60s) is an
    idealization; a real flapping daemon's backoff ramps for the first ~2 minutes
    before settling, so the true worst-case density during that ramp is higher, not
    lower, than what the test asserts. *Mitigation:* this only means the test is
    slightly conservative (it tests the harder-to-catch settled state, not the easier
    ramp), which is the correct direction for a regression guard — it must not
    understate the deployed behavior.
  - *Risk:* CI now depends on `promtool test rules` behaving the same way across the
    pinned `PROM_VERSION=2.52.0` used in `.github/workflows/build.yml`; no version
    change is proposed, so this is a null risk for this change, noted only because the
    new test step reuses that same binary.
