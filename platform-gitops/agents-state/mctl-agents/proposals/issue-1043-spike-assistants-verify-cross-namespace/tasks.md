# Tasks: issue-1043-spike-assistants-verify-cross-namespace

- [ ] 1. Version inventory — record pinned versions with source and commit: server 1.31.0 / chart 1.2.0 (`platform-gitops/bootstrap/templates/data/temporal.yaml`), admin-tools 1.31.0 (`infra-components/data/temporal/tenant-namespace-job.yaml`), `temporalio==1.34.0` and `nexus-rpc==1.4.0` (`pyproject.toml`, `uv.lock`), mctl-agents image 1.117.0 (`services/admins/mctl-agents-worker/values.yaml`), mctl-api 4.154.0 and its Go SDK version from mctl-api `go.mod` at a pinned commit (or `not-observed`). — DoD: "Environment and versions" section of `docs/spikes/1043-cross-namespace-dispatch.md` lists each with a label `verified`/`assumed`/`not-observed`.
- [ ] 2. Nexus gate evaluation N1-N7 (depends on 1) — read upstream server source/release notes at tag v1.31.0, chart 1.2.0 values, Python SDK 1.34.0 and the pinned Go SDK; answer each gate in a table with evidence links. No live namespace or endpoint is created. — DoD: every gate has a verdict and citation; no gate is marked verified without a source.
- [ ] 3. Local disposable verification plan (depends on 2) — write exact reproduction steps (`temporal server start-dev` at 1.31.x, two namespaces, one endpoint, a caller in a third namespace attempting the endpoint) for any gate left `not-observed`. Run them only if the issue owner explicitly authorizes it on the issue; otherwise mark not run. — DoD: steps in the memo; run/not-run stated.
- [ ] 4. Decision (depends on 2, 3) — apply the decision rule from design.md and set the memo's first line to `STATUS: <OUTCOME>`, one of `NEXUS_VERIFIED`, `API_BRIDGE_SELECTED`, `BLOCKED_NEEDS_SDK_OR_SERVER_UPGRADE`, `DEFER`. — DoD: exactly one outcome, justified by gate results.
- [ ] 5. Contract schemas (depends on 4) — write `docs/spikes/1043/command.schema.json` and `docs/spikes/1043/result.schema.json` (JSON Schema 2020-12, `additionalProperties: false`, bounded strings, opaque ref patterns, `aar_` required for mutation kinds) and fixtures under `docs/spikes/1043/fixtures/` (valid, extra-field, raw-secret-shaped field, missing approval on mutation, expired TTL > 15 min, bad ref pattern). If the outcome is `NEXUS_VERIFIED`, the same schemas define the Nexus operation input/output. — DoD: schemas and fixtures committed.
- [ ] 6. Call diagram, failure/retry/cancellation matrix, denial-test plan D1-D12, ownership map, migration/rollback and cost (depends on 4) — in the memo, consistent with design.md. — DoD: each section present; denial tests name the exact RPC or route and expected answer.
- [ ] 7. Offline test (depends on 5) — `tests/test_spike_1043_contracts.py`: validates each fixture against its schema (valid passes, each negative fails for the expected reason), asserts the memo's status line is one allowed outcome, and asserts no fixture contains `MCTL_TOKEN`, `Bearer ` or a JWT-shaped string. Use a required `import jsonschema` and fail CI if it is missing (pin/update the test dependency if needed, under review). — DoD: `uv run pytest tests/test_spike_1043_contracts.py` passes offline; `ruff` clean.
- [ ] 8. Follow-up issue drafts (depends on 4) — in the memo, list the separate later issues (mctl-api bridge routes and outbox, mctl-agents control workflow, provider worker, gitops namespaces/identities after #2456), each needing its own approved DevLoop proposal. — DoD: list present; nothing filed or implemented here.
- [ ] 9. PR — open the documentation PR with `Refs mctlhq/mctl-agents#1043` (never `Closes`, per `orchestrator/spike_issue.py`). — DoD: PR open; issue stays open for the owner's verdict.

## AMEND 2026-11-08 — mandatory integrity checks

- [ ] A1. Source-backed Temporal scope/role examples use `temporal-system:admin`, not `system:admin`, and assertions cover a negative invalid-scope JWT.
- [ ] A2. Offline JSON Schema tests MUST NOT be skipped if `jsonschema` is unavailable: pin or explicitly require the dependency and fail CI with installation instructions. A green run must execute at least one positive and all negative fixtures, with case counts.
- [ ] A3. The implementation remains a docs/schemas/contract-tests-only spike. Any separate dependency/lock update requires review; this does not authorize Nexus endpoints or real bridge operations.

## Tests

- [ ] T1. Valid command and result fixtures validate against their schemas.
- [ ] T2. A command with an undeclared field (for example `glovo_session_cookie`) is rejected.
- [ ] T3. A mutation command (`place_order_fake`) without `approval_ref` is rejected.
- [ ] T4. A ref not matching the opaque pattern (for example a raw email) is rejected.
- [ ] T5. A string over its `maxLength` is rejected.
- [ ] T6. The memo's first status line is one of the four allowed outcomes.
- [ ] T7. No fixture or memo text contains a credential-shaped value.

## Rollback

Documentation-only change: revert the PR (memo, `docs/spikes/1043/`, `tests/test_spike_1043_contracts.py`). No namespace, endpoint, secret, permission or runtime configuration is touched, so nothing else needs to be undone. If the decision is later overturned, a new spike revision supersedes the memo; the schemas are `v1alpha1` and are not consumed by any service.
