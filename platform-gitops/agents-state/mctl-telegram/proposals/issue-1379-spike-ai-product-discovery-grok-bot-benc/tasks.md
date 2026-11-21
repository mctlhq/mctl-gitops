# Tasks: issue-1379-spike-ai-product-discovery-grok-bot-benc

These tasks are docs-only. No task starts before the owner approves this proposal, and the intake alone authorizes nothing.

- [ ] 1. Pin the baseline: record the mctl-telegram SHA and the mctl-gitops state. Then write section 1 of `docs/spikes/pa-grok-town-benchmark.md`, the MCTL baseline table. Its rows are consent, private-chat ingress, the 24 h TTL, `/new`, `/forget`, `/consent`, linking OAuth, the connector executor, audit, egress, taint, budgets, allowlist and switches. Each row is classified merged, deployed, flagged, tested or planned and cites `internal/pa/*`, `internal/config/config.go`, `docs/adr/0011-personal-assistant.md`, the threat model, the S1 and S2 manifests, and the gitops `values.yaml`. — DoD: every row has a path and a label, and no internal identifier, Vault path or account id appears.
- [ ] 2. Vendor benchmark: fetch the six URLs in the issue, read-only, with no login. Fill the 15-dimension matrix for Townie and Grok Bot, and record the access date per source. — DoD: every cell is `VENDOR-DOCUMENTED` with a quote and URL, or `UNTESTED`, `NOT-IMPLEMENTED` or `UNKNOWN`. Custom MCP authentication is quoted verbatim or marked `UNKNOWN`.
- [ ] 3. Interop matrix (depends on 1, 2): four rows, Grok Bot and Townie against `tg` and `alice`. The `tg` columns come from `internal/oauth/server.go`, `scopes.go`, `cimd_client.go`, `internal/toolprofile/toolprofile.go`, `cmd/server/main.go` and the gitops values. The `alice` columns come from the mctl-alice repo, or are marked `UNKNOWN`. — DoD: every column from work package 3 is filled or marked `UNKNOWN`, and each required admission or policy change is listed as an owner decision, not a recommendation to apply.
- [ ] 4. Reproducible test plan (depends on 3): scripted against `tg-preview.mctl.ai` with a synthetic or approved isolated account.
  - Positive steps: discovery, registration, PKCE with `resource`, `initialize`, `tools/list`, and `get_my_identity`.
  - Negative steps: a scope outside the ceiling, a revoked token, a wrong audience, a redirect not on the allowlist, a profile-excluded tool, and code reuse.
  - Vendor-driven steps are in a separate section that needs owner approval.

  — DoD: each step has its preconditions, its exact request shape, its expected status or error, and its expected audit entry. Every step is marked `NOT-EXECUTED`.
- [ ] 5. Meetup pack (depends on 1, 2): the pitch (60-90 s), a synthetic storyboard (Alice, Bob, Carol, Dana), the interop demo plan, an interview script for 5-10 voluntary interviews with a consent line, and an anonymized findings template. Confirm the meetup date with the organizer, or record it as unconfirmed. — DoD: the template has no PII or chat-content field, and the findings section contains no results.
- [ ] 6. Hypotheses and metrics (depends on 1-3): 3-5 hypotheses, each with the user job, evidence class, ICE, success and failure metrics, dependencies, the smallest experiment, cost and security implications, and its owning issue (#1325, #1048, #1088 or #1280). Define activation, D7, task success, cost per successful task, approval and denial rates, and retention and privacy limits. — DoD: no hypothesis proposes new infrastructure outside its owning issue.
- [ ] 7. Decision and handoff (depends on 6): one of PA_FIRST, MCP_DISTRIBUTION_FIRST, DUAL_TRACK_BOUNDED or DEFER, with its rationale, the next owner decision, and the PDLC handoff chain. Status PROPOSED, `Refs #1379`. — DoD: an independent reviewer has signed off before owner approval, and no HOLD or gate text is changed.

## Tests

- [ ] T1. `git diff --stat` for the report PR touches only `docs/spikes/pa-grok-town-benchmark.md`.
- [ ] T2. `go test ./docs/...` still passes. The PA manifest tests and the runbook and troubleshooting tests are unaffected.
- [ ] T3. `git grep` over the new file finds no numeric Telegram id taken from gitops, no Vault path, no Cloudflare account id and no real handle. Only the personas Alice, Bob, Carol and Dana appear.
- [ ] T4. Every claim line carries one of the evidence labels. A reviewer checks every `VENDOR-DOCUMENTED` cell against its URL and date.
- [ ] T5. Every test in the plan reads `NOT-EXECUTED`, and the findings template is empty.

## Rollback

The change is docs-only. Revert the report commit, or close the PR unmerged. No runtime, flag, OAuth or gitops state is touched, so nothing else needs to be undone.
