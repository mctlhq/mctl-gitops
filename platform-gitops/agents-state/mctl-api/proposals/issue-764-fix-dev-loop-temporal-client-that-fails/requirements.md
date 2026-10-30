# Re-dial the DevLoop Temporal client after a failed startup dial

## Context

`cmd/api/main.go` builds the DevLoop Temporal client exactly once at startup
(`temporalclient.New(temporalAddress, temporalNamespace)`, next to the
`var devLoopClient mctlapi.DevLoopClient` declaration). If that one dial fails,
the code logs `WARN temporal client init failed` and leaves `devLoopClient` as a
nil interface for the life of the process. From then on every DevLoop route on
that pod answers `503 dev-loop Temporal client not configured`
(`requireTemporalAdmin` in `internal/api/handlers_dev_loop.go`), the
human-input routes report "unknown" or 503, and the lifecycle-conflict view
reports the legacy answer as unknown. Meanwhile `/readyz` stays green, so the
pod keeps taking traffic. On 2026-10-22/23 one of two replicas lost its dial
during the k3s upgrade window, and clients pinned to it by the sticky cookie got
a hard 503 on `approve` and `GET dev-loop` while the other replica worked. Only a
restart fixed it.

This proposal makes a failed startup dial recoverable without a restart. When
`TEMPORAL_ADDRESS` is set, the client is retried in the background with capped
exponential backoff. Until a dial succeeds, the DevLoop routes return a distinct
503 that says the client is configured but unreachable. That keeps the existing
`not configured` message for deployments that have no `TEMPORAL_ADDRESS`.
Readiness is not affected, because a Temporal outage must not take the whole API
out of rotation. This is the Temporal counterpart of mctl-api#387 (stores that
fail their one startup init).

## User stories

- AS a platform admin calling `mctl_approve_dev_loop` / `mctl_get_dev_loop` I
  WANT every replica to start serving DevLoop routes once Temporal is reachable
  SO THAT a transient Temporal outage during pod start does not need a manual
  restart.
- AS an operator reading a 503 I WANT to know whether Temporal is not configured
  on this deployment or is configured but not yet reachable SO THAT I fix the
  right thing (configuration or the Temporal frontend).
- AS the platform I WANT a Temporal outage to leave the rest of the API in
  rotation SO THAT unrelated routes keep working.

## Acceptance criteria (EARS)

- IF `TEMPORAL_ADDRESS` is unset or empty THEN THE SYSTEM SHALL leave
  `Options.TemporalClient` as a nil interface, and every DevLoop route SHALL
  answer 503 `dev-loop Temporal client not configured` (unchanged behaviour).
- WHEN `TEMPORAL_ADDRESS` is set THE SYSTEM SHALL install a non-nil
  reconnecting client in `Options.TemporalClient` whether or not the first dial
  succeeds. It SHALL never store a nil `*temporalclient.Client` in the interface
  field.
- IF the startup dial fails THEN THE SYSTEM SHALL keep re-dialing in the
  background with exponential backoff (1s initial delay, 30s cap) until a dial
  succeeds or the process shuts down.
- WHILE `TEMPORAL_ADDRESS` is set and no dial has succeeded yet THE SYSTEM SHALL
  answer every route gated by `requireTemporalAdmin` with 503 and the message
  `dev-loop Temporal client configured but currently unreachable`. That message
  is different from the not-configured one.
- WHILE the client is configured but unreachable, `GET /api/v1/human-inputs`
  with `state=pending` and `POST` human-input responses SHALL answer 503 with
  the unreachable message. Per-request human-input state and the
  lifecycle-conflict legacy answer SHALL report unknown with reason
  `dev-loop Temporal client configured but currently unreachable`.
- WHEN a background re-dial succeeds THE SYSTEM SHALL serve DevLoop routes
  through the new client on the next request, without a restart. It SHALL log
  one INFO line with the number of attempts.
- WHILE re-dialing THE SYSTEM SHALL log the first failure at WARN and later
  failures at most once per backoff-cap interval, so logs are not flooded.
- WHILE the Temporal client is configured but unreachable THE SYSTEM SHALL keep
  `GET /readyz` at its current verdict. The Temporal state SHALL be reported as
  information only, as `checks.temporal` = `connecting`, `ok` or
  `not_configured`, and SHALL NOT set ready=false.
- WHEN the process shuts down THE SYSTEM SHALL cancel a pending re-dial and
  close the client if it was ever dialed.
- WHEN a test server starts with an unreachable Temporal frontend that later
  becomes reachable THE SYSTEM SHALL stop answering 503 on the DevLoop routes
  without a restart. This SHALL be covered by an automated test.

## Out of scope

- Failing readiness when Temporal is unreachable. The issue offers this as an
  alternative but prefers keeping the pod in rotation.
- Changing how per-call Temporal RPC failures on an already-dialed client are
  mapped (the existing 502 paths). The gRPC connection under a dialed SDK client
  already reconnects by itself.
- Re-trying the other optional dependencies in `main.go` (k8s quota client,
  agent registry, and so on).
- The unverified `@MCTL investigate` non-acknowledgement on mctlhq/.github#209.
- Helm or gitops changes. No new environment variables are required.

## Open questions

- Should the backoff bounds be configurable (for example
  `TEMPORAL_REDIAL_MAX_BACKOFF`)? Proposed: no, hard-code 1s/30s like
  `storeInitBaseDelay`, and add a variable later if needed.
- Should `checks.temporal` appear in `/readyz` at all, given it never changes
  the verdict? Proposed: yes, as information for operators. A reviewer may
  prefer to expose it only in logs or metrics.
- The deployed mctl-api configuration (replica count, `TEMPORAL_ADDRESS`) could
  not be read in this run. See design.md "Deployed state checked". The
  description of production comes from the issue.
