# Tasks: issue-467-fix-alerts-mctlbridgedaemonsflapping-res

- [ ] 1. Change the `MctlBridgeDaemonsFlapping` expression in
      `deploy/alerts/mctl-telegram.rules.yaml` from
      `changes(mctl_bridge_active_daemons[10m]) > 20` to
      `changes(mctl_bridge_active_daemons[10m]) > 4`, and add a YAML comment above the
      rule (matching the style of the comments already above
      `MctlToolAvailabilityFastBurn` and the `mctl-telegram-session-borrow` group)
      explaining: settled single-daemon flap ~= 20 changes/10min (10 cycles at the
      60s `reconnectMax` backoff cap in `cmd/local/daemon.go`), a normal rollout = 2
      changes, `> 4` is an interim, daemon-count-coupled threshold pending a
      per-daemon connection-counter alert (see issue #467). — DoD: `git diff` shows
      only the `expr:` value and the added comment changed in this rule block; `promtool
      check rules` (extracted `.spec`) still passes; no other alert in the file is
      touched.

- [ ] 2. Update `docs/runbook.md` anchor `#mctlbridgedaemonsflapping` (depends on 1):
      change "changes more than 20 times in 10 minutes" to "changes more than 4 times
      in 10 minutes," and add a sentence noting the threshold is sized for the current
      small daemon count and is expected to need re-tuning, or replacing with a
      connection-counter-based alert, as the pilot grows. Do not rename or move the
      `<a id="mctlbridgedaemonsflapping"></a>` anchor. — DoD: `go test ./deploy/alerts/...`
      (`TestRunbookURLsResolve`) still passes; the anchor text and its "Symptom" section
      both state the same number (4) as the rule's `expr`.

- [ ] 3. Add the promtool rule unit test file
      `deploy/alerts/mctl_bridge_daemons_flapping_test.yaml` (depends on 1) with two
      cases against `MctlBridgeDaemonsFlapping`:
      - a "settled flap" `mctl_bridge_active_daemons` series alternating 0/1 every 60s
        out to at least 10 minutes, asserting the alert IS firing at `eval_time: 10m`;
      - a "rollout" series with exactly one 1 -> 0 -> 1 transition pair inside the
        10-minute window, asserting the alert is NOT firing at `eval_time: 10m`.
      Point `rule_files` at the same extracted bare-rules path the CI job already
      produces (see task 4). — DoD: running `promtool test rules
      deploy/alerts/mctl_bridge_daemons_flapping_test.yaml` locally against a
      `yq '.spec' deploy/alerts/mctl-telegram.rules.yaml`-extracted file passes with
      today's `> 4` expression, and fails if the expression is manually reverted to
      `> 20` (confirms the test actually discriminates the two thresholds).

- [ ] 4. Extend the `promtool-check` job in `.github/workflows/build.yml` (depends on
      3) to run `promtool test rules
      deploy/alerts/mctl_bridge_daemons_flapping_test.yaml` immediately after the
      existing `promtool check rules /tmp/rules.yaml` step, reusing the same
      `/tmp/rules.yaml` extraction and the same pinned `promtool` binary. — DoD: the
      job has both `promtool check rules` and `promtool test rules` steps; no new
      `PROM_VERSION` or extra download is introduced.

## Tests

- [ ] T1. `promtool test rules deploy/alerts/mctl_bridge_daemons_flapping_test.yaml`
      (task 3) — the settled-flap case fires, the rollout case stays silent, both
      against the real `expr` shipped in `deploy/alerts/mctl-telegram.rules.yaml`.
- [ ] T2. `promtool check rules /tmp/rules.yaml` (existing CI step, task 1) — the
      edited rule file is still syntactically valid.
- [ ] T3. `go test ./deploy/alerts/...` (existing `TestRunbookURLsResolve`, task 2) —
      the `runbook_url` for `MctlBridgeDaemonsFlapping` still resolves to an existing
      anchor after the runbook edit.
- [ ] T4. Manual/CI-log spot check: confirm the new promtool test step's failure output
      is legible (alert name + eval_time) if intentionally broken during review, since
      this is the acceptance criterion the issue cares most about (a test that can
      actually catch a future regression, not just a silent-rollout check).

## Rollback

- The change is confined to `deploy/alerts/mctl-telegram.rules.yaml` (one `expr` line
  plus a comment), `docs/runbook.md` (one anchor's text), a new standalone promtool
  test fixture, and a CI workflow step. Revert is a plain `git revert` of the PR's
  squash commit — no data migration, no running service redeploy is involved beyond
  whatever process re-syncs the `PrometheusRule` CRD (ArgoCD, per repo convention).
- If the new `> 4` threshold proves too noisy in production before option 2 (the
  connection counter) is built, the immediate mitigation is to raise the threshold
  again (e.g. back toward `> 20` or an intermediate value) with the same promtool test
  updated to match — do not silently widen the window or add a `for:` duration as a
  workaround without re-deriving the cycle math in Design, since that reintroduces the
  same class of bug this proposal fixes.
