# Spike: Finance Assistant owner-private delivery and CSV feasibility (L2 discovery, research only)

## Context
Issue mctlhq/mctl-telegram#1240 asks a bounded discovery question: can the existing
MCTL Assistant Catalog and the owner-facing Saved Messages control path (#297, #354)
safely carry a private, read-only Finance Assistant digest built from synthetic or
CSV-derived data, without generic peer auto-replies, a new identity system or live
financial integrations? The answer must be one of four outcomes
(REUSE_EXISTING_OWNER_PATH | BOUNDED_EXTENSION_REQUIRED | DEFER_UNSAFE |
NO_TELEGRAM_SURFACE), grounded in pinned code evidence, with an L2 test plan that is
executed only after a separate research-artifact approval.

The parent spike mctlhq/.github#325 stays owner-decided RESEARCH_ONLY_DEFER. This
proposal produces research artifacts only. It approves no Finance Assistant, connects
no bank, and changes no production code, flag or deployment. Its preliminary verdict
from the code read for this proposal (pinned at mctl-telegram
`8ab82c8245dea3a286c062a0666fe8d35076d684`) is **BOUNDED_EXTENSION_REQUIRED**. The
private transport is reusable. An owner-initiated invocation, a source/consent grant
and a CSV source store do not exist (see design.md).

## User stories
- AS the platform owner I WANT a pinned evidence map of the owner-only Telegram path SO THAT a later pilot decision rests on code, not assumptions.
- AS the platform owner I WANT a threat model with an explicit peer/group leak counterexample SO THAT I can see exactly where finance data could escape.
- AS a reviewer I WANT a reproducible L2 test plan using fake transport and synthetic identities SO THAT no L2 PASS is inferred from the abstract #325 model.
- AS the platform owner I WANT exactly one verdict and the smallest next decision SO THAT the Finance Assistant stays deferred until I change it explicitly.

## Acceptance criteria (EARS)
- WHEN the research report is produced THE SYSTEM SHALL include a source map pinned to a commit SHA for #297 (`SendToSelf`/`InputPeerSelf`), #354 (`classifySavedCommand`, `pollSavedHistory`), #1002 (AssistantInstall `audience.onlySenders`, mode `observe`, send tier `never`), job claim/propose/send policy and install-revision fencing, with each item labelled implemented, configured/deployed, tested, or unknown.
- WHEN a claim about deployed state is made THE SYSTEM SHALL cite the gitops path or read-only tool call that showed it, and SHALL mark unobserved state "unknown", never "absent".
- THE SYSTEM SHALL provide a threat model and data-flow diagram covering authenticated principal, tenant/account, AssistantInstall revision, source/consent grant, normalized synthetic CSV, deterministic digest, private destination, and revocation/deletion.
- WHILE any destination other than the owner's own primary Saved Messages dialog (`InputPeerSelf`) is in question THE SYSTEM SHALL classify it as deny-by-default.
- THE SYSTEM SHALL document at least one concrete peer/group leak counterexample against the current code, including the case where a finance digest is produced inside a peer-triggered conversation job.
- THE SYSTEM SHALL deliver an L2 test plan with the cases listed in tasks.md (owner, same-tenant non-owner, other tenant, peer/group, replay/out-of-order, reconnect `msg.Out`/history, stale install revision, revoke during pending send, no auto-reply, denial audit), using only fake transport, synthetic identities (personas Alice, Bob, Carol, Dana) and temporary state.
- IF the separate research-artifact approval for L2 execution has not been recorded THEN THE SYSTEM SHALL NOT run or report L2 results, and SHALL state "not executed".
- THE SYSTEM SHALL compare three private surfaces (Saved Messages, owner DM via bot, separate owner workspace launcher) and a CSV-only approach against a no-ingestion educational alternative.
- THE SYSTEM SHALL include a CSV/privacy risk matrix covering encryption, size/quotas, parsing safety, merchant/memo prompt injection, debug logs/traces and backup deletion.
- WHEN vendor claims (Anthropic Personal Finance, Plaid coverage) are cited THE SYSTEM SHALL cite the primary-source URL with an access date, and SHALL mark Montenegro/EEA/UK coverage "unknown" wherever it is not verified.
- THE SYSTEM SHALL end with exactly one verdict from the four outcomes, the smallest next owner decision, associated repos, dependency gates (#1048, #1088, #309), and explicit stop reasons.
- IF any step would require a code change, a flag change, a deployment, a real Telegram send or real financial data THEN THE SYSTEM SHALL stop and record it as a gated follow-up instead.

## Out of scope
- Any implementation of the Finance Assistant, a CSV uploader, a new `/mctl` subcommand, a new job kind, or a consent store.
- Real bank/Plaid OAuth, credential linking, real statements, payments, trading or investment actions.
- Production Telegram sends, automatic peer/group replies, managed runtime enablement (#1088), connector trust changes (#1048).
- Changes to `platform-gitops`, production flags, Argo or customer data.
- Creating downstream implementation issues or starting the implementer.

## Open questions
- Where should the research report live: `mctlhq/.github/docs/spikes/finance-assistant-private-delivery.md` (next to the #325 report) or `docs/research/` in this repo? Assumed: `.github` next to #325.
- Who records the separate "research-artifact approval" that gates L2 execution, and in what form (a PR approval on the test-artifact PR or a gitops status flip)? Assumed: a human approval on a dedicated test-only PR.
- Is a separate owner workspace launcher (mctl-portal/mctl-web) in scope for evidence, or only for comparison? Assumed: comparison only, no code read beyond public routes.
- I did not read mctl-api's upload, retention and deletion code, I did not check the live service status or logs, and I did not confirm that gitops image tag `0.135.0` maps to the pinned SHA. All three remain unknown until tasks 1 and 5 are done.
- Account-level revocation (`telegram_accounts.revoked_at`) is not checked in `policy.Evaluate`. Whether revoking during a pending send blocks delivery is unverified (test T8).
- Vendor and Montenegro coverage claims were not verified in this run (no web access was used). They must be verified with access dates during task 6 and stay "unknown" until then.
