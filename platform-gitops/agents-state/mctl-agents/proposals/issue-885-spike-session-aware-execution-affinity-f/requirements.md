# Spike #885: session-aware execution affinity for DevLoop and agent runs

## Context

Issue mctlhq/mctl-agents#885 asks whether MCTL needs explicit, application-level "session affinity",
meaning that related steps, retries and wakeups of one logical DevLoop or agent execution must always
run in the same executor context. The idea comes from protocol-aware Diameter load balancing, which
routes by logical session identity and not by TCP or pod stickiness. The issue allows exactly one of
three outcomes: `NO_AFFINITY_NEEDED`, `ADD_EXECUTION_AFFINITY_KEY` or `ADD_SESSION_ROUTING_BINDING`.
The answer must rest on a bounded experiment that forces consecutive steps of one logical execution
onto two interchangeable executor instances. It must not rest on argument alone.

This matters because MCTL keeps adding durable multi-step work that crosses executor boundaries: the
DevLoopWorkflow approval park, the `continue_as_new` merge watch, activity retries that resume Argo
polling through heartbeat details, WorkItem `we_` resume (ADR 011), and three worker roles on three
task queues (ADR-008). A hidden same-process assumption would show up as a stranded or duplicated
execution after a worker restart or a scale-out. Adding affinity that is not needed would add a second
session concept next to `execution_id` and the Temporal workflow id. The investigation's working
hypothesis is `NO_AFFINITY_NEEDED`. The spike exists to prove or refute that hypothesis with evidence,
and the recommendation is only written once the evidence exists.

## User stories

- AS a platform maintainer I WANT a current-state map from logical identity to durable state to
  executor routing for DevLoop and the #757 attention path SO THAT I know which state survives a
  change of executor.
- AS a platform maintainer I WANT every implicit same-executor assumption listed with its code and
  contract owner SO THAT scale-out or worker loss cannot silently break correctness.
- AS a reviewer I WANT a reproducible two-executor fixture with recorded evidence SO THAT the final
  outcome is backed by measurement, not opinion.
- AS the owner of #757 and #881 I WANT this spike to reuse existing identities and leave their scope
  alone SO THAT no competing session concept is introduced.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL map, for each tested path, its logical identity
  (Temporal workflow id `dev-loop-mctlhq-<repo>-<issue>`, run id, WorkItem `wi_`, execution `we_`,
  approval `aar_`, Argo workflow name, watched-resource key) to where its state is held and to how a
  step reaches an executor (task queue, sticky cache, Argo pod).
- WHEN the two-executor fixture runs a DevLoop path THE SYSTEM SHALL force consecutive workflow
  tasks and activity attempts of the same workflow id onto two distinct worker instances, and record
  the identity of the worker that ran each step.
- WHEN the fixture forces an activity retry after a heartbeat (the `submit_and_wait` resume path) THE
  SYSTEM SHALL record whether the second attempt on the other worker resumes from
  `activity.info().heartbeat_details` without a second submit.
- WHEN the fixture delivers an `approve` signal and a merge-watch `continue_as_new` hop while the
  previous worker is gone THE SYSTEM SHALL record whether the workflow completes with the same result
  as the single-worker baseline.
- WHEN the fixture runs the #757 `decide_wake_cycle` path on two instances THE SYSTEM SHALL record
  whether the decision depends only on the envelope, the re-observed state and the stored digest.
- IF any step behaves differently across executors than in the single-executor baseline THEN THE
  SYSTEM SHALL classify the gap (process-local state, missing durable key, ordering), name its owner,
  and repeat the run with the smallest explicit binding built on an existing identity (`execution_id`
  or workflow id) to show whether the gap disappears.
- IF a measurement could not be observed (no worker identity recorded, the test server unavailable,
  a step not reached) THEN THE SYSTEM SHALL report it as `unknown`, never as a pass.
- WHILE the spike runs THE SYSTEM SHALL make no change to production routing, worker configuration,
  `orchestrator/` modules or mctl-gitops values.
- WHILE any affinity contract is proposed THE SYSTEM SHALL keep identity, policy, approval and
  evidence canonical and server-side, and SHALL define recovery after executor loss.
- WHEN the report is final THE SYSTEM SHALL state exactly one outcome from the declared set, and SHALL
  open follow-up issues only for gaps the experiment proved.

## Out of scope

- Any production routing, sticky-pod, pod-affinity or connection-stickiness change.
- Changing the worker queue split or slot limits (ADR-008), or the implementation admission singleton.
  The spike records the singleton as a finding but does not change it.
- Persistent conversation sessions, the session store and Telegram coalescing (#760), and the
  claude-remote session design (#757).
- Sandbox or runtime choice (#881).
- Replacing Temporal, WorkItem, `we_` execution identity or lifecycle ownership (ADR 010).
- A generic service mesh or load balancer.

## Open questions

- Which #757 path counts as "representative"? The only executable artefact is
  `docs/spikes/757/attention.py` (`decide_wake_cycle`). The live claude-remote session is
  single-replica (`replicaCount: 0`, `Recreate` in mctl-gitops `services/labs/claude-remote/values.yaml`)
  and keeps its transcript in emptyDir synced to R2, so it cannot run on two instances without a
  production change. Assumption: test the fixture-level `decide_wake_cycle` with a shared digest store
  versus a per-instance digest store, and record the live session as unobserved.
- The implementation worker's admission capacity is a per-process slot limit that is correct only with
  one replica (`services/admins/mctl-agents-worker-implement/values.yaml`). That is a capacity
  invariant, not routing affinity, and ADR-010 / mctl-api#337 already own it. Assumption: list it as an
  implicit single-executor assumption with its owner, but do not count it as an affinity gap for the
  outcome decision.
- I could not see live Temporal sticky-queue behaviour or which worker ran each task in production,
  because no read-only mctl tool exposes them. The spike therefore runs on the Temporal test server
  and treats production routing as unknown, not as confirmed.
- Whether the usage ledger's in-process queue (`orchestrator/usage_ledger.py` `_WORKER`, flushed
  `atexit`) loses records on a hard executor kill. That is a durability question, not an affinity one.
  Assumption: record it in the dependency count and file a follow-up only if the fixture shows a loss.
