# Separate private fake-provider Glovo Temporal worker image with tenant-fenced basket operations

## Context

PR #1187 added a Go Temporal PoC in the nested module `test/glovo-poc/`
(`controlplane`, `fakeglovo`, `fairness`, `leakcheck`, `workflows`) covering
revocation, fake baskets, consent and handoff (tests T1-T18). It is test-only
code: in-memory control plane, an httptest-only fake provider, no executable,
no image. Issue #1236 asks to promote only the reviewed, reusable parts of that
PoC into an independently buildable, private **fake-provider worker
executable and container image** in `mctl-telegram`, distinct from the public
server image (`Dockerfile`) and from the agent-worker image
(`Dockerfile.agent-worker`).

The worker is the provider side of the boundary described in
`docs/adr/0010-glovo-multitenant-connections.md`: it polls only the Temporal
provider namespace `mctl-assistants-provider-glovo`, has no authority over
`mctl-assistants` control workflows or `mctl-agents` DevLoop, accepts only
opaque identifiers, and revalidates tenant/owner/install/revision/connection
and a single-use `aar_` approval receipt through mctl-api at the synthetic
basket mutation boundary. The control-to-provider protocol (mctl-agents#1043)
and mctl-api authority (mctl-api#953, #954) are pending, so this slice ships
a versioned Go contract with fake implementations for local tests only.
Production integration, image publication to a deploy, GitOps changes and any
real Glovo access are out of scope and blocked.

## User stories

- AS a platform operator I WANT the Glovo provider worker built as its own
  private image SO THAT a compromise of provider I/O cannot reach the public
  `tg.mctl.ai` process, its secrets, or trusted Temporal workflows.
- AS a tenant owner I WANT every synthetic basket write fenced by my live
  tenant, install revision, connection and a single-use approval receipt SO
  THAT no other tenant, principal or replayed request can change my basket.
- AS a security reviewer I WANT fake-only enforced at build time and at
  runtime, with negative tests for every refusal SO THAT approving this code
  cannot result in a real Glovo call, credential, or egress.
- AS an SRE I WANT health/readiness, metrics, a kill switch, graceful
  shutdown and rollback-to-previous-image SO THAT the worker is operable once
  later approvals allow deployment.

## Acceptance criteria (EARS)

Build and image
- WHEN `docker build -f Dockerfile.glovo-provider-worker .` runs THE SYSTEM
  SHALL produce a reproducible image (digest-pinned base images, `-trimpath`,
  `CGO_ENABLED=0`, version via build arg) containing only the
  `glovo-provider-worker` binary, running as non-root uid 1000, with no shell
  entrypoint and no exposed public port other than the internal health/metrics
  port.
- WHEN a pull request is opened THE SYSTEM SHALL build that image in a separate
  CI job (`docker-glovo-provider-worker`) without pushing it, and SHALL vet and
  race-test the nested module `provider/glovo` with `-race -count=1`.
- THE SYSTEM SHALL keep the Temporal SDK out of the root module `go.mod`, and
  the root `cmd/server` binary SHALL NOT import any `provider/glovo` package.

Fake-only gate
- WHILE the binary was built without the `glovo_real` build tag THE SYSTEM
  SHALL contain no real provider adapter code path, and SHALL refuse to start
  unless `FAKE_ONLY=true` (missing or any other value is a startup error).
- IF any environment variable whose name matches a Glovo credential/session
  pattern (`GLOVO_*TOKEN*`, `GLOVO_*SESSION*`, `GLOVO_*COOKIE*`,
  `GLOVO_*PASSWORD*`, `GLOVO_API_*`, `GLOVO_BASE_URL`) is set THEN THE SYSTEM
  SHALL refuse to start and log only the variable name.
- WHILE running THE SYSTEM SHALL serve the fake provider only on loopback
  in-process and SHALL refuse any provider base URL that is not loopback
  (reusing `fakeglovo.NewClient`'s `ErrNonLoopback` rule).

Temporal identity
- WHEN the worker starts THE SYSTEM SHALL connect only to the namespace
  `mctl-assistants-provider-glovo` and task queue `assistants-provider-glovo`,
  and IF the configured namespace or queue differs THEN THE SYSTEM SHALL
  refuse to start.
- THE SYSTEM SHALL register no workflow or activity that lists, signals,
  queries, cancels or terminates workflows in any other namespace, and SHALL
  hold no Temporal client handle other than the worker's own poller.

Request fencing
- WHEN a provider activity receives a request THE SYSTEM SHALL accept only
  opaque identifiers (`we_` execution, tenant, owner principal, `gcn_`
  connection, intent hash, install id/revision, `aar_` receipt ref) defined by
  a versioned protocol type, and IF the request carries an unknown field, a
  role, `namespace`, `workflow_id`, `run_id`, `task_queue`, URL, endpoint or
  credential field THEN THE SYSTEM SHALL reject it with zero mutations.
- WHEN a synthetic basket mutation is about to be applied THE SYSTEM SHALL
  resolve live tenant, owner, install revision, connection state and consume
  the `aar_` receipt through the `ControlBridge` interface, and IF any of
  foreign order id, other tenant, same-tenant other principal, stale install,
  revoked or expired connection, wrong `aar_`, wrong `we_`, mismatched intent
  hash, expired receipt or replayed receipt applies THEN THE SYSTEM SHALL
  return the matching typed refusal code from ADR 0010 and perform zero
  mutations.
- IF the `ControlBridge` is unreachable, times out or returns a malformed
  answer THEN THE SYSTEM SHALL fail closed (non-retryable refusal, zero
  mutations), never treating an unknown answer as an allow.

Exactly-once synthetic effect
- WHEN a mutation activity is retried, or its first attempt ended in an
  ambiguous timeout THE SYSTEM SHALL read back the fake basket and compare its
  fingerprint before any re-apply, and SHALL apply the observable synthetic
  basket effect at most once per `(tenant, order, intent hash)` idempotency key.
- IF revocation or cancellation arrives during any activity, after an activity
  boundary, or at handoff open THEN THE SYSTEM SHALL reach a deterministic
  terminal state (`revoked`, `cancelled`, or `OUTCOME_UNKNOWN` when the effect
  cannot be verified) and SHALL revalidate scope before issuing or honouring a
  handoff.

Operations
- THE SYSTEM SHALL expose `/livez`, `/healthz`, `/readyz` and `/metrics` on an
  internal port only, where readiness is false until the Temporal poller is
  running and the kill switch is off.
- WHEN the kill switch (`GLOVO_PROVIDER_DISABLED=true`, or a per-provider
  circuit breaker open) is active THE SYSTEM SHALL stop accepting new
  mutation activities with a typed refusal while letting reads of local state
  and shutdown proceed.
- WHEN SIGTERM is received THE SYSTEM SHALL stop polling, let in-flight
  activities finish within a bounded grace period, and exit 0.
- THE SYSTEM SHALL emit structured audit and trace events containing only
  opaque identifiers and refusal codes, never tenant PII, basket item text,
  receipts, tokens or session material, enforced by a leak-scan test.
- THE SYSTEM SHALL enforce independent per-tenant concurrency limits and a
  per-provider circuit breaker (promoted from `test/glovo-poc/fairness`).

## Out of scope

- Any real Glovo API, login, session, checkout, payment, or outbound Glovo
  egress (gate G3 in ADR 0010).
- Publishing the image to GHCR from main, any GitOps service, namespace,
  NetworkPolicy, Vault secret, DNS, Temporal namespace or deployment. The
  image *specification* and a no-push CI build are in scope; publishing and
  deploying need separate approvals.
- The public MCP facade (`glovo.mctl.ai/mcp`), its image and tools (separate
  issue).
- The production `ControlBridge` implementation (Nexus or mctl-api bridge);
  blocked on mctl-agents#1043, mctl-api#953/#954, mctl-gitops#2469.
- Removing or rewriting `test/glovo-poc`; it remains as the reference PoC.

## Open questions

- Transport for control-to-provider dispatch (Nexus vs. authenticated mctl-api
  bridge) is undecided in mctl-agents#1043. This proposal defines a local
  versioned Go contract (`protocol/v1alpha1`) and fakes; the wire format is
  expected to be replaced when #1043 lands. Proceeding on that basis.
- Exact `aar_` receipt shape and consume semantics (mctl-api#954). Assumed:
  opaque ref, server-side single-use consume bound to tenant, owner, `we_`,
  connection, install revision, basket fingerprint and intent hash, per ADR
  0010 "Approval".
- Image name: assumed `ghcr.io/mctlhq/mctl-telegram-glovo-provider-worker`;
  only the label/spec is defined here, nothing is pushed.
- Whether the PoC `test/glovo-poc` should later import the promoted packages
  instead of its own copies; left unchanged in this slice to keep the
  reviewed PoC stable.
- How the worker authenticates to Temporal (mTLS/API key) depends on
  mctl-gitops#2469; this slice only supports a configured endpoint plus
  optional TLS files and is not deployable until then.
