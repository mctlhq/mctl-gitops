# Design: issue-1240-spike-finance-assistant-owner-private-de

## Current state
All references are pinned to mctl-telegram `8ab82c8245dea3a286c062a0666fe8d35076d684`
(2026-11-08). "Implemented" here means present in merged code. It does not mean
proven safe for finance.

**Private transport (#297), implemented.**
- `internal/telegram/sendself.go`: `SendToSelf` and `SendToSelfWithRandomID` call
  `SendToInputPeer[WithRandomID]` with `&tg.InputPeerSelf{}`. The destination is fixed
  by the type, not by a caller-supplied peer id, so it cannot be redirected to a
  peer/group. The random-id variant de-duplicates crash retries server-side
  (`RANDOM_ID_DUPLICATE`, `LocateOwnOutgoing` #1029).
- `cmd/server/agentwiring.go` (`poolSelfSender`) wires these into the client pool.
- `internal/agent/control/notifier.go`: `Notifier.Reply` (synchronous `/mctl` reply)
  and `DeliverPending` (queued `owner_notifications`, claim lease 2m, max pending
  age 24h, `GlobalKill` check, truncation to the Telegram limit).

**Owner command intake (#354), implemented.**
- `internal/agent/listener/extract.go`: `ExtractMessage` classifies the Saved Messages
  dialog by peer identity (`isSelfPeer`), not by `msg.Out`. The code comments record
  live observations (2026-07-26, 2026-08-01) of `Out=false` on owner messages.
  `classifySavedCommand` rejects forwarded messages, a foreign `saved_peer_id` and a
  foreign `from_id`, and drops any text that is not `/mctl` (`isMCTLCommand`).
- `internal/agent/listener/history.go`: `pollSavedHistory` and
  `initializeSavedHistoryCursor` read `messages.getHistory` on `InputPeerSelf`.
  `ExtractSavedHistoryMessage` re-checks the PeerID. The cursor lives in
  `internal/db/agent_saved_commands.go`.
- `internal/agent/control/router.go`: `HandleSavedText` dispatches a **closed** set of
  subcommands (status, leads, conversations, show, continue, pause, unpause,
  assistant, takeover, approve, reject, plus input/work/link behind flags). An
  unknown subcommand gets `unknownCommandReply`. There is **no owner-invoked
  assistant job**: no command starts a worker job from Saved Messages.

**Worker-produced owner-facing output, implemented.**
- `internal/agentapi/actions.go`: `send_owner_summary` goes through `handleOwnerFacing`
  (`ActionTypeOwnerSummary`, `NotificationSummary`). It is bound to a claimed job
  (`enforceBinding`, `jobBound`) and may carry `ConversationID == 0`.
- `internal/agent/policy/policy.go` `Evaluate`: order is global kill, then a
  user-mismatch check (applied **only** to `ActionTypeReply`), then the install-revision
  fence (`in.InstallRevision != in.Profile.InstallRevision` gives
  `DenyInstallChanged`, #1018), then mode (`observe`/`guarded` allowed, `off`
  denied). After that, owner-facing actions **return Allow before every
  per-conversation gate** (blocked senders, audience, superseded source, pause).
- `internal/agent/executor/executor.go` re-checks the install revision at approve time
  and during recovery ("deny stale-install draft").

**Assistant Catalog / install (#1002), implemented.**
- `internal/assistant/assistant.go`: the install spec has `audience.scope`,
  `audience.onlySenders`, `audience.blockedSenders`, `mode`, and per-intent send tiers
  `auto|approve|never` (`TierNever`, `NeverAutoSend`).
  `internal/assistantinstall/service.go` provides `Prepare/Commit/Apply/Patch` with
  an expected revision (optimistic concurrency) and `PatchWithConsent`.
- `onlySenders` scopes **which inbound peers create jobs**. It does not scope where
  output goes, and it is not an owner-invocation mechanism.

**CSV / ingestion.** No private-finance CSV ingestion or upload store was located in the
**inspected mctl-telegram code**; mctl-api upload, retention and deletion were
not read, so cross-component presence remains `unknown`, not proven absent.
`internal/mcp/media_tools.go` has an outbound media upload with a byte cap
(`MediaUploadMaxBytes`, `file_base64`/`file_url`), which is a send path and not
ingestion. No source/consent grant table exists.

**Leak counterexample (current code).** A worker job is claimed for a peer
conversation (for example a group-adjacent or same-tenant non-owner DM matched by the
audience). If a finance capability were enabled in that worker, `send_owner_summary`
for that job would be allowed by `Evaluate` regardless of `blockedSenders`/audience,
because owner-facing actions skip those gates. Delivery would still land in Saved
Messages, but the computation would be **triggered and contextualised by a peer
message**, and the job's `propose_reply` path would sit in the same job, with only
the send tier separating finance content from the peer. Conclusion: the transport is
private, but the invocation is not owner-initiated. This is why
`onlySenders=[owner]`/`observe` is not proof of end-to-end safety.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, image
  tag `0.135.0`, `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`,
  `ASSISTANT_REGISTRY_ENABLED: "true"`, `HUMAN_INPUT_ENABLED: "true"`, work context
  feature gated separately. These values show the **labs GitOps configuration**, not production runtime
  behavior. Whether image 0.135.0 contains the pinned SHA's code, or the
  effective live configuration behaves this way, was **not verified**.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` exists (preview
  service). Not read in detail.
- mctl MCP read tools (`mctl_get_service_status`, logs) were **not called** in this run.
  Live health and the runtime behaviour of Saved Messages delivery are unknown.
- mctl-api CSV/upload/retention capabilities: **not observed** (repo not cloned in this
  run). Recorded under Open questions.

## Proposed solution
A **documentation-only research deliverable** in the `mctl-telegram` repository,
recorded at `docs/reports/finance-assistant-owner-private-discovery.md` (or a
reviewed equivalent local report path). No cross-repo writes, product code,
new L2 Go tests, test execution, flags or deployment. The report contains four
sections, produced in order. After independent review a separate owner
decision may authorize an exact test-only artifact; this proposal does not.

1. **Evidence matrix** (report section): each mechanism above listed with file:symbol
   at the pinned SHA and four columns: implemented / configured (gitops path) / tested
   (existing test file, e.g. `internal/agent/listener/extract_test.go`,
   `history_test.go`, `internal/agent/control/notifier_test.go`,
   `internal/agent/policy/policy_test.go`, `internal/agentapi/intent_never_test.go`) /
   unknown. Includes a cross-check against #325 D2 findings.
2. **Threat model + data-flow** (Mermaid in the report):
   principal (mctl OAuth user) -> tenant/account (`telegram_accounts`, user_id) ->
   AssistantInstall revision -> source/consent grant **[missing]** -> normalized
   synthetic CSV **[missing]** -> deterministic rules-only digest -> `owner_notifications`
   -> `SendToSelfWithRandomID(InputPeerSelf)` -> revoke/delete. Each edge is annotated
   with its fence (revision, kill switch, mode, account revocation) or marked as a gap.
   Deny-by-default for every non-`InputPeerSelf` destination.
3. **Gap and option analysis.** The smallest contract extension (described, **not
   implemented**) has three parts:
   (a) an owner-invoked job kind started only from `classifySavedCommand` output (for
   example `/mctl finance digest`), carrying no conversation id and no peer, whose
   worker credential may call only `send_owner_summary`, never `propose_reply`;
   (b) the policy rule that this job kind has `ConversationID == 0` and is fenced by
   install revision plus a consent-grant revision;
   (c) a per-account consent/source grant with revoke that tombstones pending
   `owner_notifications`. Surface comparison: Saved Messages (reuse; best fence),
   owner DM through the bot (`internal/bot`; needs a chat-id-to-principal binding),
   owner workspace launcher (no Telegram exposure; outcome NO_TELEGRAM_SURFACE). CSV-only
   versus no-ingestion educational assistant.
4. **L2 test plan**: application-level Go integration tests against a fake `SelfSender`
   and fake MTProto updates, in-memory SQLite and synthetic personas. It is written as a
   plan; execution happens only on a separately approved test-only PR.

**Verdict rules (no preselected outcome):**
- **REUSE_EXISTING_OWNER_PATH:** only if source-pinned evidence proves an
  owner-invoked job and private output can be composed without a new permission
  or product runtime; testability and remaining unknowns explicitly stated.
- **BOUNDED_EXTENSION_REQUIRED:** only if evidence establishes a viable,
  small additive owner-invocation/consent contract under existing identity
  and policy, with independently gated L2 tests before a pilot.
- **DEFER_UNSAFE:** if principal binding, data custody, deletion or
  destination authorization cannot be established from current evidence.
- **NO_TELEGRAM_SURFACE:** if the only defensible user-facing approach is a
  separate owner workspace and Telegram should remain out of the finance path.

Recommend exactly one outcome *after* completing evidence, threat model,
alternatives and privacy analysis, and include strongest contrary evidence.
The smallest next owner decision is whether to authorize a separately
specified **L2 test-only artifact**; approval of this proposal permits only
the report and test **plan**, never L2 execution. Stop if real data, live
sends, managed runtime (#1088), connector trust changes (#1048) or shared
memory beyond #309 is needed.

## Alternatives
- **REUSE_EXISTING_OWNER_PATH**: dropped because no owner-initiated invocation exists.
  The only producer of owner summaries is a peer-triggered job (counterexample above).
- **Implement the extension now**: dropped. The issue forbids implementation, and #325
  stays RESEARCH_ONLY_DEFER.
- **NO_TELEGRAM_SURFACE (workspace-only)**: kept as the fallback recommendation if the
  owner rejects any new job kind. It avoids Telegram entirely but gives up the existing
  private transport.
- **Treat `onlySenders=[owner]` + `observe` as sufficient**: rejected. Audience scopes
  inbound triggers, not output. Owner-facing actions bypass audience gates in `Evaluate`.

## Platform impact
- Migrations: none. Backward compatibility: unaffected (documents only).
- Resources: none in production. L2 execution, if approved, runs in CI with fakes.
- Risks: (1) the report is read as an implementation approval. Mitigation: verdict text
  states it is not, and #325 stays RESEARCH_ONLY_DEFER. (2) A fixture leaks real
  identifiers. Mitigation: CLAUDE.md persona rule and `git grep` before choosing ids.
  (3) Vendor claims go stale. Mitigation: access dates, "unknown" defaults.
  (4) Deployed image does not match the pinned SHA. Mitigation: record the 0.135.0 tag
  and resolve it against the SHA in task 1.
