# Design: issue-1300-ui-assistants-clarify-configured-authori

Status: proposed. Owner approval is required before any implementation.

## Current state

Assistant management UI (server-rendered, no JS):

- `internal/web/manage_assistant.go` builds `assistantSectionView`
  (`:70-94`) in `buildAssistantSection` (`:115-154`) from
  `assistantinstall.Service.Current` (an `Installed`: assistant name, version,
  install revision) and `Service.CurrentSettings` (`*assistantinstall.Settings`).
  The template constant `manageAssistantSection` (`:428-520`) renders it inside
  the manage page (`/telegram/connect/manage#assistant`). The template is
  parsed by `newManageTemplate` (`internal/web/manage.go:547`) with
  `html/template`, so output is contextually escaped.
- Relevant rows today: Mode (`:438`), Paused yes/no (`:441`), Listening
  yes/no (`:442`), **"Replies on its own"** = `Settings.AutoIntents` or "none"
  (`:445`), "Never" = `Settings.NeverIntents` (`:446`). The "Replies on its
  own" row ignores Mode and Paused, so `observe` + `AutoIntents=[discovery]`
  renders "Replies on its own: discovery". That is the misleading presentation
  the issue targets (spike §5.4: "prints the intent names even in observe
  mode, where nothing is auto-sent").
- `assistantinstall.Settings` (`internal/assistantinstall/service.go:782-800`)
  is built by `SettingsOf` (`:803-814`) from `db.AgentProfile`:
  `Mode`, `Paused` (= `AutopilotPaused`), `Listening` (= `ListenerEnabled`),
  `AutoIntents` (= `IntentAllowlist` csv), `NeverIntents` (= `IntentDenylist`
  csv), limits, working hours and audience. It has no live runtime, listener,
  kill-switch or fork-promotion field. Everything in it is a saved setting.
- Reply policy lives in `policy.Evaluate` (`internal/agent/policy/policy.go`).
  Source-derived notes (line references from the earlier source review; the
  hold-reason facts are verified, see "Verified source facts (hold reasons)"):
  - mode `off` -> deny; an unrecognized mode -> deny (`:445-451`);
  - `IntentDenylist` match -> deny, which approval cannot release (`:517`);
  - `AutopilotPaused` -> deny `autopilot_paused` (`:503`);
  - `observe`, or `guarded` on an unpromoted fork
    (`db.IsForkAssistant`, `internal/db/assistant_forks.go:44`) ->
    `RequireApproval` with `ReasonObserveMode` (`:573-576`);
  - turn budget, intent not on allowlist, rate limit, working hours, hours
    unreadable and protected-field handling -> `RequireApproval`
    (`:577-603`);
  - owner-facing wording for approval reasons is `policy.OwnerHoldReasons`
    (`:634-660`).
  These describe reply policy only. They are not a statement about every
  owner-facing action kind (alerts, notices, approvals), and the page does not
  claim they are.
  `Evaluate` does not read `ListenerEnabled`. Listening controls which
  profiles the listener supervisor starts
  (`internal/agent/listener/supervisor.go:78`, `ListListenerEnabledProfiles`).
  Saved `listening=false` therefore describes configured intake, not proof that
  no queued action can ever send.
- Mode semantics are documented at `internal/db/agent_domain.go:29-31`
  (observe: never auto-send; guarded: allowlisted intents may auto-send; off:
  deny everything).
- Public catalog `/assistants` (`internal/web/assistants.go`,
  `internal/web/assistants.html`): read-only catalog entries. The card tier
  digest (`assistants.html:145`) prints e.g. "auto: discovery" for the
  catalog's *default* tiers. The detail table already says "Default tier"
  (`:206`), and the footnote (`:214`) already explains observe and guarded.
- Existing tests: `internal/web/manage_assistant_test.go` (fixture
  `newManageAssistantFixture`, `installDirect`, `get`,
  `assertNoAssistantLeak`; asserts ids `assistant-mode`, `assistant-paused`,
  `assistant-listening`), `internal/web/assistants_test.go`.
- `internal/web` already imports `internal/db` and `internal/auth`.
  `internal/agent/policy` depends only on internal packages that do not import
  `internal/web` (checked with `go list -deps`), so importing it adds no cycle
  and no new module.
- Research grounding: `docs/spikes/assistant-builder-ui-reference.md` §4.2
  (configured is not effective; "must never say X is allowed") and §9.1 (the
  smallest slice, provisional files `manage_assistant.go` and its test).
- Ownership: #1002 (catalog epic, open), #1022 (assistant pages, closed),
  #1026 (governed delegation and authority UX, open). Open PRs checked
  (`gh pr list`, 2026-11-17): #1293, #1279, #1278 (policy denial-code
  persistence; does not touch `internal/web`), #1258 and dependabot bumps.
  No open PR edits `manage_assistant.go` or `assistants.html`.

### Deployment evidence, kept in separate categories

These are provenance notes from the earlier research. They do not change the
design, and none of them proves per-account behaviour.

- **Observed (a point-in-time read, 2026-11-17):**
  `mctl_get_service_status(team=labs, service=mctl-telegram)` reported the Argo
  CD application Synced and Healthy, image tag `0.139.1`, host `tg.mctl.ai`.
  The tag matched the source clone's `.release-please-manifest.json`
  (`0.139.1`). This is the only deployment health observation. It says the Argo
  application was healthy, not that any assistant worker or listener was.
- **Desired GitOps configuration (flags in the repo, not observed runtime):**
  `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` sets
  `AGENT_ENABLED: "true"` (`:332`) and `AGENT_KILL_SWITCH: "false"` (`:333`).
  `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` sets
  `AGENT_ENABLED: "true"`, tag `main-14ac95b` (the main HEAD of the clone at the
  time). These are desired values; they were not confirmed against the running
  pods.
- **Comments in GitOps values (claims, not evidence):** comments in that file
  say production runs in observe mode and that the worker runs off-cluster. A
  comment does not prove that any production account is in `observe` mode, that
  a worker is running off-cluster, or that a listener is healthy. The design
  does not rely on these comments.
- **Unknown:** per-account `agent_profiles` rows (mode, paused, listening) in
  the production DB, worker or listener state, fork promotion and the effective
  kill-switch value. They were not readable with the tools available and do not
  affect the design. The kill switch is env configuration the web template does
  not see, which is why the page states it as "not verified here".

### Verified source facts (hold reasons)

The orchestrator read `policy.go` on mctl-telegram `main` (read-only GitHub
connector, 2026-11-18); this proposal makes no claim of its own checkout access
or live observation. The line references above remain from earlier review.

- The static illustrative label list is the six existing exported constants
  `ReasonObserveMode` (observe only), `ReasonTurnBudget`,
  `ReasonIntentNotAllowed`, `ReasonRateLimit`, `ReasonWorkingHours` and
  `ReasonScheduleUnreadable`. The list is nonexhaustive.
- `OwnerHoldReasons` takes a string (stored reasons joined by "; "), not
  variadic constants.
- The protected-field reason is dynamic: it uses the UNEXPORTED
  `protectedFieldReasonPrefix` / `protectedFieldReasonSuffix` and the actual
  field key. `Settings` supplies no per-action field key, so the page lists no
  protected-field label; that condition is context-dependent and not resolved
  here. No key, constant or fake action is invented, and no extra data is read.
- No new backend API or import change follows from this. Re-reading the latest
  source before implementation is a drift check only.

## Proposed solution

Presentation-only change in two templates plus one pure helper. No handler,
route, service, store, policy or schema change. No second policy evaluator and
no live reads.

### 1. Pure display helper (`internal/web/manage_assistant.go`)

Add an unexported view type and a pure function:

```go
type assistantAuthorityView struct {
    State, StateText string   // e.g. "Paused", "Per saved settings, replies are held back and not sent."
    SavedAuto        []string // saved auto-send intents shown in the conditional row; nil -> "None under saved settings"
    SavedAutoText    string   // reason or conditional wording, always names the unverified runtime
    AutoUnknown      bool     // guarded fork: promotion not visible here
    AutoConfigured   []string // Settings.AutoIntents verbatim
    HoldShown        bool     // observe or guarded, unpaused: show illustrative hold conditions
    HoldConditions   []string // illustrative policy.OwnerHoldReasons wording
    Never            []string // Settings.NeverIntents
}

func assistantAuthorityOf(assistant string, s *assistantinstall.Settings) *assistantAuthorityView
```

It returns nil for nil settings, and the template then prints "Configured
authority is unavailable". `buildAssistantSection` sets a new field
`Authority *assistantAuthorityView` from `cur.Assistant` and `v.Settings`. It
does no extra I/O. The helper only maps saved settings to text. It never calls
`policy.Evaluate`.

Field names deliberately avoid "now", "effective" and "allowed". Nothing in the
view type or the rendered labels claims a verified effective permission.

Hold-condition text comes from calling `policy.OwnerHoldReasons(<constant>)`
once per constant (it takes a string), so the page and the Telegram approval
notices use the same words and cannot drift. Only the six static labels in
"Verified source facts (hold reasons)" are passed in; the dynamic
protected-field reason is not listed. Denial reasons are never listed under
approval. The list is illustrative: it is introduced as
"Conditions that can hold a reply (illustrative, not a current decision)". It is
not an exhaustive current decision and does not declare that every hold is
active.

### 2. State / authority display matrix

Display precedence for the primary label: **off > unrecognized > paused > not
listening > observing > guarded.** This is presentation precedence, not a policy
contract. Here "fork" means `db.IsForkAssistant(assistant)`. All entries are
statements about saved settings and reply policy, not verified behaviour.

| Mode | Paused | Listening | Fork | Display label | "Configured to send without approval (saved setting)" | "Needs your approval" |
|---|---|---|---|---|---|---|
| off | any | any | any | Off — per saved settings, replies are not sent | None under saved settings — mode is off | replies held back and not sent; whether anything is queued is not shown |
| other/unknown string | any | any | any | Unrecognized mode — reply policy refuses replies | None under saved settings — mode not recognized | same as above |
| observe/guarded | yes | any | any | Paused — per saved settings, replies are held back and not sent | None under saved settings — paused | same as above |
| observe/guarded | no | no | any | Not listening — listening is off in saved settings; new messages are not configured to be picked up | None under saved settings — listening is off (configured intake, not proof that no queued action can send) | illustrative hold conditions for the saved mode (observe reason only if observe) |
| observe | no | yes | any | Observing — every reply waits for your approval | None under saved settings — observe mode | every reply; illustrative hold conditions incl. observe |
| guarded | no | yes | yes | Guarded (private fork) | **unknown** — depends on fork promotion, not shown here | illustrative hold conditions |
| guarded | no | yes | no | Guarded | AutoIntents with "saved setting; applies only in guarded mode, unpaused, listening, and when no hold below applies; effective result not verified here"; "None under saved settings" if empty | every other reply; illustrative hold conditions (no observe reason) |

Three kinds of cell are used deliberately:

- known configured state: "None under saved settings" or the saved list, with
  the condition;
- unavailable data: handled before the matrix (see below);
- unobservable effective authority: "unknown" (guarded fork) and the
  "Not verified here" note.

The "none" wording is never used as a blanket. It means "saved settings
configure no auto-send for this state", and always names the reason.

Rows rendered in every installed case (Settings non-nil):

- `Auto-send list (saved setting)` (`id="assistant-auto-configured"`):
  AutoIntents or "none", plus "used only in guarded mode while unpaused and
  listening".
- `Never sent (saved setting)` (`id="assistant-never"`): NeverIntents or
  "none", plus "approval cannot release these", plus the static platform-rules
  note.
- `Not verified here` (`id="assistant-unverified"`): "This section shows saved
  settings. It cannot confirm effective permission, that a listener or worker is
  running, fork promotion, or whether the platform kill switch is on."
- The existing Paused/Listening rows stay, with ids and yes/no values
  unchanged, and their labels become "Paused (saved setting)" and "Listening
  (saved setting)".

Observe, paused and off statements are scoped to replies, which is the action
reply policy governs. The copy does not say these states stop alerts, notices or
approvals. The page also does not infer approval-queue availability from the
listening setting: it says "approval" only as the saved-mode meaning of a hold,
and says nothing about whether an approval can be delivered or read.

The old row `Replies on its own` is removed. The new wording never contains
"allowed" for a configured intent.

Unavailable data is handled before the matrix: `LoadErr` -> existing
`assistant-unknown` message and no authority block; install present with
`Settings == nil` -> "Configured authority is unavailable", no label, no
authority implied; not installed -> existing `assistant-none`.

### 3. Template (`manageAssistantSection`)

Replace lines `:445-446` with an `{{with $.Assistant.Authority}}` block of
`field-row` divs and plain text. It uses existing CSS classes (`field-row`,
`field-label`, `field-value`, `meta`), so it adds no CSS and no JS, and the
CSP is unchanged. Existing classes keep the block readable at mobile width (no
fixed-width table). The label is text (`id="assistant-state"`), not a colour.
Every value goes through `html/template` escaping. The block contains no
`<form>`, `<input>`, `<select>` or `<button>`. Existing forms, their
`expected_revision` fields and option values are untouched.

### 4. Public catalog label (`internal/web/assistants.html:145`)

Prefix the card tier digest with `Default tiers:` so catalog defaults are not
read as account authority. The table and footnote are unchanged.

### File allowlist (implementation, after owner approval)

- `internal/web/manage_assistant.go`
- `internal/web/manage_assistant_test.go`
- `internal/web/assistants.html`
- `internal/web/assistants_test.go`

Anything else, in particular `internal/assistantinstall/**`,
`internal/agent/**`, `internal/db/**`, `internal/mcp/**` and handlers, is out
of bounds. No new backend fields, API, policy, settings or grants. If the
implementation finds it needs a new backend field (kill switch, fork promotion,
listener health), it stops and asks for a separate decision.

## Alternatives

1. **Keep "Replies on its own" and add a footnote.** Rejected: the row still
   presents configured intents as autonomous behaviour in observe and paused
   states, and a footnote is easy to miss on mobile.
2. **Compute effective authority by calling `policy.Evaluate` with a
   synthetic action per intent.** Rejected: `Evaluate` needs conversation, peer,
   revision and timing inputs that the page does not have. Faking them would
   produce answers that look verified but are not, and it turns the copy into a
   second authority engine (spike §9.1 rules this out).
3. **Add a live status read (kill switch, listener/worker heartbeat, fork
   promotion) to `assistantinstall.Settings`.** Rejected for this slice: it
   needs a new backend field or API, which the issue says must stop for a
   separate decision. The page states "not verified here" or "unknown" instead.
4. **Hard-code the hold-reason wording in the template.** Rejected in favour of
   `policy.OwnerHoldReasons`, so the approval-notice wording and the page share
   one source.

## Platform impact

- Migrations: none. Backward compatibility: no API, JSON, MCP tool or form
  field changes. Only visible text changes on `/telegram/connect/manage` and
  one label on `/assistants`. Existing element ids are kept, and the only
  removed text is the "Replies on its own" label.
- Resources: no extra I/O per request (the helper works on data already
  loaded). The only extra work is a little template text.
- Dependencies: no new modules. One new intra-repo import (`internal/web` ->
  `internal/agent/policy`), checked to be acyclic.
- Risks and mitigations:
  - Copy drifts from policy behaviour or overclaims. Mitigations: wording taken
    from `policy.OwnerHoldReasons`; every config-derived row is labelled as a
    saved setting with conditions and a separate unverified note; table-driven
    tests pin the matrix including mixed states; a regression test fails if
    `AutoIntents` appears in the conditional auto-send row in observe, paused,
    off or unrecognized states.
  - Overclaiming listener semantics. Mitigation: "configured intake" wording
    and an open question for review.
  - Hold list read as a current decision. Mitigation: "illustrative" lead-in
    and a test that the lead-in is present and no "active" wording is used.
  - Escaping regressions. Mitigation: a test with a hostile intent name
    (`<script>x</script>`) asserting the escaped form and the absence of a raw
    `<script`.
- Rollout: after owner approval and review, the change lands as a normal PR.
  Releases and deploys are separately governed and are not part of this
  proposal or its approval. No flags.
