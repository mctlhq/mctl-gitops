# Spike: cross-namespace Nexus versus an authenticated mctl-api command bridge for deployable Glovo M1

## Context

ADR 0010 and the merged runtime report (mctlhq/mctl-telegram#1225, proposal `issue-1225-spike-runtime-choose-shared-assistant-pr`) define two independent Temporal namespaces: trusted control `mctl-assistants` and low-trust provider `mctl-assistants-provider-glovo`. The report left the dispatch transport between them open, and states "Without verified bridge: hold runtime activation". An ordinary Temporal Activity is a task in its own workflow's namespace and cannot run in another, so control needs either Temporal Nexus (a cross-namespace operation through a registered endpoint) or a control-plane-owned mctl-api command/results bridge. The provider must never get start/signal/query/list/terminate authority on `mctl-assistants` or on the DevLoop namespace `mctl-agents`.

This spike is research and documentation only. It produces a version-pinned decision memo in `docs/spikes/` of mctl-agents, with exactly one outcome: `NEXUS_VERIFIED`, `API_BRIDGE_SELECTED`, `BLOCKED_NEEDS_SDK_OR_SERVER_UPGRADE` or `DEFER`. It also produces machine-checkable contract schemas for the bridge, a call diagram, a failure/retry/cancellation matrix, a denial-test plan and an ownership map. Implementation, namespace creation, secrets and rollout belong to later, separately approved issues.

## AMEND 2026-11-08 — role spelling and mandatory non-skipped schema validation

- The stock Temporal system scope in ADR 0003 is `temporal-system:<role>`, e.g. `temporal-system:admin`, **not** `system:admin`. Nexus operator test data must use correct claims and clearly label candidate permissions until verified in server 1.31.0.
- The JSON Schema contract validation test is a **required gate**, not an optional smoke. If the `jsonschema` library is absent in the CI test environment, **fail with an actionable dependency error**, or explicitly add/pin it in the test dependency group under a separately reviewed project change; never return a green suite through `pytest.importorskip`. Positive and negative fixtures must actually be executed and counted in CI.
- These corrections remain documentation/contract-test only. No Temporal namespace/client auth change, bridge code or deployment is authorized.

## User stories

- AS the platform owner I WANT one selected, source-backed cross-namespace transport SO THAT the M1 provider worker is not designed on an unverified or insecure dispatch path.
- AS a security reviewer I WANT version-pinned evidence that separates verified facts from assumptions SO THAT I can approve or reject the transport without re-doing the research.
- AS the later implementer I WANT exact command/result schemas, an ownership map and a failure matrix SO THAT the M1 build is mechanical and its denial tests are known in advance.
- AS an operator I WANT a migration, rollback and cost note SO THAT adopting (or later swapping) the transport is reversible.

## Acceptance criteria (EARS)

- WHEN the spike is complete THE SYSTEM SHALL contain `docs/spikes/1043-cross-namespace-dispatch.md` whose first status line names exactly one of `NEXUS_VERIFIED`, `API_BRIDGE_SELECTED`, `BLOCKED_NEEDS_SDK_OR_SERVER_UPGRADE`, `DEFER`.
- WHEN the memo states a fact about a version, configuration or API THE SYSTEM SHALL cite the pinned source (gitops path and commit, lockfile entry, upstream tag or release note URL) and label it `verified`, `assumed` or `not-observed`.
- THE memo SHALL pin at least: Temporal server 1.31.0 and chart 1.2.0 (`platform-gitops/bootstrap/templates/data/temporal.yaml`), admin-tools 1.31.0, Python SDK `temporalio==1.34.0` with `nexus-rpc==1.4.0` (`pyproject.toml`, `uv.lock`), the deployed mctl-agents image 1.117.0, and the mctl-api Go SDK version (or record it as `not-observed`).
- WHEN the Nexus option is evaluated THE SYSTEM SHALL answer each Nexus gate (N1-N7 in design.md) with evidence: OSS availability and enablement on 1.31.0, endpoint registry and routing, who may create endpoints, whether a caller namespace can be restricted per endpoint in OSS, worker SDK support (Python and Go), cancellation, retry and error propagation, and the callback/HTTP address requirements.
- IF any Nexus gate N1-N5 is unverified or fails THEN THE SYSTEM SHALL NOT select `NEXUS_VERIFIED`.
- WHEN `API_BRIDGE_SELECTED` is chosen THE SYSTEM SHALL provide JSON Schemas `docs/spikes/1043/command.schema.json` and `docs/spikes/1043/result.schema.json` with `execution_id`, opaque `tenant_ref`/`principal_ref`/`order_ref`/`connection_ref`, issuer and worker identity, `nonce`, `issued_at`/`expires_at`, `command_id` dedupe key, attempt, cancellation and an `aar_` approval reference.
- THE schemas SHALL reject any field not declared (`additionalProperties: false`) and SHALL bound every string length, so raw customer or provider secrets have no slot.
- WHEN a provider mutation is described THE SYSTEM SHALL specify that the `aar_` receipt is consumed once, at the provider fake mutation, through mctl-api's consume route, and that a second consume yields zero additional provider writes.
- THE memo SHALL contain a denial-test plan proving the provider identity cannot start, signal, query, list, terminate or describe any workflow in `mctl-assistants` or `mctl-agents`, cannot forge tenant context, and that a duplicate callback or a stale approval produces zero additional provider writes.
- THE memo SHALL contain an ownership map: mctl-api is the only client for start/signal/query/list and the only user/tenant/approval authority; mctl-agents owns trusted control orchestration; the provider worker runs in its own namespace with its own identity; the MCP facade holds no Temporal credentials.
- WHILE the spike runs THE SYSTEM SHALL NOT create live Temporal namespaces or endpoints, add secrets, change production Temporal configuration, call a hosted Glovo API, or change permissions.
- IF a local disposable Temporal test is not explicitly authorized on the issue THEN THE SYSTEM SHALL record the corresponding gate as `not-observed` with the exact reproduction steps rather than run it.
- WHEN the memo is merged THE SYSTEM SHALL leave the issue open (spike rule, `orchestrator/spike_issue.py`): the PR uses `Refs`, not `Closes`, and the owner records the verdict.
- THE offline test `tests/test_spike_1043_contracts.py` SHALL validate positive and negative fixtures against the schemas without network access.

## Out of scope

- Any implementation of the bridge, a Nexus handler, a provider worker or the MCP facade.
- Creating `mctl-assistants` or `mctl-assistants-provider-glovo` namespaces, Nexus endpoints, Vault roles or secrets.
- Enabling Temporal TLS or the authorizer (that is mctl-gitops#2456 and its follow-up slices).
- Any hosted Glovo API, real customer credentials, DNS/TLS/OAuth for the facade.
- Merge, deploy or activation; the decision on #324 runtime ownership.

## Open questions

- The mctl-api Temporal Go SDK version and its Nexus support are not observable from this clone (mctl-api source is not checked out here). The implementer must read mctl-api `go.mod` at a pinned commit; if unavailable, record `not-observed`.
- The live Temporal server image and dynamic config are not observed (no access to the `temporal` namespace). GitOps declares 1.31.0 with no `dynamicConfig` block; the live value may differ.
- Whether a local disposable Temporal dev server test is authorized. The issue says "only if explicitly allowed"; this proposal assumes it is NOT allowed and plans the steps as reproducible-but-not-run.
- Whether OSS 1.31.0 can restrict which caller namespaces may target a Nexus endpoint. Temporal Cloud documents endpoint allowlists; for OSS this is assumed to require a custom Authorizer until proven otherwise. This is the most likely deciding fact.
- ADR 0010 lives in mctl-telegram and is not in this clone; the memo cites it by issue reference only.
