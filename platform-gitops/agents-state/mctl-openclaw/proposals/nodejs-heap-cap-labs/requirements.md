# Cap Node.js heap in labs pod via --max-heap-size (Node 24.15.0 LTS)

## Context
The `labs` tenant of mctl-openclaw runs on Kubernetes and is documented as close to its memory
limit (see `context/architecture.md`). The openclaw process is a long-lived Node.js service
managing multiple channel connections. Without an explicit JavaScript heap ceiling, the V8 garbage
collector has no external pressure to compact aggressively, so heap growth can silently consume the
headroom reserved for OS/channel buffers and native allocations. When the kernel's OOM killer fires
before V8 can reclaim memory, the pod is terminated without a clean shutdown path, causing auth
state to be lost from memory. On the next startup the restore-state readiness probe must rehydrate
all sessions from S3 (per ADR-0002), producing downtime for labs channel users and increasing
operational noise that masks genuine incidents.

Node.js 24.15.0 LTS ("Krypton"), released 2026-04-15, promotes `--max-heap-size=<MB>` to a stable
CLI option. Setting this flag gives V8 a hard ceiling: when the heap approaches the cap, V8
performs aggressive GC; if GC cannot free enough, the process throws a catchable JS heap OOM
instead of being OOMKilled by the kernel. This allows a controlled restart with full S3 state
restore rather than an abrupt pod eviction. Critically, the flag does not increase RSS — it only
constrains the JS heap, so enabling it in the memory-constrained `labs` tenant carries no upward
memory risk, only a downward cap risk (GC thrashing) if sized incorrectly. A mandatory profiling
step gates the chosen cap value.

## User stories
- AS a platform operator I WANT the labs openclaw pod to have a bounded JavaScript heap SO THAT
  kernel OOMKills are replaced by catchable JS heap OOMs that allow a graceful restart with S3
  state restore.
- AS a labs channel user I WANT auth sessions to survive pod restarts caused by memory pressure SO
  THAT channel downtime is minimized and I do not lose my connected sessions.
- AS an on-call engineer I WANT the heap cap value to be derived from a documented profiling
  baseline SO THAT I can adjust it with confidence if GC pressure becomes visible in metrics.

## Acceptance criteria (EARS)

- WHEN the labs pod starts, THE SYSTEM SHALL pass `--max-heap-size=<N>` (where N is the value
  determined by the profiling task) to the Node.js process via the labs-specific helm overlay, so
  that V8 applies a JavaScript heap ceiling from the first event loop tick.

- WHEN the JavaScript heap reaches the configured cap, THE SYSTEM SHALL trigger aggressive V8
  garbage collection before allocating beyond the cap, so that GC reclaim is attempted prior to any
  OOM condition.

- IF V8 garbage collection cannot reclaim sufficient heap after reaching the cap, THE SYSTEM SHALL
  throw a catchable JavaScript heap OOM error (not rely on kernel OOMKill), allowing the process to
  emit a structured shutdown log entry and exit with a non-zero code so that the Kubernetes restart
  policy and the restore-state probe can execute the standard S3 rehydration path.

- WHILE the labs pod is running under normal load, THE SYSTEM SHALL maintain heap utilisation below
  the configured cap without triggering excessive GC cycles, as evidenced by the existing CPU and
  memory metrics remaining within their pre-change baselines.

- WHEN the `--max-heap-size` flag is present in the labs helm overlay, THE SYSTEM SHALL NOT apply
  that flag to the `admins` or `ovk` helm values, so that those tenants are not constrained
  unnecessarily.

- IF the heap cap value is not yet profiled and confirmed, THE SYSTEM SHALL block deployment of
  this change until the profiling task (task 1 in `tasks.md`) produces a documented baseline and a
  recommended cap value.

## Out of scope
- Applying `--max-heap-size` to the `admins` or `ovk` tenants — neither has a memory constraint
  that justifies a heap cap today.
- Upgrading Node.js to a new major version — that is handled by the separate
  `nodejs-runtime-upgrade` proposal.
- Capping RSS, total container memory limits, or native/buffer heap allocations — `--max-heap-size`
  only governs the V8 JS heap.
- Modifying S3 state persistence, the s3-sync canary, or the restore-state probe — those
  mechanisms are governed by ADR-0002 and are unchanged.
- Adding new memory monitoring infrastructure — existing mctl MCP metrics are sufficient for
  validating the cap value.
