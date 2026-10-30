# Tasks: issue-764-fix-dev-loop-temporal-client-that-fails

- [ ] 1. Add `internal/temporalclient/reconnecting.go`. It contains
  `ErrUnavailable`, the `Reconnecting` type (atomic `*Client` pointer, last dial
  error, injectable dialer), `NewReconnecting(ctx, hostPort, namespace)` (a
  synchronous first attempt bounded at about 3s, then background re-dial with
  1s to 30s jittered exponential backoff using `client.DialContext`),
  `Available()`, `Close()`, and delegating implementations of every
  `DevLoopClient` method that return `ErrUnavailable` (wrapping the last dial
  error) until a dial succeeds. Add rate-limited WARN logs and an INFO log on
  success after a retry.
  DoD: `go vet` is clean. `*Reconnecting` satisfies `mctlapi.DevLoopClient`
  (compile-time assertion in an `internal/api` test file, to avoid an import
  cycle).
- [ ] 2. (depends on 1) In `cmd/api/main.go`, replace the one-shot
  `temporalclient.New` block with `NewReconnecting(rootCtx, ...)`. Assign the
  non-nil `*Reconnecting` to `devLoopClient` and run `defer rc.Close()`. Update
  the nil-interface comment so that nil means only "`TEMPORAL_ADDRESS` unset".
  DoD: an unset `TEMPORAL_ADDRESS` still leaves the interface nil. A set
  address always yields a non-nil client.
- [ ] 3. (depends on 1) In `internal/api/handlers_dev_loop.go`, add the
  `TemporalAvailability` interface, the `msgTemporalNotConfigured` and
  `msgTemporalUnreachable` constants, and `(*Handlers).temporalState()`. Make
  `requireTemporalAdmin` return 503 with the unreachable message when the client
  is configured but unavailable. Map `errors.Is(err, temporalclient.ErrUnavailable)`
  to 503 with the unreachable message on the start, approve, abandon and get
  paths, and on the roadmap wave per-item failure path.
  DoD: the not-configured message is emitted only for a nil client.
- [ ] 4. (depends on 3) Apply the same distinction in
  `handlers_human_input.go` (`newHumanInputStates`, `state()`, the
  `state=pending` list check), `handlers_human_input_response.go` (503 with the
  unreachable message) and `handlers_lifecycle_conflict.go`
  (`lifecycleLegacyFor` reason).
  DoD: no consumer reports "not configured" for a configured-but-unreachable
  client.
- [ ] 5. (depends on 1) Add `Options.TemporalState func() string` in
  `internal/api/router.go`. Report it as `checks.temporal`
  (`not_configured` / `connecting` / `ok`) in `internal/api/ready.go` without
  affecting `ready`, and wire it in `main.go`.
  DoD: `/readyz` stays 200 while Temporal is unreachable and all other checks
  pass.
- [ ] 6. Run `go fmt`, `go vet`, `golangci-lint` and `go test -race ./...`.

## Tests

- [ ] T1. `internal/temporalclient/reconnecting_test.go`: an injected dialer
  fails N times and then succeeds. Assert that `Available()` returns an error
  matching `ErrUnavailable` before success and nil after, that delegated calls
  return `ErrUnavailable` before and reach the underlying mock
  (`go.temporal.io/sdk/mocks.Client`) after, that the backoff is capped, and
  that `Close()` stops the loop with no goroutine left (cancelled context).
- [ ] T2. Acceptance test: start the server with an unreachable
  `TEMPORAL_ADDRESS`, then make Temporal reachable. In
  `internal/temporalclient`, reserve a TCP port and leave it closed, then call
  `NewReconnecting` against it (with backoff shrunk through a test variable).
  Then start a `grpc.Server` on that address that registers a
  `workflowservice.UnimplementedWorkflowServiceServer` stub answering
  `GetSystemInfo` and `DescribeWorkflowExecution`. Assert that `DescribeDevLoop`
  goes from `ErrUnavailable` to a real answer without building a new client.
- [ ] T3. Router-level test in `internal/api/handlers_dev_loop_test.go`: build
  the router with a `Reconnecting` whose dialer is gated by a channel. Assert
  that `GET /api/v1/agents/dev-loop/{id}` and approve answer 503 with
  `configured but currently unreachable`. Release the dialer and assert that the
  same router (no rebuild) answers 200 / 202.
- [ ] T4. Not-configured remains distinct: with `TemporalClient` nil, assert
  that the 503 body equals `dev-loop Temporal client not configured` on the
  dev-loop, human-input-pending and human-input-response routes, and in the
  lifecycle-conflict legacy reason.
- [ ] T5. Unreachable variants for the human-input list (`state=pending`), the
  human-input response, per-request human-input state, and the
  lifecycle-conflict legacy reason.
- [ ] T6. `/readyz`: `checks.temporal=connecting` with HTTP 200 while
  unavailable, and `ok` after the dial succeeds. The key is absent when
  `TemporalState` is nil.
- [ ] T7. Existing `handlers_dev_loop_test.go`, `handlers_human_input_test.go`
  and `handlers_roadmap*_test.go` fakes, which do not implement
  `TemporalAvailability`, keep passing unchanged.

## Rollback

Revert the PR. The change has no schema, configuration or Helm footprint, so
the previous image restores the one-shot dial exactly. If a pod is degraded
after rollback, the documented remediation still applies: bump
`ROLLOUT_MARKER` in mctl-gitops to restart the pods.
