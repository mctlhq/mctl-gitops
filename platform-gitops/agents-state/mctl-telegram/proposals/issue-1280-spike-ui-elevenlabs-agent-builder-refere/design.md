# Design: issue-1280-spike-ui-elevenlabs-agent-builder-refere

## Current state

The spike deliverable already exists. `docs/spikes/assistant-builder-ui-reference.md`
is on main at clone HEAD `82623cde1ad2215b4d07114f4e8960a0798f5014`. Its
sections are:

- 0: evidence limits.
- 1: inventory of `/assistants` and the manage assistant section.
- 2: status map.
- 3: vendor matrix and comparison for ElevenAgents, affectUI and elizaOS.
- 4: prompt / capabilities / effective authority / runtime / approval separation, and the auto / approval / denied derivation.
- 5.1-5.3: wireframe flows A-C with state tables.
- 6: ownership map.
- 7: accessibility and security review.
- 5.4 and 5.5, placed after 7: the authority panel and the First Message definition.
- 8: constraints.
- 9: outcomes, with ITERATE_CURRENT_UI recommended pending the owner, the 9.1 slice and the 9.2 backlog.
- 10: what is missing.

Code facts re-checked at HEAD:

- `cmd/server/main.go:658` mounts `/assistants`. `:680-681` mount
  `POST /telegram/connect/manage/assistant/install|update`. Both match the report.
- `internal/web/assistants.go:189` `Assistants` matches.
- `internal/web/manage_assistant.go:445-446` still renders "Replies on its own"
  from `AutoIntents` in every mode. This is the honesty gap the 9.1 slice
  targets, and it is still present.
- `internal/agent/policy/policy.go:634` `OwnerHoldReasons` exists.
- `internal/config/config.go`: the report cites `:498` for the forks flag. The
  comment is now at `:499`, and the `envBool("ASSISTANT_FORKS_ENABLED", false)`
  default is at `:614`. `ManagedRuntimeEnabled` is at `:504`. So some
  citations have drifted.
- The report's pinned SHA `b341c520...` cannot be resolved in the clone, which
  is shallow with one commit. Its citations therefore cannot be reproduced
  without a fresh pin.
- No other doc covers builder UX. `docs/reports/assistant-runtime-boundary-spike.md`
  covers the runtime boundary. The `docs/*_test.go` guard tests (for example
  `docs/managed_runtime_docs_test.go`) do not reference `docs/spikes/`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - ingress hosts `tg.mctl.ai`, `labs-mctl-telegram.mctl.ai`;
  - `AUTH_MODE: local-jwt` (line 85);
  - `AGENT_ENABLED: "true"` (line 331);
  - no `MANAGED_RUNTIME_ENABLED` and no `ASSISTANT_FORKS_ENABLED` key.
  - So `/assistants` and the manage assistant forms are mounted in production, and forks use the code default (false).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  - host `tg-preview.mctl.ai`;
  - `AUTH_MODE: local-jwt` (line 60);
  - `AGENT_ENABLED: "true"` (line 213);
  - `MANAGED_RUNTIME_ENABLED: "true"` and `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"` (lines 295-296);
  - no `ASSISTANT_FORKS_ENABLED`.
- The tenant is `labs`, taken from the gitops path.
- mctl MCP tools were not called in this run. The live ArgoCD sync state and the
  runtime env therefore went unobserved; the values above are the desired state
  in gitops only. This gap is recorded under Open questions.

## Proposed solution

Make one documentation-only change, to `docs/spikes/assistant-builder-ui-reference.md`,
so that the report is complete and ready for the owner's verdict. The changes
are, in order:

1. **Re-pin.**
   - Replace the "Main source SHA inspected" with a current main SHA.
   - Re-check every `path:line` citation against it and fix the ones that drifted (for example `config.go:498` becomes `:499` and `:614`).
   - Keep the reasoning the same; correct only the locations.
2. **Deployed baseline.** Add a new subsection 1.0 that lists the gitops paths
   above and what they show, as production versus preview. This makes the
   section 2 status map concrete:
   - managed runtime is flag-gated in preview only;
   - forks are off in both by code default;
   - the assistant surfaces are live in both.
   - State explicitly that this is desired state from gitops, not observed runtime.
3. **Evidence closure (section 3.1 and section 10 item 1).**
   - Where network access exists, fetch each vendor URL already listed and record the retrieval date. For GitHub READMEs and LICENSEs, record the commit SHA from `git ls-remote` or the API.
   - Upgrade the rows from "relayed" to VENDOR-DOCUMENTED (own fetch).
   - Actual vendor UI stays UNTESTED, because no vendor account is allowed.
   - Where no access exists, leave the rows as they are and say so.
   - Add no screenshots unless they are public documentation images, cited by URL and date.
4. **Ownership verification (section 6, section 10 item 2).** For each issue
   number, record title and state if `gh issue view` works, or mark it
   "unverified". This covers #1002, #1022, #1026, #1043, #1044, #1046, #1048,
   #1088, mctl-portal#111, .github#261, .github#309 and .github#312.
5. **Structure.**
   - Move 5.4 and 5.5 into section 5, before section 6.
   - Keep the anchors stable where possible, and update the internal "see 5.4/5.5" references.
6. **Decision record (new section 11).**
   - A table of the four verdicts with the recommendation (ITERATE_CURRENT_UI).
   - Blank fields: owner, date, verdict chosen, conditions.
   - The sentence: "Until these fields are filled by the owner in a reviewed commit, no backlog item in 9.2 is authorised and #1280 stays open."
   - An acceptance cross-walk table that maps each acceptance bullet of the original issue and the 2026-11-11 addendum to the section that satisfies it, or to "missing: reason".

The report stays server-rendered-first and framework-free. The 9.1 slice
remains a proposal. Why docs-only: the issue forbids code, and the remaining
gaps are about evidence and governance, not product behaviour.

## Alternatives

- **Implement the 9.1 "Configured authority" slice now** (`internal/web/manage_assistant.go`).
  Dropped. The issue forbids code before the owner signs off, and the report
  itself says the slice is pending the owner. It should become its own issue
  after the decision.
- **Add a `docs/spikes_test.go` guard** that asserts the verdict set and
  "PENDING OWNER" are present. Dropped. It would be the first test over a
  research doc, and the spike's execution boundary excludes test changes. It
  could be revisited if spikes become a recurring doc type.
- **Write a new report from scratch.** Dropped. The existing report already
  meets most of the deliverables and was reviewed and merged. Rewriting it
  would churn reviewed content and risk losing the safety invariants it states.

## Platform impact

- Migrations: none. Backward compatibility: not applicable. Resource impact:
  none. No deploy is triggered beyond the normal release-please flow for a
  docs commit.
- Risk: the corrected citations could themselves be wrong. Mitigation: check
  every citation mechanically against the pinned SHA (task 1).
- Risk: if fetched vendor content is phrased as fact, it could be read as an
  implementation mandate. Mitigation: keep the VERIFIED / VENDOR-DOCUMENTED /
  UNTESTED labels and section 8's "no vendor dependency" constraints.
- Risk: the decision record could be filled by an agent. Mitigation: the
  fields ship blank, and the PR must not set them. Only the owner edits them,
  in a separate reviewed commit.
- Privacy: the doc must not include real Telegram identifiers, prompts, owner
  notes or account data (CLAUDE.md safety rules).
