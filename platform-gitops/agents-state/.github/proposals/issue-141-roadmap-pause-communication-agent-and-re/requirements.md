# Roadmap cleanup: pause the Communication Agent epic and retire the OpenClaw-only Client Lifecycle branch

## Context

Two owner portfolio decisions have to be encoded in the declarative roadmap control
plane in `mctlhq/.github`. First, the entire Communication Agent workstream
(`roadmap/epics/communication-agent.yaml`, root `mctlhq/mctl-telegram#518`) is paused
until an explicit owner unpause: it must stop being offered as executable work without
being recorded as delivered. Second, `admins/openclaw` is being decommissioned, so the
OpenClaw-only branch of the Client Lifecycle epic
(`roadmap/epics/client-lifecycle.yaml`, root `mctlhq/.github#22`) — `mctl-gitops#1182`
and `mctl-telegram#400` — must be reassessed, while everything in that epic that is
useful independently of OpenClaw is preserved.

This matters because the roadmap manifests are the authored desired state that
`roadmap/scripts/ready.py`, `health.py`, `plan.py` and `apply.py` derive from, and that
mctl-api's wave planner selects work from. Encoding a pause the wrong way — by making
required items optional, by closing issues as completed, or by inventing an
undeclared field — would corrupt the completion and readiness axes that every other
epic is measured on. Encoding it the right way turns out to be a one-line change, and
the investigation below shows exactly where that one line is honoured, where it is not
yet honoured, and what the second decision costs in reconciliation.

## User stories

- AS the portfolio owner I WANT the Communication Agent epic to stop appearing in
  wave-selectable ready work SO THAT no automated pipeline starts #334, #347, #350 or
  the Temporal approval children while the workstream is paused.
- AS the portfolio owner I WANT the pause recorded without any item being completed,
  closed or demoted to optional SO THAT the C1 evidence and the real remaining scope
  survive the pause intact.
- AS the portfolio owner I WANT a single-line unpause SO THAT resuming the workstream
  needs no compensating edits and cannot leave residue behind.
- AS the portfolio owner I WANT the OpenClaw-only Client Lifecycle branch retired
  rather than left blocked forever SO THAT `client-lifecycle` completion is not held
  hostage by work that will never be done.
- AS the portfolio owner I WANT the already-shipped least-privilege `admin:users`
  lookup capability and all non-OpenClaw client-lifecycle work preserved SO THAT
  retiring a deployment branch does not discard delivered product capability.
- AS a wave planner (mctl-api) I WANT `mctl-telegram#679` to carry no OpenClaw-only
  dependency SO THAT its readiness reflects only work that is still planned.
- AS a reviewer I WANT the exact before/after required/ready/blocked counts and the
  exact GitHub mutations SO THAT approving this proposal is the same decision as
  approving what will be written.
- AS a reviewer I WANT any required item whose `complete` status rests on insufficient
  acceptance evidence named explicitly SO THAT a false completion does not silently
  unblock downstream work.

## Acceptance criteria (EARS)

### Communication Agent pause

- WHEN the Communication Agent pause is encoded THE SYSTEM SHALL change exactly one
  line, `spec.lifecycle` in `roadmap/epics/communication-agent.yaml`, from `active` to
  `paused`, using the value already declared in
  `roadmap/schemas/epic-definition.schema.json` (`spec.lifecycle` enum, line 37) and
  already in use by `roadmap/epics/edge-ai-android.yaml`.
- WHILE the epic is paused THE SYSTEM SHALL leave every work item's `required` flag,
  `dependsOn` edge, `parent` edge and `issue` binding byte-identical to today.
- WHILE the epic is paused THE SYSTEM SHALL report `completion.status: incomplete`
  with `blocking: ["c2-safety-gate", "quota-domain"]`, because `completion.py` derives
  completion from observed GitHub state and never reads `spec.lifecycle`.
- WHILE the epic is paused THE SYSTEM SHALL NOT close, complete, reopen or relabel
  `mctl-telegram#518`, `#334`, `#347`, `#339`, `#340`, `#341` or `#350`.
- WHEN `publish.py` next runs THE SYSTEM SHALL copy `lifecycle: paused` verbatim into
  `publication.json` `epics[].lifecycle` via `publish._epic_identity`.
- WHEN mctl-api is asked for ready work with no epic named THE SYSTEM SHALL omit the
  Communication Agent epic, as it already omits `edge-ai-android`.
- IF an operator attempts `mctl_plan_epic_wave` on the paused epic THEN THE SYSTEM
  SHALL refuse with `epic_paused` and no override.
- THE SYSTEM SHALL state plainly, in the design, that `ready.py` and `health.py` are
  lifecycle-blind: the published `ready-set.json` still lists four `ready` items for
  the paused epic, and the only gate today is the mctl-api consumer that joins
  `publication.json`.
- WHEN the smallest explicit control-plane extension is proposed THE SYSTEM SHALL
  propose adding an optional `lifecycle` property to `$defs.epic` in
  `roadmap/schemas/roadmap-ready-set.schema.json` (and, for symmetry,
  `roadmap-health.schema.json`), populated from the same validated manifest bytes the
  way `publish._epic_identity` already does, and SHALL mark it a hardening rather than
  a prerequisite.
- THE SYSTEM SHALL NOT invent a `spec.status` field, SHALL NOT set any work item to
  `required: false` to simulate a pause, and SHALL NOT use `closed:not_planned` to
  simulate a pause.

### Client Lifecycle branch retirement

- WHEN `mctl-gitops#1182` is classified THE SYSTEM SHALL classify it **retire as not
  planned**, because every one of its five scope steps is `admins/openclaw`
  deployment work that the owner has prohibited.
- WHEN `mctl-telegram#400` is classified THE SYSTEM SHALL classify it **retire as not
  planned**, because its own "Status 2026-09-11" section records that the in-repository
  half is delivered (#511, #575) and that only the deployment half tracked by #1182
  remains.
- WHEN a work item is retired THE SYSTEM SHALL remove it from the manifest as well as
  close its issue as not planned, because `completion.py` maps `closed_not_planned` to
  `incomplete` and `ready.py` maps an item whose own issue is `closed_not_planned` to
  `blocked`; a required item left in the manifest and closed not-planned would make the
  epic permanently blocked and permanently incomplete.
- THE SYSTEM SHALL preserve the shipped `admin:users` lookup tier
  (`TG_LOGIN_LOOKUP_ADMINS`, `list_telegram_identities`, `get_user_audit_log` from
  mctl-telegram#511 and #575) by not touching any code and by not closing those issues.
- THE SYSTEM SHALL preserve work items `client-reachability-preferences` (#438),
  `login-bot-update-receiver` (#619), `safe-broadcast` (#439), `product-update-feed`
  (#440) and `onboarding-integration` (#679) unchanged except for the `dependsOn`
  edit named below.
- WHEN the new dependency set for `onboarding-integration` (#679) is authored THE
  SYSTEM SHALL set `dependsOn: [safe-broadcast, product-update-feed]`, removing
  `operator-identity-lookup` and retaining no OpenClaw-only dependency.
- IF the `identity` phase has no remaining work items THEN THE SYSTEM SHALL remove the
  phase, noting that `validate.py` permits an empty phase (it checks only duplicate
  phase ids and unknown phase references) so removal is tidiness, not a fix.

### Evidence quality of #440

- WHEN `product-update-feed` (#440) is assessed as a dependency THE SYSTEM SHALL NOT
  rely on its observed `closed` / `COMPLETED` state, because #440 was closed at
  2026-09-26T06:52:09Z by release-please pull request `mctl-telegram#682`
  ("chore(main): release 0.69.0", author `app/mctl-agents`), under five hours after
  the owner's own acceptance matrix comment of 2026-09-26T01:56:17Z concluded
  "**Not closing #440:** 7 is missing, 6 and 9 lack end-to-end evidence, and 1 needs
  its deviation confirmed".
- THE SYSTEM SHALL record that acceptance criterion 7 of #440 is explicitly moved to
  `mctl-telegram#683`, which is OPEN.
- THE SYSTEM SHALL record that retiring `operator-identity-lookup` makes
  `onboarding-integration` (#679) the only remaining incomplete required item and turns
  it `ready`, so #440's false `complete` would be the sole thing standing between a
  wave planner and #679.
- THE SYSTEM SHALL recommend reopening `mctl-telegram#440` as the primary remedy, and
  SHALL offer binding a new required work item to `mctl-telegram#683` as the
  alternative if the owner ratifies the partial delivery.

### Reconciliation and sequencing

- IF both Client Lifecycle work items are removed in a single manifest change THEN
  THE SYSTEM SHALL expect `plan.py` to refuse the whole manifest with
  `RemoveDependency targets an identity this manifest does not author:
  mctlhq/mctl-telegram#400` and exit 3, writing nothing.
- WHEN the change is sequenced THE SYSTEM SHALL split it into two pull requests: the
  first editing only `onboarding-integration.dependsOn` (yielding exactly one governed
  `RemoveDependency` operation, `opId f955af581e0687da`), the second removing the two
  work items and the `identity` phase (yielding zero operations and two
  `HierarchyUnexpectedChild` notes).
- WHILE the first pull request's governed apply has not landed THE SYSTEM SHALL NOT
  merge the second pull request.
- THE SYSTEM SHALL list the sub-issue detachments of `mctl-gitops#1182` and
  `mctl-telegram#400` from `mctlhq/.github#22` as manual operator actions outside the
  governed apply path, because `plan.py` deliberately never removes a child the
  manifest does not own.
- WHEN either manifest is edited THE SYSTEM SHALL keep `python roadmap/scripts/
  validate.py roadmap/epics` passing for the entire corpus.
- THE SYSTEM SHALL require a fresh publication (`publication_request.py`, or the push
  trigger on `roadmap/**`) before any wave is planned, because
  `ROADMAP_WAVE_MAX_AGE` defaults to 30 minutes.

### Rollback / unpause

- WHEN the owner unpauses the Communication Agent THE SYSTEM SHALL require only
  `spec.lifecycle: paused` to be set back to `active` in one line, with no compensating
  edit to any work item, dependency or issue.
- WHEN the unpause is merged THE SYSTEM SHALL restore the epic to exactly its
  pre-pause wave-selectable state, because the pause changed no relation and therefore
  the evaluator's ready set never changed.

### Authorization boundary

- THE SYSTEM SHALL stop at human approval: no manifest pull request, no governed
  apply, no issue closure, no reopen, no label change and no code implementation are
  performed by this investigation.

## Out of scope

- Fixing `mctl-gitops#571` (the dead `admins/openclaw` OAuth refresh sidecar).
- Creating Telegram accounts, Vault entries or any credential.
- Any change to Communication Agent runtime code or configuration.
- Rewriting product strategy outside `communication-agent` and `client-lifecycle`.
- Closing, reopening or relabelling `#1182`, `#400` or `#679` during investigation.
- Any change to the other fifteen epic manifests, including the other epics whose
  issues were closed by release-please pull request `mctl-telegram#682`.
- Implementing the optional `lifecycle` addition to the ready-set/health schemas; it
  is proposed and scoped here, not built.
- Adding `spec.status`, `pausedAt`, `pausedBy` or any other new EpicDefinition field.

## Open questions

- Does `mctl_get_ready_work_items` filter a **named** paused epic, or only filter when
  no epic is given? The tool contract documents the filter only for the no-epic case.
  Verification is task T2; if a named paused epic still returns ready items, that is
  acceptable for a status read but the answer should carry `lifecycle: paused`.
  Proceeding on the assumption that the wave-planning path (`mctl_plan_epic_wave`,
  which documents an `epic_paused` refusal) is the one that matters.
- Does the DevLoop `issue-poll` schedule (`*/15 * * * *`, ADR-005 "Temporal Schedule →
  DevLoopWorkflow") select issues independently of roadmap lifecycle? A code search of
  `mctlhq/mctl-agents` for roadmap lifecycle awareness returned nothing. If it selects
  by GitHub label or state, `lifecycle: paused` does not gate it and the pause must be
  backed by a GitHub-side hold on #334, #347, #339, #340, #341 and #350. Proceeding
  with the manifest pause as the primary control and the GitHub hold as a conditional
  follow-up (task 9).
- #440: reopen it (recommended) or ratify the partial delivery and bind a new required
  work item to #683? Owner decision. Proceeding with reopen as the primary recommendation
  because it is the smaller change and matches the owner's own written intent.
- Should a bounded audit check whether release-please pull request #682 closed other
  roadmap-required issues? Its changelog references `issue-443`, which belongs to the
  `surfaces` epic. Flagged only; deliberately not proposed, to respect the no-broad-
  portfolio-cleanup constraint.
- The issue records no unpause trigger or review date for the Communication Agent
  beyond "an explicit owner unpause". Proceeding without encoding one, since the
  manifest has no field for it and inventing one is out of scope.
- Should `communication-agent` also adopt `spec.github.project.priority: PARK`, as
  `edge-ai-android` does? That field is free-form (`github.project` accepts additional
  properties). Proposed as optional convention alignment, not required.
