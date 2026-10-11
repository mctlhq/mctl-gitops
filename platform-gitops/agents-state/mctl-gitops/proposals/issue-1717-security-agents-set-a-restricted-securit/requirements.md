# Restricted securityContext for mctl-agents workflow steps

## Context

The Argo steps that run agent code (Claude Agent SDK sessions with a shell,
`git`, `uv`, test runners) use the image `{{workflow.parameters.agent_image}}`
in six ClusterWorkflowTemplates under
`platform-gitops/argo-workflows/cluster-templates/`: `run-implementer`
(`cwft-mctl-agents-implement.yaml`), `run-investigator`
(`cwft-mctl-agents-investigate.yaml`), `run-orchestrator`
(`cwft-mctl-agents-run.yaml`), `run-shepherd` (`cwft-mctl-agents-shepherd.yaml`),
`run-reconcile` (`cwft-mctl-agents-reconcile.yaml`) and `collect-usage`
(`cwft-mctl-agents-usage-collector.yaml`). None of them sets a pod or
container `securityContext`. They run as uid 1000 only because the image ends
with `USER app:app`; privilege escalation and the default capability set are
allowed, and with no k3s `seccompDefault` the effective seccomp profile is
`Unconfined`. The long-lived `admins-mctl-agents-worker-implement` Deployment,
which only enqueues work, is hardened more strongly than the pods that execute
untrusted-ish model-driven shell commands.

The issue asks for the cheapest available isolation step (VM sandboxes are not
possible on the Hetzner nodes): pin a restricted pod and container
`securityContext` on every agent-image step, and add a CI check so the
hardening cannot silently regress. `cwft-mctl-agents-daily.yaml` was checked:
it is a CronWorkflow that only references `mctl-agents-run` via
`workflowTemplateRef` and has no containers of its own, so it is covered by the
change to `cwft-mctl-agents-run.yaml`.

## User stories

- AS a platform operator I WANT agent pods to run with a non-root,
  no-escalation, no-capability, RuntimeDefault-seccomp security context SO THAT
  a compromised or misbehaving agent session has a smaller kernel and
  privilege attack surface.
- AS a platform operator I WANT CI to reject a change that removes this
  hardening from an agent-image step SO THAT the posture does not regress
  unnoticed.
- AS an agent author I WANT the workspace (`/workdir`) to stay writable for
  the agent SO THAT implement/investigate/shepherd runs keep working.

## Acceptance criteria (EARS)

- WHEN Argo creates the pod for `run-implementer`, `run-investigator`,
  `run-orchestrator`, `run-shepherd`, `run-reconcile` or `collect-usage` THE
  SYSTEM SHALL set the pod `securityContext` to `runAsNonRoot: true`,
  `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`,
  `seccompProfile.type: RuntimeDefault`.
- WHEN Argo creates any of those pods THE SYSTEM SHALL set the agent
  (`main`) container `securityContext` to `allowPrivilegeEscalation: false`
  and `capabilities.drop: [ALL]` (plus `runAsNonRoot: true`).
- WHILE a step's pod also contains the `clone-gitops` initContainer
  (`alpine/git`, which runs `apk add` and `chown -R 1000:1000 /workdir`) THE
  SYSTEM SHALL give that initContainer an explicit, narrower-than-default
  container `securityContext` (`allowPrivilegeEscalation: false`,
  `capabilities.drop: [ALL]`, only the capabilities it demonstrably needs
  added back, explicit `runAsUser: 0` / `runAsNonRoot: false`) so that the
  pod-level `runAsNonRoot` does not block it and its exception is visible in
  the template rather than implicit.
- WHILE the agent container runs THE SYSTEM SHALL keep `/workdir` (emptyDir)
  and `/tmp` writable by uid 1000.
- WHEN one real run each of implement, investigate, run (orchestrator),
  shepherd, reconcile and usage-collector is executed after the change THE
  SYSTEM SHALL complete it successfully.
- IF an agent-image step (container image `{{workflow.parameters.agent_image}}`)
  in any `cwft-mctl-agents-*.yaml` lacks pod-level `runAsNonRoot: true` or
  `seccompProfile.type: RuntimeDefault`, or container-level
  `allowPrivilegeEscalation: false` or `capabilities.drop: [ALL]`, THEN THE
  SYSTEM SHALL fail the `validate-manifests.yml` CI job.
- WHEN the new validator runs with `--selftest` THE SYSTEM SHALL prove it
  goes red on a fixture template with the block removed and green on the
  hardened fixture.
- IF a new `cwft-mctl-agents-*.yaml` adds an agent-image step THEN THE SYSTEM
  SHALL apply the same check to it without editing the validator's file list.

## Out of scope

- Setting `pod-security.kubernetes.io/enforce: restricted` on the
  `argo-workflows` namespace.
- The optional follow-up `pod-security.kubernetes.io/warn|audit: restricted`
  label on `argo-workflows` (recorded as a follow-up, done separately after
  this change is live).
- NetworkPolicy for agent steps.
- VM / gVisor / Kata sandbox runtimes.
- Hardening the non-agent helper templates (`commit-and-push`,
  `assert-attempt`, `notify-telegram`, `post-deploy-verify`) and
  `cwft-mctl-agents-approve.yaml`, which never run the agent image.
- `readOnlyRootFilesystem` for the agent container (the SDK, `uv` and
  toolchain bootstraps write under `$HOME` and `/tmp`).

## Open questions

- Whether the `clone-gitops` initContainer should be made fully non-root
  (drop the redundant `apk add`, set `HOME=/tmp`, rely on `fsGroup` instead of
  `chown`) in this change. This proposal keeps it root with an explicit,
  capability-trimmed container `securityContext` because
  `scripts/validate-local-workdir.py` (`validate_agents_workdir_nonroot_handoff`)
  asserts the `chown -R 1000:1000 /workdir` handoff, and rewriting the clone
  step multiplies the risk of a failed rollout. A fully non-root init is a
  natural follow-up and is required before any `enforce: restricted`.
- The exact minimal capability set the root initContainer needs
  (`CHOWN` is certain for `chown -R`; `apk add` may additionally need
  `DAC_OVERRIDE`/`FOWNER`/`SETGID`/`SETUID`). The design starts from
  `[CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID]` and the implementer should
  trim it only if a real run proves a capability unnecessary.
