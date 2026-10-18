# Tasks: issue-182-spike-evaluate-mctl-governance-beyond-hu

- [ ] 1. Pin the evidence base: record the main SHAs of mctlhq/.github, mctl-api, mctl-agents and mctl-gitops, and the deployed tags of mctl-api and the mctl-agents workers (gitops values, plus `mctl_get_service_config` / `mctl_get_service_status` where available), and set the audit date. — DoD: the "Audit method and pinned revisions" table exists in `docs/spikes/agent-governance-decision-assurance.md`, and any unobservable source is stated as such.
- [ ] 2. Build the path inventory P1-P7 (DevLoop approval, direct mctl-agents-approve, capability gateway invoke, incident-responder auto-accept and incident-resolve, commerce invocation, MCP platform operation, delegated WorkItem execution), and list excluded paths with reasons (depends on 1). — DoD: each path names its entry point, its components and the code or contract files at the pinned SHAs.
- [ ] 3. Write the D1 Mermaid sequence diagrams per path, with trust boundaries, the identity carried, the evidence persisted, and implemented steps marked apart from planned ones (depends on 2). — DoD: every arrow is backed by a cited file, test or contract, and the actual evaluation order is stated.
- [ ] 4. Write the dimension sections for scope items 1-8 (intent provenance; identity and authority, including revalidation at execution and caller-supplied strings such as the approve CWFT `approver`; policy evidence, name versus version; decision context classified as present, missing or UX-only per path; approval integrity per trust boundary; end-to-end trace with durable IDs versus sampled spans; reject, override, escalation and break-glass; governance metrics and instrumentation limits on top of the #55 primitives) (depends on 3). — DoD: each section ends with gaps that carry owners.
- [ ] 5. Write the D2 capability matrix with per-path status for the 13 minimum rows, using only the statuses implemented, partial, missing, owned-by-another-epic or `unknown (not observed: reason)` (depends on 4). — DoD: no row claims `implemented` for paths other than those its evidence covers, and #681 is credited to P1 only unless other paths are proven.
- [ ] 6. Write the D3 F1-F10 table with the current behaviour per path, the desired invariant, the evidence (an existing test path@SHA or a bounded non-production reproduction), the gap, the owner and an optional candidate AssuranceScenario for #151 (depends on 4). — DoD: all ten rows are filled, and unverifiable rows are marked unverified with the reproduction they would need. No production side effects.
- [ ] 7. Write D4: map each GovernedDecision field to an existing contract (mctl-api#572 identity evidence, ActionApprovalRequest artifact_hash/intent_hash, WorkItem execution and execution requests, InvocationRecord, commerce receipt, usage ledger, #55 trace id) or mark it new with a reason; specify append-only references for approvals, attempts, evaluations and steps; and define retention, access and redaction (depends on 5, 6). — DoD: no field is left unmapped or without a reason, and the section states that stored authority claims are not authorization.
- [ ] 8. Write D5: exactly one disposition, plus a routing table (Gap | Owner component | Owner epic | Draft follow-up with evidence, scope and acceptance criteria) and the parent #181 disposition with an explicit non-claim (depends on 5, 6, 7). — DoD: every gap from D2 and D3 appears exactly once, and no follow-up issue numbers are invented.
- [ ] 9. Update `roadmap/epics/agent-governance-decision-assurance.yaml` to match D5: `lifecycle: archived` with a header comment that points at the report (EXTEND EXISTING / NO NEW EPIC), or a refined set of phases, work items for existing issues only, and a `dependsOn` DAG (CREATE NEW EPIC). Keep the non-claim in successCriteria (depends on 8). — DoD: `python3 roadmap/scripts/validate.py roadmap/epics` passes.
- [ ] 10. Add the report to `AGENTS.md` next to the Agent Commerce entry (depends on 1). — DoD: the link resolves.

## Tests

- [ ] T1. `python3 -m pip install -r roadmap/requirements.txt && python3 roadmap/scripts/validate.py roadmap/epics` passes after the manifest edit.
- [ ] T2. `python3 -m pytest roadmap/tests .github/tests` passes unchanged.
- [ ] T3. Content check of the report: D1-D5 headings are present; D2 has at least the 13 named rows with five columns; D3 has rows F1-F10; D5 contains exactly one of "NO NEW EPIC", "EXTEND EXISTING" or "CREATE NEW EPIC" as the stated disposition.
- [ ] T4. Every Mermaid block renders (GitHub preview or `mmdc` locally).
- [ ] T5. Every cited code reference is a pinned-SHA link or a path qualified by a SHA in the revisions table. No secrets, tokens or tenant payloads appear in the report.

## Rollback

The change is documentation plus one manifest field. Revert the PR. That
restores `roadmap/epics/agent-governance-decision-assurance.yaml` to
`lifecycle: proposed`, and the next `roadmap-publish.yml` run republishes the
previous state. No runtime component is touched, so nothing else needs to be
rolled back.
