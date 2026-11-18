# Tasks: issue-1300-ui-assistants-clarify-configured-authori

Status: proposed. Owner approval is required before any task below starts.
These tasks are a plan for later implementation, not authorized work.

File allowlist: `internal/web/manage_assistant.go`,
`internal/web/manage_assistant_test.go`, `internal/web/assistants.html`,
`internal/web/assistants_test.go`. Stop and ask for a separate decision if any
other file, a new backend field, API, policy, setting or grant, or a new
dependency seems necessary.

- [ ] 0. Drift check (not a new investigation): re-read the latest `policy.go`
  and confirm the verified facts in design.md "Verified source facts (hold
  reasons)" still hold. The static illustrative, nonexhaustive label list is
  the six exported `ReasonObserveMode`, `ReasonTurnBudget`,
  `ReasonIntentNotAllowed`, `ReasonRateLimit`, `ReasonWorkingHours` and
  `ReasonScheduleUnreadable`; `OwnerHoldReasons` takes a string. The
  protected-field reason is dynamic (unexported prefix/suffix plus the actual
  field key, which `Settings` does not supply) and is context-dependent, not
  resolved here. Invent no key, constant or fake action and read no extra
  data — DoD: the helper lists only those six labels; anything without
  source-supported static wording is omitted; no new backend API or import
  change.
- [ ] 1. Write the rendering tests first (T1-T10 below) against the current
  template, and confirm that T1 (regression) and the matrix cases fail on
  current main — DoD: `go test ./internal/web -run 'ManageAssistant|AssistantAuthority|Assistants'`
  shows the new tests failing for the documented reason ("Replies on its own"
  printing AutoIntents in observe/paused), and existing tests passing.
- [ ] 2. Add `assistantAuthorityView` and the pure `assistantAuthorityOf(assistant string, s *assistantinstall.Settings)`
  in `internal/web/manage_assistant.go`, implementing the design.md matrix.
  Display precedence: off > unrecognized > paused > not listening > observing >
  guarded (presentation only, not a policy contract). Fork detection uses
  `db.IsForkAssistant`. Hold-condition text comes from
  `policy.OwnerHoldReasons` with only approval categories (depends on 0, 1) —
  DoD: helper unit tests T2 and T10 pass; no I/O in the helper; no call to
  `policy.Evaluate`; `go vet` clean; no import cycle.
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
  controls in the block, no JS, and keep the page readable at mobile width
  (depends on 3) — DoD: T1-T8 and T10 pass; all pre-existing tests in
  `manage_assistant_test.go` and `manage_test.go` pass unchanged.
- [ ] 5. Prefix the card tier digest in `internal/web/assistants.html:145`
  with `Default tiers:` (independent) — DoD: T9 passes; existing
  `assistants_test.go` passes.
- [ ] 6. Run the restore-bug mutation check (T11), then `gofmt -l` on the Go
  files this change edits (`internal/web/manage_assistant.go`,
  `internal/web/manage_assistant_test.go`, `internal/web/assistants_test.go` if
  changed) and format only those files if listed. Do not run `go fmt ./...` or
  rewrite unrelated files. Then run `go vet ./...`, `golangci-lint run` and
  `go test ./...` (depends on 4, 5) — DoD: all green; the diff touches only
  allowlisted files.
- [ ] 7. Open a PR (conventional title `fix(web): clarify configured assistant authority and state`)
  referencing #1300 and #1280 without closing #1280. The PR body includes the
  display matrix and a before/after text excerpt. The PR is reviewed like any
  other source change. Do not tag a release or deploy; releases and deploys are
  separately governed and are not part of this task or its approval (depends
  on 6) — DoD: PR open, CI green, merge left to the operator.

## Tests

All tests are deterministic. They use `newManageAssistantFixture` +
`installDirect`, then set profile fields through the existing store test
helpers (or a direct `UPDATE agent_profiles` on the test DB, as other manage
tests do), or they call `assistantAuthorityOf` / execute the template with a
synthetic `assistantSectionView`. They use only the synthetic identities
already in the tests (Alice, `500100101`). No network and no Telegram.

Assertions about the new block are scoped to the authority block or to the
named row ids (`assistant-auto`, `assistant-auto-configured`,
`assistant-approval`, `assistant-never`, `assistant-unverified`), never to the
whole page. The page legitimately contains intent names and the word "allowed"
elsewhere (forms, option values, existing copy), so whole-page "appears only
once" or "never appears" checks are not used.

- [ ] T1. Regression: with `mode=observe`, unpaused, listening and
  `IntentAllowlist="discovery,schedule"`, the rendered page does not contain
  `Replies on its own`. Within the authority block, the `id="assistant-auto"`
  value starts with `None under saved settings` and names observe mode, and
  `discovery` does not appear in the `assistant-auto` row; it appears in the
  `assistant-auto-configured` row. Other parts of the page (forms) are not
  asserted on. The test fails if the old row or its logic is restored.
- [ ] T2. Table-driven `assistantAuthorityOf` matrix: every row of the
  design.md matrix (off; unrecognized `"bogus"`; observe+paused;
  guarded+paused; guarded+not listening; observe+listening; guarded+listening
  non-fork with intents; guarded+listening non-fork with empty AutoIntents ->
  "None under saved settings"; guarded+listening fork name `hr-recruiter~abc`
  -> AutoUnknown). Asserts State, SavedAuto, HoldShown and the hold-condition
  membership.
- [ ] T3. Paused, off and unrecognized states never list a configured intent in
  the `assistant-auto` row, never list hold conditions, and say replies are held
  back and not sent without stating that anything is queued. The authority
  block never contains the word `allowed` in any matrix case, and no row or
  label implies a verified effective permission (no "verified", "guaranteed" or
  "will send" wording outside the "Not verified here" note).
- [ ] T4. Hold conditions: the list is introduced as illustrative and does not
  claim the holds are active or exhaustive. In observe, the conditions contain
  `policy.OwnerHoldReasons(policy.ReasonObserveMode)[0]`. In guarded they do not
  contain it, and they contain the `OwnerHoldReasons` wording for the other
  five static labels (turn budget, not-on-list, rate limit, working hours,
  hours unreadable). The six-label list is illustrative and nonexhaustive.
  No protected-field label is asserted: that reason is dynamic and
  context-dependent, not resolved here.
  Negative guard: no denial reason (`ReasonAutopilotPaused`,
  `ReasonInstallChanged`, kill switch, never intent) appears under
  `assistant-approval`. The row makes no statement about approval-queue
  availability.
- [ ] T5. Never: `IntentDenylist="salary"` renders `salary` under
  `id="assistant-never"` with "approval cannot release". The static platform
  note mentions the kill switch and the install revision.
- [ ] T6. Unavailable, unknown and empty data: a `LoadErr` view renders
  `assistant-unknown` and no `assistant-state`. Installed with `Settings == nil`
  renders "Configured authority is unavailable" and no `assistant-auto`.
  Not installed renders `assistant-none` and no authority block. A guarded fork
  renders `unknown` (not "none" and not a list). Empty AutoIntents and
  NeverIntents render "none". `assistant-unverified` is always present when
  Settings is non-nil.
- [ ] T7. Escaping: a synthetic view with intent `<script>x</script>` in both
  AutoIntents and NeverIntents renders `&lt;script&gt;x&lt;/script&gt;` and
  contains no raw `<script` anywhere in the assistant section.
- [ ] T8. No-JS and preservation: the response has no `<script` element, and
  the CSP header equals the value before this change. The authority block
  (between `id="assistant-state"` and `id="assistant-unverified"`) contains no
  `<form`, `<input`, `<select>` or `<button`. Every existing form action, every
  `expected_revision` hidden field and the existing form option values are
  still present outside the block. `assertNoAssistantLeak` passes. The existing
  ids `assistant-mode`, `assistant-paused` and `assistant-listening` keep their
  yes/no and mode values and are labelled as saved settings.
- [ ] T9. `/assistants` card tier digest contains `Default tiers:` before the
  tier names. The existing catalog, 503 and escaping tests still pass.
- [ ] T10. Mixed-state rendering (display precedence off > unrecognized >
  paused > not listening > observing > guarded). Rendered through the template,
  each case shows exactly one primary label in `assistant-state` and the saved
  Paused and Listening rows still show every stored flag:
  off+paused+not listening -> Off; unrecognized+paused -> Unrecognized mode;
  observe+paused+not listening -> Paused; guarded+paused+not listening ->
  Paused; observe+unpaused+not listening -> Not listening; observe+unpaused+
  listening -> Observing; guarded+unpaused+listening -> Guarded. Also asserts
  that the "Not listening" text says configured intake and does not claim that
  nothing can be sent, and that no mixed case lists a saved auto intent in the
  `assistant-auto` row except guarded non-fork.
- [ ] T11. Restore-bug mutation check (temporary, never committed). Commit the
  good tests first. Run each mutation in isolation, applied with Edit:
  (a) template-only: restore the old unconditional auto-intent row (printing
  AutoIntents) in the template. The scoped rendering regression T1 must fail
  on it. T2 (pure helper) is not expected to fail on a template-only edit.
  (b) helper-only: change the helper so observe mode lists AutoIntents. The
  relevant observe helper/matrix assertion in T2 must fail, plus the scoped
  rendering assertion in T1 or T10 only where it asserts that behaviour.
  T3 (paused/off/unrecognized) is not expected to fail on an observe-only
  mutation.
  For each mutation: confirm the failure is the intended assertion, not a
  setup, call-count or compile artifact; then `git restore` the file, confirm a
  clean `git status`, and confirm the tests are green again before the next
  one. No claim is made that every named test fails on every mutation.

## Rollback

The change is presentation only, with no data, schema, API or flag changes.
Roll back by reverting the source change through a reviewed PR (a revert of the
implementation commit or PR). No data migration or cleanup is needed, and no
stored state depends on the new text. Releases, deploys and image changes are
separately governed; they are not tasks here and are not authorized by this
proposal or its approval.
