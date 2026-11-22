# Tasks: issue-1398-spike-pa-natural-language-workflow-disco

All tasks are research and documentation only. Each produces a section of `docs/spikes/pa-workflow-discovery.md`, delivered as one docs-only PR. No runtime code, flags, deployments or real data are involved.

- [ ] 1. Pin the baseline: record the mctl-telegram SHA and the mctl-gitops SHA, then build an inventory table covering the PA, the Catalog, the managed runtime, automation and memory, labelled VERIFIED_CODE / VERIFIED_DEPLOYMENT / DESIGNED_ONLY / UNKNOWN. Cite:
  - `internal/pa/context.go`, `runloop.go`, `jobs/jobs.go`, `connector/`, `catalog/pin.json`, `memory.go`;
  - `internal/assistant/`, `internal/digest/digest.go`;
  - the S1 and S2 manifests;
  - the gitops `services/labs/mctl-telegram{,-preview}/values.yaml`.

  DoD: every row has a label and a citation, and every unreadable source is UNKNOWN with a reason.
- [ ] 2. Verify the VECTOR primary source (the original post and any linked material) and record its exact claims, or mark them UNKNOWN. DoD: no claim rests on an unverified summary.
- [ ] 3. Draw the relationship diagram: PA, Catalog, the #318 trigger authority, `mctl-agents`, the managed runtime and the MCP servers (depends on 1). DoD: every edge is labelled with its owner issue and evidence label.
- [ ] 4. Write the product model and Telegram storyboard (request -> draft -> preview -> synthetic dry run -> callback activation -> receipts -> feedback -> edit, pause or revoke), and compare conversational creation with the #1280 builder (depends on 1). DoD: every step names the existing PA mechanism it reuses, or is marked as a gap.
- [ ] 5. Analyse the "unanswered" semantics against the `telegram.Message` fields and the pinned `tg` tools, and propose the honest framing plus any pin change it would need (depends on 1). DoD: the heuristic's failure modes are listed, and no reliability claim is made.
- [ ] 6. Write the options matrix (PA_EXTENSION, CATALOG_COMPOSER, BOUNDED_HYBRID, DEFER) with owners and build-vs-reuse evidence, plus the recommendation (depends on 3, 4). DoD: the matrix agrees with design.md (research BOUNDED_HYBRID, build DEFER until the gates are met).
- [ ] 7. Write the proposed `pa-workflow/v1alpha1` spec, the activation receipt, the revalidation list, idempotency, retries and unknown outcomes, pause, the kill switch, revoke and delete, all marked "proposed, not production" (depends on 6). DoD: every field maps to an existing binding (`authority_revision`, pin hashes, consent version) or is flagged new.
- [ ] 8. Write the negative-test matrix and the synthetic Daily Brief fixture design, using the personas Alice, Bob, Carol and Dana (depends on 7). DoD: every case in issue #1398 is present, and each is marked UNTESTED.
- [ ] 9. Write the staged experiment, metrics, hypotheses, ranked alternative jobs and cost formula, and one bounded next owner decision (depends on 7, 8). DoD: there are no invented thresholds, and the hypotheses are falsifiable.
- [ ] 10. Open the docs-only PR and request an independent review (depends on 1-9). DoD: the PR description states that it carries no approval and no implementation, and the review is requested from the #1048 security owner and the PA owner.

## Tests

- [ ] T1. Every capability claim in the report has an evidence label and a citation. Checked manually by the reviewer.
- [ ] T2. Search the report for real Telegram identifiers or names. It must contain only synthetic personas, and none of the numeric ids found in the gitops values.
- [ ] T3. Every negative-test row is marked UNTESTED, and no row claims to have been executed.
- [ ] T4. The report proposes no in-process scheduler, new runtime, new MCP auth layer or memory database, and no write tool in the workflow contract.
- [ ] T5. `go test ./docs/...` still passes, so the manifest and doc tests are unaffected by the new spike file.

## Rollback

The spike adds only a markdown document, so revert the docs PR to roll back. No flags, data, deployments or runtime behaviour change, so nothing else needs undoing.
