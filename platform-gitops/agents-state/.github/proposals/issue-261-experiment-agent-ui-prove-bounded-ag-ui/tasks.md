# Tasks: issue-261-experiment-agent-ui-prove-bounded-ag-ui

- [ ] 1. Add `roadmap/spikes/agent-ui-ag-ui-phase-b.yaml`: SpikeDefinition binding `mctlhq/.github#261`, outcomes `PROMOTE_AG_UI_ADAPTER` / `KEEP_LIMITED_OPERATOR_ADAPTER` / `STOP_AG_UI_EXPERIMENT`, `lifecycle: active`, `timebox.decisionBy: "2026-12-15"`, `execution.devloop: true`, `evidence.report: docs/spikes/agent-ui-ag-ui-phase-b.md`, no `decision`, and a header comment referencing #258's verdict. DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes, and `python3 -m unittest discover -s roadmap/tests` stays green.
- [ ] 2. Scaffold `docs/spikes/agent-ui-ag-ui-phase-b/` with `go.mod` (`module mctl.ai/spikes/aguiphaseb`, `go 1.22`, no `go.sum`) and a `README.md` (NON-NORMATIVE banner, run commands, layout, `[REF]` meaning). DoD: `go vet ./...` succeeds on the empty package.
- [ ] 3. (depends on 2) `model/events.go` and `model/records.go`: closed adopted-subset enum with strings copied from `@ag-ui/core@1.0.3`, event, Interrupt and ResumeEntry structs, canonical record types, the `Store` interface, and a JSON fixture loader. Add `fixtures/` with one bounded DevLoop run (stages, one recorded tool invocation, an `aar_`, a human-input request, usage with three cost fields), two tenants and three actors (human admin, other-tenant human, service credential). DoD: fixtures load, and the types compile with no third-party imports.
- [ ] 4. (depends on 3) `model/projector.go`: deterministic `Project` with `<we_>:<seq>` ids, events only from records, the closed and capped `mctl.*` CUSTOM refs, usage costs kept separate, TOOL_CALL ARGS/RESULT as digest/ref with the capability id, and the RUN_FINISHED `interrupt` outcome for a pending `aar_` or human-input. DoD: identical byte output across repeated runs, and no forbidden event type is reachable.
- [ ] 5. (depends on 4) `model/sse.go`: SSE encoder, `Last-Event-ID` replay from the store, snapshot fallback (unknown, malformed or expired id, count cap, byte cap), and slow-consumer drop on a simulated clock. The adapter keeps no event buffer. DoD: a reconnect at any id yields a gap-free, duplicate-free continuation.
- [ ] 6. (depends on 3) `model/resume.go`: the Adapter Resume/Cancel forwarder (strict closed-schema decode, authorization before lookup, known `interruptId`) and the `CanonicalHandlers` interface. Add a fake handler with the existing mctl-api semantics (digest/intent match, single-use consume, human-admin only, no self-decision, service credential refused, abandon records its terminal result) and a call log. DoD: the adapter has no decision branch, and every grant or refusal of substance originates in the handler.
- [ ] 7. (depends on 4,5,6) `model_test.go`: `TestRunLifecycleProjection`, `TestStageSteps`, `TestUsageRefOnly`, `TestInterruptFromApproval`, `TestResumeForwards`, `TestResumeStaleDigest`, `TestResumeReplay`, `TestResumeWrongActorTenant`, `TestInjectedEventRefused`, `TestLastEventIDReplay`, `TestCancelRecordedTerminal`, `TestToolIdentityNoGrant`, `TestBoundedReplaySnapshot`, `TestSlowConsumerDropped`, `TestAdapterRemovable`, `TestClosedSubset`, `TestMctlCustomClosed`. Add `bench_test.go` (per-event projection and encode cost, allocations, time-to-first-event). DoD: `go vet ./... && go test ./...` passes offline.
- [ ] 8. (depends on 7) CI: in `.github/workflows/workflow-tests.yml`, add `docs/spikes/agent-ui-ag-ui-phase-b/**` to the pull_request and push path lists, add a `setup-go` step with `go-version-file: docs/spikes/agent-ui-ag-ui-phase-b/go.mod`, and add a step "AG-UI Phase B reference model (mctlhq/.github#261)" running `go vet ./... && go test ./...` in that directory. DoD: the workflow file still parses, and the new step mirrors the G0 step.
- [ ] 9. (depends on 7) Write `docs/spikes/agent-ui-ag-ui-phase-b.md`: non-claims and tags (`[REF]` added), pins, the normative S1/S2/S3 contract (routes, auth, version header, id scheme, bounds 512 events / 256 KiB / 24 h / 5 s, closed resume schema, refusal table, `mctl.*` field list justified by Phase A D1, feature flag, Run Inspector view rules), the proof checklist with `[REF]` and live columns, the exact/lossy/unsupported table for every 1.0.3 event type, every measurement from the issue (REF values filled from tests and benches, live values `unknown (not observed)`), semantic duplication, and an exit section with exactly one exit decision and exactly one roadmap disposition, plus the decision rule and flip conditions, labelled a recommendation pending the owner `decision`. DoD: each issue measurement and proof appears exactly once, and no live claim is made without a pin.
- [ ] 10. (depends on 9) Add a Spikes bullet to `AGENTS.md` for the Phase B report and its model directory. DoD: the link resolves.

## Tests

- [ ] T1. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new manifest. A local negative check (adding a `decision` while `active`) is rejected.
- [ ] T2. `cd docs/spikes/agent-ui-ag-ui-phase-b && go vet ./... && go test ./...` passes with no network and no `go.sum`.
- [ ] T3. The ten issue-named tests exist under those exact names and pass.
- [ ] T4. `TestResumeReplay` shows exactly one handler state transition across two identical resumes on separate connections.
- [ ] T5. `TestResumeWrongActorTenant` and `TestInjectedEventRefused` show zero handler state changes, and the same refusal shape for unknown and forbidden ids.
- [ ] T6. `TestLastEventIDReplay` and `TestBoundedReplaySnapshot` show no lost or duplicated ids, and a snapshot fallback past the caps or retention.
- [ ] T7. `TestAdapterRemovable` shows identical canonical outcomes with the adapter enabled and disabled.
- [ ] T8. The `workflow-tests.yml` run on the PR executes the new step.
- [ ] T9. A grep of the report confirms that every live cell is either pinned evidence or `unknown (not observed)`, and that exactly one exit decision and one disposition are named.

## Rollback

All changes are additive documentation, a non-normative model and one CI step. To roll
back, revert the PR. This removes `roadmap/spikes/agent-ui-ag-ui-phase-b.yaml`,
`docs/spikes/agent-ui-ag-ui-phase-b{.md,/}`, the CI step and its path filters, and the
`AGENTS.md` bullet. No runtime, data or deployment is affected. If only the CI step
misbehaves, delete that step and its path filters and keep the model and report.
`roadmap/spikes/agent-ui-ag-ui.yaml` (Phase A) is untouched either way.
