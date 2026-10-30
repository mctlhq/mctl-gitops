# Design: issue-764-fix-dev-loop-temporal-client-that-fails

## Current state

- `cmd/api/main.go`, the block after the comment "Temporal client for
  DevLoopWorkflow": `var devLoopClient mctlapi.DevLoopClient`. When
  `TEMPORAL_ADDRESS` is set, it calls
  `temporalclient.New(temporalAddress, temporalNamespace)` once. `TEMPORAL_NAMESPACE`
  defaults to `mctl-agents`. On error the code runs
  `slog.Warn("temporal client init failed", ...)` and leaves the interface nil.
  On success it assigns the client and runs `defer tc.Close()`. The comment
  there documents the nil-interface discipline: never assign a nil
  `*temporalclient.Client` to the interface. The value is passed as
  `TemporalClient: devLoopClient` into the router options.
- `internal/temporalclient/client.go`: `New` calls `client.Dial(...)` (SDK
  `go.temporal.io/sdk v1.47.0`). Dial does an eager connectivity check, so an
  unreachable frontend fails it immediately. `Client` wraps
  `temporal client.Client`. Once dialed, the SDK's gRPC connection reconnects by
  itself, so only the first dial is fatal.
- `internal/api/interfaces.go`: `DevLoopClient` interface (StartDevLoopWorkflow,
  RestartAbandonedDevLoopWorkflow, DevLoopEnded, SignalApprove, SignalAbandon,
  DescribeDevLoop, DescribeDevLoopExecution, QueryShepherdInLoop,
  QueryHumanInputState, SignalHumanInputResponse).
- `internal/api/router.go`: `Options.TemporalClient DevLoopClient`.
- Consumers that check for nil:
  - `internal/api/handlers_dev_loop.go` `requireTemporalAdmin`:
    `h.opts.TemporalClient == nil` returns 503
    `dev-loop Temporal client not configured`. It is used by 10 routes,
    including start, approve, abandon, get and the roadmap wave start
    (`handlers_roadmap_wave.go`).
  - `internal/api/handlers_human_input.go`: `humanInputStates.state` returns
    `HumanInputUnknown, "dev-loop Temporal client not configured"` when the
    client is nil. The list handler returns 503 for `state=pending` when the
    client is nil.
  - `internal/api/handlers_human_input_response.go`: 503
    `human-input responses are not configured` when the client is nil.
  - `internal/api/handlers_lifecycle_conflict.go` `lifecycleLegacyFor`: legacy
    answer unknown with reason `dev-loop Temporal client not configured`.
- Precedent: mctl-api#387. `initStore` / `initStoreAttempts` in `main.go` retry a
  store with backoff inside a shared 8s budget, then record a failure in
  `storeInitFailures`, which keeps `/readyz` at 503 (`internal/api/ready.go`,
  `Options.StoreInitFailures`). The Temporal client was never moved onto that
  path. The issue explicitly asks not to tie Temporal to readiness.
- Tests: `internal/api/handlers_dev_loop_test.go` injects fake `DevLoopClient`s.
  `internal/temporalclient/client_mock_test.go` uses `go.temporal.io/sdk/mocks`.
  `cmd/api/main_test.go` has `TestTransientStoreInitFailureKeepsThePodNotReady`
  as the #387 analogue.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)` returned
  "service not found: admins/mctl-api". The deployed config was not observable
  through this tool.
- `$MCTL_GITOPS_ROOT/services/` (checkout): `admins/` contains
  mctl-agents-worker*, mctl-design, mctl-docs, mctl-web and umami, but no
  mctl-api values.yaml. `TEMPORAL_ADDRESS` and `replicaCount: 2` could
  therefore not be confirmed. The production facts used here
  (`temporal-frontend.temporal.svc.cluster.local:7233`, namespace `mctl-agents`,
  2 replicas, sticky cookie) come from the issue report only.
- The repo's `helm/` has no `TEMPORAL_ADDRESS` default. It is set by the
  deployment's values, which could not be observed here.

## Proposed solution

### 1. `temporalclient.Reconnecting` (new, `internal/temporalclient/reconnecting.go`)

`Reconnecting` is a wrapper that implements the whole `DevLoopClient` method set:

```go
var ErrUnavailable = errors.New("temporalclient: configured but currently unreachable")

type Reconnecting struct {
    current atomic.Pointer[Client]   // nil until a dial succeeds
    lastErr atomic.Pointer[error]
    dial    func(ctx context.Context) (*Client, error) // injectable for tests
    cancel  context.CancelFunc
    done    chan struct{}
}

func NewReconnecting(ctx context.Context, hostPort, namespace string) *Reconnecting
func (r *Reconnecting) Available() error // nil once dialed, else ErrUnavailable wrapping last dial error
func (r *Reconnecting) Close()           // cancels the loop, closes current if set
```

- `NewReconnecting` makes one synchronous dial attempt, bounded by a short
  timeout (about 3s), so a healthy start behaves as it does today. If that
  attempt fails, it starts a goroutine that re-dials with exponential backoff
  (1s, 2s, 4s, and so on, capped at 30s, with jitter). The loop stops on the
  first success or when the context is cancelled.
- The dial uses `client.DialContext`, so shutdown cancels a dial in flight.
  `New` stays as it is. A new unexported `newWithContext` is shared by both.
- Each `DevLoopClient` method loads `current`. If it is nil, the method returns
  `fmt.Errorf("%w: %v", ErrUnavailable, lastErr)`. Otherwise it delegates.
  After a dial succeeds there is no further re-dial: the SDK handles transport
  reconnects.
- Logging: the first failure at WARN
  (`temporal client dial failed; retrying in background`), later failures at
  most once per 30s cap interval, and success after a retry at INFO with
  `attempts`.
- Tests can build the type with a constructor that accepts a dial func
  (`newReconnectingWithDialer`).

Why a wrapper rather than mutating `Options.TemporalClient`: `Options` is
copied into the handlers at router build time. A stable non-nil wrapper whose
inner pointer is swapped atomically needs no locking in the handlers and keeps
the nil-interface discipline trivially true.

### 2. `cmd/api/main.go`

```go
var devLoopClient mctlapi.DevLoopClient
if temporalAddress := os.Getenv("TEMPORAL_ADDRESS"); temporalAddress != "" {
    rc := temporalclient.NewReconnecting(rootCtx, temporalAddress, temporalNamespace)
    devLoopClient = rc            // non-nil concrete pointer, never nil
    defer rc.Close()
}
```

The block comment is updated: the nil interface now means only
"`TEMPORAL_ADDRESS` not set". The `defer tc.Close()` is replaced by
`defer rc.Close()`.

### 3. Availability check in handlers (`internal/api`)

Add an optional interface and one helper in `handlers_dev_loop.go`:

```go
// TemporalAvailability is implemented by clients that may be configured
// but not yet connected (temporalclient.Reconnecting).
type TemporalAvailability interface{ Available() error }

const (
    msgTemporalNotConfigured = "dev-loop Temporal client not configured"
    msgTemporalUnreachable   = "dev-loop Temporal client configured but currently unreachable"
)

// temporalState returns "" when usable, else the message to report.
func (h *Handlers) temporalState() string
```

Fakes in existing tests do not implement `TemporalAvailability` and are treated
as available, so the existing tests keep passing unchanged.

Call sites:
- `requireTemporalAdmin`: nil gives 503 not-configured (unchanged). Unavailable
  gives 503 unreachable. Both checks run before the auth checks, as today.
- `handlers_human_input.go`: `newHumanInputStates` records the state message.
  `state()` returns `HumanInputUnknown` with that message. The `state=pending`
  list check uses `temporalState()` and returns 503 with the right message plus
  the existing suffix `: pending state cannot be determined`.
- `handlers_human_input_response.go`: keeps the combined
  "not configured" check for nil. Adds a 503 with the unreachable message when
  the client is configured but unavailable.
- `handlers_lifecycle_conflict.go` `lifecycleLegacyFor`: unknown, with the
  matching reason.
- Defence in depth: wherever a handler maps a Temporal error to 502 (start,
  approve, get, abandon, roadmap wave per-item failures), an error matching
  `errors.Is(err, temporalclient.ErrUnavailable)` is mapped to 503 with the
  unreachable message instead. This covers a request that passed the gate in
  the instant before a dial result is published. In practice that can only go
  from unavailable to available, never the reverse.

### 4. `/readyz` information (`internal/api/ready.go`)

Add `Options.TemporalState func() string`, wired in `main.go` to report
`not_configured`, `connecting` or `ok`. `ready.go` copies it into
`checks["temporal"]` and never touches `ready`. When it is nil (tests), the key
is omitted.

## Alternatives

1. **`client.NewLazyClient` instead of `Dial`.** The SDK defers connecting until
   the first call, and gRPC handles reconnection, so a failed start heals
   automatically. This was dropped as the only change because there is no
   "configured but unreachable" state to report: every call while Temporal is
   down surfaces as a generic RPC failure (502 on most routes), which misses the
   acceptance criterion for a distinct 503. It also changes behaviour on healthy
   starts, where a bad address would no longer show up in the startup log. It
   could still be used inside `Reconnecting` later.
2. **Fail readiness when the dial fails** (fold into `storeInitFailures`). This
   is simple and matches #387, but the issue explicitly prefers not to: a
   Temporal outage at deploy time would take every replica, and therefore every
   non-DevLoop route, out of rotation. A store-style "stays nil until restart"
   also still needs a restart.
3. **Lazy dial on first request under a mutex.** No goroutine, but the first
   caller after an outage pays the full dial timeout, concurrent callers
   serialise behind it, and the 503 message would depend on request timing.
   Dropped in favour of background backoff with an atomic swap.

## Platform impact

- **Migrations:** none. **Configuration:** none new. `TEMPORAL_ADDRESS` and
  `TEMPORAL_NAMESPACE` keep their meaning.
- **Backward compatibility:** the not-configured 503 is unchanged for
  deployments without `TEMPORAL_ADDRESS`. Clients that match on the 503 status
  alone see no change. The MCP tools pass the error text through. The new
  message is additive. No MCP tool is added or removed, so the tool count in
  `server_test.go` is unchanged.
- **Resources:** at most one goroutine per pod while Temporal is unreachable,
  and one dial every 30s at steady state. This is negligible.
- **Risks and mitigations:**
  - A healthy start becomes slower: the synchronous first attempt is bounded at
    about 3s, which is no worse than today's unbounded `Dial`.
  - A goroutine leak in tests: `Close()` cancels and waits on `done`. Tests use
    `t.Cleanup(rc.Close)`.
  - A misconfigured address (typo) now retries forever instead of failing once.
    The WARN log every 30s plus `checks.temporal=connecting` keep it visible.
  - Data race on swap: `atomic.Pointer` is used. The race detector runs in the
    tests.
