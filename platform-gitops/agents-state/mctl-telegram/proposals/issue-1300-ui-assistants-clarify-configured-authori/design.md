# Design: issue-1300-ui-assistants-clarify-configured-authori

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
  kill-switch or fork-promotion field.
- Effective authority lives only in `policy.Evaluate`
  (`internal/agent/policy/policy.go`):
  - mode `off` -> deny; an unrecognized mode -> deny (`:445-451`);
  - `IntentDenylist` match -> deny, which approval cannot release (`:517`);
  - `AutopilotPaused` -> deny `autopilot_paused` (`:503`), which queues an
    owner alert instead of an approval;
  - `observe`, or `guarded` on an unpromoted fork
    (`db.IsForkAssistant`, `internal/db/assistant_forks.go:44`) ->
    `RequireApproval` with `ReasonObserveMode` (`:573-576`);
  - turn budget, intent not on allowlist, rate limit, working hours, hours
    unreadable, protected field -> `RequireApproval` (`:577-603`);
  - owner-facing wording for these reasons is `policy.OwnerHoldReasons`
    (`:634-660`).
  `Evaluate` does not read `ListenerEnabled`. Listening controls which
  profiles the listener supervisor starts
  (`internal/agent/listener/supervisor.go:78`, `ListListenerEnabledProfiles`).
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

Deployed state checked:

- `mctl_get_service_status(team=labs, service=mctl-telegram)`: Argo CD Synced
  and Healthy, image tag `0.139.1`, host `tg.mctl.ai`. This matches the
  clone's `.release-please-manifest.json` (`0.139.1`).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  `AGENT_ENABLED: "true"` (`:332`), so the assistant section is mounted in
  production. `AGENT_KILL_SWITCH: "false"` (`:333`). The comments say
  production runs in observe mode and the worker runs off-cluster. That is
  exactly the state in which the current "Replies on its own" row misleads.
  The kill switch is env configuration that the web template does not see,
  which is why the design states it as "not verified here".
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  `AGENT_ENABLED: "true"`, tag `main-14ac95b` (the current main HEAD of the
  clone).
- Not checked: per-account `agent_profiles` rows (mode, paused, listening)
  in the production DB. They are not readable with the tools available here
  and do not affect the design.

## Proposed solution

Presentation-only change in two templates plus one pure helper. No handler,
route, service, store, policy or schema change.

### 1. Pure display helper (`internal/web/manage_assistant.go`)

Add an unexported view type and a pure function:

```go
type assistantAuthorityView struct {
    State, StateText string   // e.g. "Paused", "Replies are held back and not sent."
    AutoNow          []string // intents shown under "Sends without your approval"; nil -> none
    AutoNowText      string   // reason or conditional wording
    AutoUnknown      bool     // guarded fork: promotion not visible here
    AutoConfigured   []string // Settings.AutoIntents verbatim
    ApprovalActive   bool     // observe or guarded: approval queue applies
    HoldReasons      []string // policy.OwnerHoldReasons wording
    Never            []string // Settings.NeverIntents
}

func assistantAuthorityOf(assistant string, s *assistantinstall.Settings) *assistantAuthorityView
```

It returns nil for nil settings, and the template then prints "Configured
authority is unavailable". `buildAssistantSection` sets a new field
`Authority *assistantAuthorityView` from `cur.Assistant` and `v.Settings`. It
does no extra I/O.

Hold-reason text comes from `policy.OwnerHoldReasons(policy.Reason…)`, so the
page and the Telegram approval notices use the same words and cannot drift.
Only approval reasons are passed in. Denial reasons are never listed under
approval.

### 2. State / authority display matrix

Precedence for the primary state: off > unrecognized > paused > not listening
> observing > guarded. Here "fork" means `db.IsForkAssistant(assistant)`.

| Mode | Paused | Listening | Fork | State label | "Sends without your approval" | "Needs your approval" |
|---|---|---|---|---|---|---|
| off | any | any | any | Off — sends nothing | none — mode is off | held back, not queued |
| other/unknown string | any | any | any | Unrecognized mode — every reply refused | none — mode not recognized | held back, not queued |
| observe/guarded | yes | any | any | Paused — replies are held back and not sent | none — paused | held back, not queued |
| observe/guarded | no | no | any | Not listening — new messages are not picked up | none for new messages — listening is off | hold reasons (observe reason only if observe) |
| observe | no | yes | any | Observing — every reply waits for your approval | none — observe mode | every reply; hold reasons incl. observe |
| guarded | no | yes | yes | Guarded (private fork) | unknown — depends on fork promotion, not shown here | hold reasons |
| guarded | no | yes | no | Guarded | AutoIntents, "only when none of the holds below applies"; "none" if empty | every other reply; hold reasons (no observe) |

Rows rendered in every installed case (Settings non-nil):

- `Auto-send list (saved setting)` (`id="assistant-auto-configured"`):
  AutoIntents or "none", plus "used only in guarded mode while unpaused and
  listening".
- `Never sent` (`id="assistant-never"`): NeverIntents or "none", plus
  "approval cannot release these", plus the static platform-rules note.
- `Not verified here` (`id="assistant-unverified"`): "This section shows saved
  settings. It cannot confirm that a listener or worker is running, or whether
  the platform kill switch is on."
- The existing Paused/Listening rows stay, with ids and yes/no values
  unchanged, and their labels become "Paused (saved setting)" and "Listening
  (saved setting)".

The old row `Replies on its own` is removed. The new wording never contains
"allowed" for a configured intent.

### 3. Template (`manageAssistantSection`)

Replace lines `:445-446` with an `{{with $.Assistant.Authority}}` block of
`field-row` divs and plain text. It uses existing CSS classes (`field-row`,
`field-label`, `field-value`, `meta`), so it adds no CSS and no JS, and the
CSP is unchanged. The state is a text label (`id="assistant-state"`), not a
colour. Every value goes through `html/template` escaping. The block contains
no `<form>`, `<input>`, `<select>` or `<button>`.

### 4. Public catalog label (`internal/web/assistants.html:145`)

Prefix the card tier digest with `Default tiers:` so catalog defaults are not
read as account authority. The table and footnote are unchanged.

### File allowlist

- `internal/web/manage_assistant.go`
- `internal/web/manage_assistant_test.go`
- `internal/web/assistants.html`
- `internal/web/assistants_test.go`

Anything else, in particular `internal/assistantinstall/**`,
`internal/agent/**`, `internal/db/**`, `internal/mcp/**` and handlers, is out
of bounds. If the implementation finds it needs a new backend field (kill
switch, fork promotion, listener health), it stops and asks for a separate
decision.

## Alternatives

1. **Keep "Replies on its own" and add a footnote.** Rejected: the row still
   presents configured intents as autonomous behaviour in observe and paused
   states, which fails acceptance 1, and a footnote is easy to miss on mobile.
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
  - Copy drifts from policy behaviour. Mitigations: wording taken from
    `policy.OwnerHoldReasons`; table-driven tests pin the matrix; a regression
    test fails if `AutoIntents` appears as "sends without approval" in observe,
    paused or off states.
  - Overclaiming listener semantics. Mitigation: "new messages are not picked
    up" wording, plus an open question for review.
  - Escaping regressions. Mitigation: a test with a hostile intent name
    (`<script>x</script>`) asserting the escaped form and the absence of a raw
    `<script`.
- Rollout: ships with the normal release-please release, after operator
  approval and merge. No flags.
