# Close out the #1280 Assistant Builder UI reference spike (deployed baseline, evidence gaps, decision record)

## Context

Issue #1280 is a research-only UI/UX spike. It compares ElevenLabs ElevenAgents
and two extra references (affectUI as UI patterns, elizaOS as app/catalog UX)
against the current tg.mctl.ai Assistants surfaces. It must end in a decision
report that picks ITERATE_CURRENT_UI, BOUNDED_BUILDER, FULL_STUDIO_LATER or
DEFER, and that verdict needs the owner's sign-off. No code, deployment, vendor
account, paid licence or Telegram send is allowed.

Most of that report has already merged as
`docs/spikes/assistant-builder-ui-reference.md` (628 lines). It covers the
MCTL inventory, a status map, the vendor matrix, the authority separation,
wireframe flows A-C, the ownership map, an accessibility/security review, the
outcomes table with ITERATE_CURRENT_UI recommended pending the owner, and a
prioritised backlog. By its own section 10 it is unfinished:

- The vendor evidence is paraphrases relayed from unpinned `main` branches.
- The issue numbers in the ownership map were never verified.
- The deployed state of tg.mctl.ai and tg-preview.mctl.ai was never checked.
- There is no place to record the owner's sign-off.
- It cites a SHA (`b341c520`) that cannot be reproduced from a shallow clone.
- Sections 5.4 and 5.5 sit after section 7, out of order.

This proposal closes those gaps with documentation changes only, so that the
owner can give a verdict on the exact content.

## User stories

- AS the product owner I WANT a complete, internally consistent decision report with a sign-off block SO THAT I can approve, change or defer the recommendation without re-running the research.
- AS a reviewer I WANT every MCTL claim pinned to a reproducible commit and to the real deployed flags SO THAT I can tell shipped features from flag-gated and planned ones on tg.mctl.ai and tg-preview.mctl.ai.
- AS a future implementer of any slice I WANT each control mapped to a verified field/API or marked REQUIRES NEW CONTRACT with an owner SO THAT no UI-only toggle is mistaken for authority.

## Acceptance criteria (EARS)

- WHEN the report is updated THE SYSTEM SHALL change only `docs/spikes/assistant-builder-ui-reference.md`, and no Go, template, schema, config, workflow or gitops file.
- WHEN the report cites a source line THE SYSTEM SHALL pin it to a commit SHA that exists on `mctlhq/mctl-telegram` main at writing time, and every `path:line` citation SHALL be re-checked against that SHA. Example of drift found at HEAD `82623cd`: the doc says `config.go:498` for the forks flag, but the source is now at `:499` and `:614`.
- WHEN the report describes deployed behaviour THE SYSTEM SHALL include a "Deployed baseline" subsection naming the gitops paths it read and what they show:
  - production `labs/mctl-telegram`: hosts tg.mctl.ai and labs-mctl-telegram.mctl.ai, `AUTH_MODE=local-jwt`, `AGENT_ENABLED="true"`, `MANAGED_RUNTIME_ENABLED` not set.
  - preview `labs/mctl-telegram-preview`: tg-preview.mctl.ai, `AUTH_MODE=local-jwt`, `AGENT_ENABLED="true"`, `MANAGED_RUNTIME_ENABLED="true"`, `MANAGED_RUNTIME_MAX_ACCOUNTS="1"`.
  - `ASSISTANT_FORKS_ENABLED` not set in either, so it uses the code default of false.
- IF a value is absent from values.yaml THEN THE SYSTEM SHALL state the code default and the file it comes from. The report SHALL NOT say "disabled" unless the default is known.
- IF a source (vendor page, GitHub issue, live page) could not be read THEN THE SYSTEM SHALL label the claim UNKNOWN or UNTESTED and list it under "What is missing". It SHALL NOT be presented as absent.
- WHEN vendor evidence is fetched by the author THE SYSTEM SHALL record the URL, retrieval date and (for GitHub sources) the pinned commit SHA, and label each claim VERIFIED, VENDOR-DOCUMENTED or UNTESTED. Relayed paraphrases that were not re-fetched SHALL stay labelled as relayed.
- WHEN the ownership map (section 6) lists an issue number THE SYSTEM SHALL mark it either verified (title and state checked on GitHub, with date) or unverified.
- THE SYSTEM SHALL add a "Decision record" section with:
  - the four-option verdict set;
  - the recommended option (ITERATE_CURRENT_UI);
  - empty owner, date and chosen-verdict fields;
  - the statement that no implementation starts until those fields are filled by the owner.
- WHILE the decision record is unsigned THE SYSTEM SHALL keep the report status "PROPOSED" and keep every backlog item marked "not authorised".
- WHEN the report is restructured THE SYSTEM SHALL renumber sections so that 5.4 and 5.5 sit inside section 5. Content SHALL be moved, not reworded, except where a citation is corrected.
- THE SYSTEM SHALL keep the existing safety invariants of the report unchanged:
  - no First Message as unsolicited outreach;
  - test mode never sends;
  - configured settings are not effective authority;
  - approvals go only through `executor.Approve`/`Reject` after `policy.Evaluate`;
  - the web never renders instructions, owner notes or values.

## Out of scope

- Any code, template, test, schema, dependency or configuration change, including the 9.1 "Configured authority" slice. That slice needs a separate, owner-approved issue.
- Creating vendor accounts, paying for licences, live vendor UI walk-throughs that need a login, and installing React or affectUI/elizaOS components.
- Any Telegram send, assistant activation, or change to mctl-gitops.
- Re-deriving the runtime boundary (`docs/reports/assistant-runtime-boundary-spike.md`). Also out of scope is the work owned by #1088, #1046, #1048, #111, #261, #309 and mctlhq/.github#312.
- Closing #1280. The PR text says "Refs #1280", because closure needs the owner's verdict.

## Open questions

- Who signs the decision record? The issue says "explicit owner sign-off" but names no person. The proposal leaves the field for the repo owner (CODEOWNERS).
- Does the implementer's environment have network access for pinned vendor fetches and GitHub issue lookups? If not, those rows stay UNKNOWN or unverified, and section 10 says so. That is acceptable, but the vendor comparison then stays explicitly unfinished.
- Should production `MANAGED_RUNTIME_ENABLED` be confirmed live through `mctl_get_service_config`? This run read gitops only. The live config was not observed.
