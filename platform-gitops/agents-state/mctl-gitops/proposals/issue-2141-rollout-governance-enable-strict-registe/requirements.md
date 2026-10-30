# Evidence-gated rollout: enable strict registered-policy enforcement for action approvals (mctl-api#721)

## Context

mctl-api#721 (implemented by mctl-api#766, merged 2026-10-23T08:28Z) hardened the
action-approval contract and shipped `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY`
strict-off. With strict mode on, mctl-api refuses to create (422), decide (409)
or spend (409, `reapproval_required=true`) an approval whose `policy_rule_id` is
not in the registered `governance.Policies` set (`approval_policy_unregistered`),
and answers 503 `approval_policy_unavailable` if the set is empty. #721 left the
production flip to a separate governed GitOps rollout. It is allowed only after at
least one `ACTION_APPROVAL_MAX_DECISION_AGE` observation window, and only once the
evidence shows that no live producer would be refused.

This proposal is that rollout carrier. It has two parts. The first is an evidence
gate, which can stop the rollout. The second is a one-line change to the
canonical production mctl-api Application
(`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, `env:` block)
that adds `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"`. Post-flip
verification and recorded evidence follow. It introduces no new policy model
and no mctl-api code change.

## User stories

- AS a platform owner I WANT action approvals in production to fail closed on an unregistered policy SO THAT no executable approval can rest on a rule the platform does not know.
- AS an operator I WANT the flip gated on authoritative evidence SO THAT a legitimate producer is not silently broken, and missing evidence is never read as clean.
- AS an operator I WANT a single-edit rollback SO THAT a bad flip can be reverted through GitOps with no data change.
- AS a reviewer of mctl-api#721 I WANT every step's evidence recorded on mctl-gitops#2141 SO THAT closure can be audited.

## Acceptance criteria (EARS)

Evidence gate (before any configuration change):

- WHEN the rollout starts THE SYSTEM SHALL record the pinned mctl-gitops commit, the deployed mctl-api image tag (currently `4.122.0` in `mctl-api.yaml`), and the mctl-api source revision of that tag.
- WHEN the deployed image is evaluated THE SYSTEM SHALL confirm that the tag contains the mctl-api#766 merge commit `329f17c6c238494947bfe3bcb59a9b5702760a93`, and that the `admins-mctl-api` Argo CD Application is Healthy and Synced.
- WHEN the observation window is evaluated THE SYSTEM SHALL determine the effective `ACTION_APPROVAL_MAX_DECISION_AGE` from the deployed configuration. If it is unset or empty, the value is `governance.DefaultMaxDecisionAge` (24h). The window SHALL be measured from the first #721-capable deploy to the flip, and SHALL cover at least one such age.
- WHEN producers are inventoried THE SYSTEM SHALL list every distinct (`policy_rule_id`, `policy_version`, `policy_status`) seen on action approvals created, decided or spent during the window. The source SHALL be an authoritative store: the work-items action-approval table or the audit log entries that record `policy_status`. It SHALL NOT be a Loki read alone.
- WHEN the inventory is complete THE SYSTEM SHALL proceed only if every entry has `policy_status = ok` against the registered set (today only `dev-loop.human-approval@v1`), or belongs to an approval that can no longer be executed (denied, expired, consumed or past `fresh_until`).
- WHEN live approvals are evaluated THE SYSTEM SHALL proceed only if no request in state `pending` or `approved` that is still within `fresh_until` lacks mandatory decision context or carries an unregistered rule.
- IF any evidence surface is unavailable, errors or returns nothing usable THEN THE SYSTEM SHALL NOT change the flag, and SHALL record the gap on mctl-gitops#2141 as a blocker. In this check, "unknown" is never "clean".
- IF the inventory shows an unregistered or drifting producer that is still executable THEN THE SYSTEM SHALL NOT flip. It SHALL record the producer, which needs a follow-up in mctl-api (register the rule or retire the producer) under a separate issue.

Rollout:

- WHEN the evidence gate passes THE SYSTEM SHALL open one PR that changes only `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. The PR SHALL add `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"`, with a comment giving the reason, the evidence link and the rollback, in the style of the neighbouring `MCTL_AGENT_RECEIPT_GATE` entry.
- WHILE the PR is open THE SYSTEM SHALL keep it free of unrelated changes. That includes the image tag and `ROLLOUT_MARKER`: the env change alone triggers a pod rollout.
- WHEN the PR merges THE SYSTEM SHALL let Argo CD sync normally (no manual `kubectl` or Argo bypass), and SHALL confirm that `admins-mctl-api` returns to Healthy/Synced on the same image tag.
- WHEN the new pods start THE SYSTEM SHALL capture the boot log line `action approval policy` (from `logApprovalPolicy` in mctl-api `cmd/api/main.go`) on every replica, with `require_registered_policy=true` and `registered_rules=[dev-loop.human-approval@v1]`.
- WHEN strict mode is live THE SYSTEM SHALL run a bounded negative proof: a create-only request with an unregistered `policy_rule_id` is refused with 422 `approval_policy_unregistered`. The request is non-executable and stores nothing. No approval is decided or spent, and no work runs.
- WHEN strict mode is live THE SYSTEM SHALL confirm that the next normal governed DevLoop approval (rule `dev-loop.human-approval@v1`) is still granted and spent without a policy refusal.
- IF the post-flip checks fail (pods not Healthy, boot line missing or false, legitimate DevLoop approval refused) THEN THE SYSTEM SHALL roll back by reverting the single env line through a GitOps PR.

Closure:

- WHEN all checks pass THE SYSTEM SHALL record on mctl-gitops#2141, with a link back to mctl-api#721: pinned revisions and image, effective max-decision-age and observation interval, inventory result, live-approval result, the enabling PR/commit, the Argo result, the boot evidence, the negative proof and the rollback path. Only then SHALL the issue be closed.

## Out of scope

- Any mctl-api code, chart default, or `governance.Policies` change, including registering new rules.
- Changing `ACTION_APPROVAL_MAX_DECISION_AGE`.
- A new approval or policy model, or new evidence tooling.
- Preview or staging mctl-api deployments.
- Backfilling or mutating legacy approval rows.

## Open questions

- Inventory surface: no read-only mctl MCP tool exposes action-approval rows or their `policy_status`. The rollout needs a direct read of the work-items store (`WORK_ITEMS_DB_URL`, or `AUDIT_DB_URL` in `mctl-api` on `shared-pg-rw`), or an admin API listing. Which is the sanctioned query path, and who runs it? Until this is answered the gate is "unknown", so the flip is blocked.
- `mctl_get_service_logs admins/mctl-api` (6h, 1000 lines) returned zero lines during investigation. Either Loki's selector does not match the `mctl-api` namespace, or ingestion is missing. The boot-line evidence therefore needs `kubectl logs` (operator) or a fixed Loki query. A zero-row result is not evidence.
- Effective `ACTION_APPROVAL_MAX_DECISION_AGE` in gitops is unset, which means 24h. This assumes no other source (envFrom secret, ConfigMap) overrides it. That must be confirmed against the live pod env.
- Negative proof path: is a create call with an unregistered rule an acceptable "non-side-effecting" probe? It is refused before storage, but it does write an audit record. If not, the test-suite evidence (`handlers_approval_governance_test.go`) plus the boot line could stand in. Proceeding on the create-probe interpretation.
- The Helm chart source tracks mctl-api `main` (`targetRevision: main`) while the image is pinned to 4.122.0. Chart drift is unrelated to this flag, but it is recorded as part of the pinned revisions.
