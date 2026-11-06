# Tasks: issue-314-spike-evaluate-dapr-as-an-optional-secur

- [ ] 1. Pin evidence: record 40-hex commits of mctlhq/.github, mctl-gitops and any of mctl-api, mctl-agents, mctl-telegram that can be read. Record the Dapr runtime and Dapr Agents versions, the URLs and read date of the cited Dapr pages, and re-run the read-only MCTL checks (`mctl_list_services`, `mctl_get_service_config` where applicable). DoD: an evidence-pin table in `docs/spikes/dapr-mctl.md`, with every unreadable source listed as `unknown (not observed)`.
- [ ] 2. (depends on 1) D1 trust-boundary diagram (Mermaid) and D2 capability/duplication matrix. Cover every boundary named in requirements.md, cite files such as `infra-components/data/temporal/networkpolicy.yaml`, `helm-charts/tenant/templates/networkpolicy.yaml`, `.../mctl-agents-egress-proxy/networkpolicy.yaml`, `docs/plans/mcp-gateway.md` and `docs/spikes/mcp-gateway-g0.md`, and classify each row. DoD: every row has a citation, an owner and one of the four classifications, with no generic Dapr feature list.
- [ ] 3. (depends on 2) D3 H1 analysis: ACL match semantics against the MCP JSON-RPC body, per-tool mediation placement, identity/tenant binding, bypass and spoofing. DoD: states explicitly that App-ID ACL is not per-tool authorization, names the per-tool decision point in each option, and gives an H1 verdict with prerequisites and no-go conditions.
- [ ] 4. (depends on 2) D4 H2 adapter contract sketch and MCTL-to-Dapr state mapping table. DoD: covers submit, status/stream, cancel, retry/idempotency, tenant/principal propagation, approval check, caps and evidence refs, and every unmappable state has an unsupported-case entry and an abort condition. H2 verdict given.
- [ ] 5. (depends on 2) D5 H3 actors evaluation. DoD: reference-only unless evidence is cited, with an explicit statement that an actor is not a process boundary.
- [ ] 6. (depends on 3, 4) D6 threat model with a paired allow/deny refusal-test plan, including both mandatory proofs. DoD: every allow row has at least one deny row, each row names the enforcing component and the observable used to pass or fail it.
- [ ] 7. (depends on 6) D7 disposable experiment design, baseline-first benchmark plan with pre-registered thresholds, and operability estimate. DoD: thresholds are labelled "proposed, to be agreed", the environment is explicitly a throwaway cluster, and no measured number appears.
- [ ] 8. (depends on 3-7) D8 owner decision table, verdicts (H1, H2, H3, overall from the five outcomes), recommended next small action or explicit no-action, and Limitations. DoD: the verdict section says "proposed, not approved", and no follow-up issue is opened.
- [ ] 9. Add `roadmap/spikes/dapr-mctl.yaml` (`lifecycle: proposed`, outcomes `ADOPT_BOUNDARY`, `ADOPT_ADAPTER`, `ADOPT_BOTH_OPTIONAL`, `REFERENCE_ONLY`, `NO_GO`, issue mctlhq/.github#314, `execution.devloop: true`, `evidence.report: docs/spikes/dapr-mctl.md`, no `decision`, no `epic`) and the `AGENTS.md` index entry under `# Spikes`. DoD: `python roadmap/scripts/validate.py` and `python -m pytest roadmap/tests` pass.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py` exits 0 with the new manifest, and `roadmap/tests/test_validate_spike.py::test_committed_corpus` passes.
- [ ] T2. Report lint check (manual review checklist): every claim carries an evidence tag; every pin is 40-hex or a versioned Dapr doc with a date; no secret values, tokens or payloads are quoted.
- [ ] T3. The refusal-test plan in D6 contains a paired deny for each of: cross-app caller, cross-tenant replay, revoked grant, direct endpoint bypass, unauthorized tool on an allowed App-ID, replay, malformed or forged context, sidecar down, retry/duplicate delivery, and compromised caller sidecar.
- [ ] T4. The plan contains mandatory proof A (an MCTL denial of a forbidden write with the Dapr ACL allowing the App-ID; observable: 403 from the MCTL check and no side effect on the write stub) and proof B (a Dapr ACL denial of an unapproved App-ID; observable: denial at the sidecar and a handler invocation counter of 0).
- [ ] T5. The H2 mapping table lists at least the lease/fencing epoch, exactly-once grant spend, the "unknown outcome needs reconciliation" case, and agent tool calls outside the policy checkpoint, each as supported or unsupported with an abort condition.
- [ ] T6. Consistency check: the H1, H2 and H3 verdicts, the overall outcome and the manifest outcomes use the same vocabulary, and the manifest has no `decision` block.

## Rollback

Documentation only. Revert the commit that adds `docs/spikes/dapr-mctl.md`,
`roadmap/spikes/dapr-mctl.yaml` and the `AGENTS.md` line. No runtime, gitops or
cluster state is touched, so nothing else needs undoing. If the owner rejects
the spike instead, set `lifecycle: archived` in the manifest rather than
deleting the report.
