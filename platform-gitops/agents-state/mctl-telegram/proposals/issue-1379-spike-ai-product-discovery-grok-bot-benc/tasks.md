# Tasks: issue-1379-spike-ai-product-discovery-grok-bot-benc

Revision 4 (2026-11-23). Remaining tasks are docs-only/research-only and need independent re-review and owner approval. The already owner-observed Grok (grok.com) connection on 2026-11-22 is historical evidence, NOT a newly executed test. No implementer, report PR or live test is authorized.

- [ ] 1. Re-pin the baseline at report time.
  - Record the mctl-telegram SHA, the mctl-gitops SHA, and the production and preview image tags.
  - Re-pin current mctl-telegram/gitops/mctl-alice/mctl-api source commits per revision 4; retain the 2026-11-21 SHAs only as historical evidence.
  - Write report section 1a, the PA baseline. Each row is classified merged, deployed (gitops desired state), flagged, tested or planned, with a path.

  — DoD: every row has a path and a label. No gitops identifier is copied: no TTL-exempt ids, no Cloudflare account path, no Vault paths.
- [ ] 2. Vendor sources (read-only, no login).
  - Re-fetch the six original URLs plus `town.com/docs/integrations/mcp-servers`, `docs.x.ai/grok-bot/computer-and-apps`, the Grok Bot security, pricing and FAQ pages, and the official Telegram terms (`telegram.org/tos/content-licensing`, `core.telegram.org/api/terms`).
  - Record the access date and a minimal verbatim quote per claim. Write report section 2, Town in its two roles.

  — DoD: every cell is `VENDOR-DOCUMENTED` with a quote and URL, or `UNKNOWN`. Custom MCP authentication and the callback URL are quoted, or marked `UNKNOWN`. Nothing is inferred.
- [ ] 3. Admission, profile, ceiling and revocation (depends on 1).
  - Write report sections 1b, 1c and 1d from `internal/oauth/scopes.go`, `internal/toolprofile/toolprofile.go`, `internal/oauth/server.go` (`handleRevoke`), `internal/oauth/dcr_allowlist_test.go`, `internal/mcp/hidden.go`, `SECURITY.md`, `docs/platforms/compatibility.md` and both values files.
  - Confirm the minimum read scopes for `core-readonly`.

  — DoD: there are separate columns for implicit host, exact DCR URIs (count only), CIMD, profile, ceiling, stable `client_id` and live observation, for both production and preview. Grok Bot is not marked admitted on the strength of `grok.com` or `cursor.com`. Revocation outcomes and timings match the code.
- [ ] 4. Conformance test plan (depends on 3): report section 4, scripted client against `tg-preview.mctl.ai`, synthetic or isolated approved account.

  — DoD: each step has its preconditions, its request shape, its exact expected HTTP or JSON-RPC result and timing, and its audit or metric entry, and is marked `NOT-EXECUTED`. The access token after a revoke is expected to stay valid until it expires (<=1h). The plan says it does not prove vendor E2E.
- [ ] 5. Vendor interoperability test plan (depends on 2, 3): report section 5, with rows for Grok Bot, Townie, and optionally Grok Chat and Cursor IDE.

  — DoD: every row records its registration strategy, callback host and URI, `resource`, PKCE, the requested and granted scopes, `initialize`, `tools/list`, the identity read, a synthetic read, negatives and audit. Preserve historic Grok (grok.com) OWNER_OBSERVED_WORKS; exact Grok Bot client/build remains UNKNOWN. All NEW Grok Bot attribution and restricted security tests are BLOCKED or `NOT-EXECUTED` until a separate owner GO. The live-test preconditions are listed: stable `client_id`, `core-readonly` plus a minimum-read ceiling, no admin, groups, write or account scopes, token scopes verified without logging values. Dynamic-id clients are BLOCKED.
- [ ] 6. External-client threat model (depends on 2, 3): report section 6.

  — DoD: a control-by-control table of what applies and what does not for a direct MCP client, with the Grok Bot sharing and boundary quotes. Alice is limited to `iot:view` with no device or control step. Unverified claims are `UNKNOWN`. The mctl-alice `TOOL_SCOPES` map is pinned and verified at `cb276d65`; OAuth issuer/refresh/runtime remains UNKNOWN unless separately verified.
- [ ] 7. Telegram consent and licensing gate (depends on 2): report section 7.

  — DoD: it cites `docs/design/core-profiles.md` and the dated terms, and lists the policy and legal questions apart from the engineering questions. Every digest, memory or distribution hypothesis references the gate.
- [ ] 8. Meetup pack (depends on 1, 2, 5): report section 8. Target the pack for Nov 26 and the rehearsal for Nov 27. The event is Nov 28, still unconfirmed, and confirmation is an owner action.

  — DoD: track A (offline, synthetic) is complete on its own. Tracks B and C each name their gates. There is an explicit fallback to A. The findings template is empty and has no PII or chat field. Nothing claims live readiness.
- [ ] 9. Hypotheses, metrics, decision (depends on 3, 6, 7): report section 9.

  — DoD:
  - There are 3-5 hypotheses with job, differentiation, evidence class, ICE, success and failure, dependencies, smallest experiment, cost and security, and owner.
  - Voice is marked "candidate, owner pending triage".
  - The metrics are defined with retention and privacy limits.
  - There is one decision and the next owner decision. DUAL_TRACK_BOUNDED is argued from evidence, not assumed.
  - No HOLD or gate text is changed.

## Tests

- [ ] T1. `git diff --stat` for the eventual report PR touches only `docs/spikes/pa-grok-town-benchmark.md`.
- [ ] T2. `go test ./docs/` (package `docs`, `docs/doc.go`) and the CI `go test -race ./...` stay green. There is no markdown linter in CI, and the `product-updates` gate does not apply to a docs-only change.
- [ ] T3. A grep of the new file finds no numeric Telegram id from gitops, no Cloudflare account path, no Vault path and no real handle. Only the personas Alice, Bob, Carol and Dana appear.
- [ ] T4. A reviewer checks every `VENDOR-DOCUMENTED` cell against its URL and date. No Grok Bot capability is derived from `grok.com` or Cursor admission.
- [ ] T5. Every revocation expectation matches `handleRevoke` and `SECURITY.md`. No step expects an immediate 401 for an issued access token.
- [ ] T6. Every future test step reads `NOT-EXECUTED` or `BLOCKED`; the 2026-11-22 Grok observation retains its historical evidence class. The findings template is empty.

## Rollback

The change is docs-only. Revert the report commit, or close its PR unmerged. No runtime, flag, OAuth, gitops, account or vendor state is touched, so nothing else needs to be undone.

## Revision 4 evidence completion tasks (all research-only; not executed)

- [ ] 10. Reconcile Grok (grok.com) and Town `OWNER_OBSERVED_WORKS` with #1393 and historical #1381 audit; retain Grok Bot exact client/build UNKNOWN and Town CIMD-versus-DCR UNKNOWN.
- [ ] 11. Use pinned latest repo SHA ledger and live-vs-desired proof: preview PA read-only flags enabled, worker replicaCount 1, three services Healthy/Synced; NO fabricated R1–R6 or Phase-4 results.
- [ ] 12. Pin mctl-alice `src/tools/handlers.ts` and its read/control/Quasar scope map; external-client threat model and admin over-scoping held for future separate minimum-privilege test.
- [ ] 13. Verify vendor primary URLs and checked-on dates, document source quotes; separate conformance scripted tests from vendor E2E and owner observation; keep Telegram consent legal decision open.
- [ ] T7. Before review confirm exactly six OpenSpec files changed in the same PR, no `.status.yaml`, OAuth configuration or runtime changes, no implementation or login; retain proposal status `proposed`.