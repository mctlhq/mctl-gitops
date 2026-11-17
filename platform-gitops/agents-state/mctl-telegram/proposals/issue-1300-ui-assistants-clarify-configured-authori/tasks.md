# Tasks: issue-1300-ui-assistants-clarify-configured-authori

File allowlist: `internal/web/manage_assistant.go`,
`internal/web/manage_assistant_test.go`, `internal/web/assistants.html`,
`internal/web/assistants_test.go`. Stop and ask for a separate decision if any
other file, a new backend field or API, or a new dependency seems necessary.

- [ ] 1. Write the rendering tests first (T1-T9 below) against the current
  template, and confirm that T1 (regression) and the matrix cases fail on
  current main — DoD: `go test ./internal/web -run 'ManageAssistant|AssistantAuthority|Assistants'`
  shows the new tests failing for the documented reason ("Replies on its own"
  printing AutoIntents in observe/paused), and existing tests passing.
- [ ] 2. Add `assistantAuthorityView` and the pure `assistantAuthorityOf(assistant string, s *assistantinstall.Settings)`
  in `internal/web/manage_assistant.go`, implementing the design.md matrix.
  Precedence: off > unrecognized > paused > not listening > observing >
  guarded. Fork detection uses `db.IsForkAssistant`. Hold-reason text comes
  from `policy.OwnerHoldReasons` with only the approval `Reason*` constants
  (depends on 1) — DoD: helper unit tests T2 pass; no I/O in the helper;
  `go vet` clean; no import cycle.
- [ ] 3. Add `Authority *assistantAuthorityView` to `assistantSectionView` and
  set it in `buildAssistantSection` from `cur.Assistant` and `v.Settings`.
  Do not add reads or change the existing error paths (depends on 2) — DoD:
  no change to `LoadErr`, `CatalogUnavailable` or handler behaviour; existing
  manage tests pass.
- [ ] 4. Update `manageAssistantSection`: replace the "Replies on its own" and
  "Never" rows with the authority block (`assistant-state`, `assistant-auto`,
  `assistant-auto-configured`, `assistant-approval`, `assistant-never`,
  `assistant-unverified`). Relabel the Paused and Listening rows as saved
  settings, keeping their ids and yes/no values. Render "Configured authority
  is unavailable" when Settings is nil. Use existing CSS classes only, no form
  controls in the block, and no JS (depends on 3) — DoD: T1-T8 pass; all
  pre-existing tests in `manage_assistant_test.go` and `manage_test.go` pass
  unchanged.
- [ ] 5. Prefix the card tier digest in `internal/web/assistants.html:145`
  with `Default tiers:` (independent) — DoD: T9 passes; existing
  `assistants_test.go` passes.
- [ ] 6. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
  `go test ./...` (depends on 4, 5) — DoD: all green; the diff touches only
  allowlisted files.
- [ ] 7. Open a PR (conventional title `fix(web): clarify configured assistant authority and state`)
  referencing #1300 and #1280 without closing #1280. The PR body includes the
  display matrix and a before/after text excerpt. Do not tag a release or
  deploy (depends on 6) — DoD: PR open, CI green, merge left to the operator
  (merge commit strategy).

## Tests

All tests are deterministic. They use `newManageAssistantFixture` +
`installDirect`, then set profile fields through the existing store test
helpers (or a direct `UPDATE agent_profiles` on the test DB, as other manage
tests do), or they call `assistantAuthorityOf` / execute the template with a
synthetic `assistantSectionView`. They use only the synthetic identities
already in the tests (Alice, `500100101`). No network and no Telegram.

- [ ] T1. Regression: with `mode=observe`, unpaused, listening and
  `IntentAllowlist="discovery,schedule"`, the rendered page does not contain
  `Replies on its own`. The `id="assistant-auto"` value starts with `none` and
  names observe mode, and `discovery` appears only inside
  `id="assistant-auto-configured"`. The test fails if the old row is restored.
- [ ] T2. Table-driven `assistantAuthorityOf` matrix: every row of the
  design.md matrix (off; unrecognized `"bogus"`; observe+paused;
  guarded+paused; guarded+not listening; observe+listening; guarded+listening
  non-fork with intents; guarded+listening non-fork with empty AutoIntents ->
  "none"; guarded+listening fork name `hr-recruiter~abc` -> AutoUnknown).
  Asserts State, AutoNow, ApprovalActive and the HoldReasons membership.
- [ ] T3. Paused and off states never list a configured intent under
  "Sends without your approval", never list hold reasons, and say replies are
  held back and not queued. The page never contains the word `allowed` inside
  the authority block in any matrix case.
- [ ] T4. Hold reasons: in observe, `HoldReasons` contains
  `policy.OwnerHoldReasons(policy.ReasonObserveMode)[0]`. In guarded it does
  not, and it contains the turn-budget, not-on-list, rate-limit, working-hours
  and hours-unreadable wording. Negative guard: no denial reason
  (`ReasonAutopilotPaused`, `ReasonInstallChanged`, kill switch, never intent)
  appears under `assistant-approval`.
- [ ] T5. Never: `IntentDenylist="salary"` renders `salary` under
  `id="assistant-never"` with "approval cannot release". The static platform
  note mentions the kill switch and the install revision.
- [ ] T6. Unavailable and empty data: a `LoadErr` view renders
  `assistant-unknown` and no `assistant-state`. Installed with `Settings == nil`
  renders "Configured authority is unavailable" and no `assistant-auto`.
  Not installed renders `assistant-none` and no authority block. Empty
  AutoIntents and NeverIntents render "none". `assistant-unverified` is always
  present when Settings is non-nil.
- [ ] T7. Escaping: a synthetic view with intent `<script>x</script>` in both
  AutoIntents and NeverIntents renders `&lt;script&gt;x&lt;/script&gt;` and
  contains no raw `<script` anywhere in the assistant section.
- [ ] T8. No-JS and preservation: the response has no `<script` element, and
  the CSP header equals the value before this change. The authority block
  (between `id="assistant-state"` and `id="assistant-unverified"`) contains no
  `<form`, `<input`, `<select>` or `<button`. Every existing form action and
  every `expected_revision` hidden field is still present.
  `assertNoAssistantLeak` passes. The existing ids `assistant-mode`,
  `assistant-paused` and `assistant-listening` keep their yes/no and mode
  values.
- [ ] T9. `/assistants` card tier digest contains `Default tiers:` before the
  tier names. The existing catalog, 503 and escaping tests still pass.

## Rollback

The change is presentation only, with no data, schema, API or flag changes.
Roll back by reverting the merge commit on main (`git revert -m 1 <merge>`)
and letting release-please cut the next patch release, or by deploying the
previous image tag (`0.139.1` or whichever preceded the release) with the
standard rollback. No data migration or cleanup is needed, and no stored state
depends on the new text.
