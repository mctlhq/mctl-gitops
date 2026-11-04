# Assistant runtime field (own | managed) with consent, feature flag and account quota

## Context

Issue mctlhq/mctl-telegram#1089 is slice 1 of epic #1088 (P5 of #1002), governed by
`docs/adr/0008-managed-runtime.md` sections 1 and 3 ("column only"). Today an installed
assistant only runs while the owner's own `cmd/agent-worker` claims its jobs. ADR 0008 adds
a per-install choice, `runtime: own | managed`, where `managed` means a platform worker will
claim that account's jobs and send message content to a third-party model provider through
MCTL's AI gateway. Because that is a change in who sees message content, switching to
`managed` is a confirmed operation (explicit, versioned consent), gated by a server flag and a
platform-wide account quota.

This slice adds only the field, its storage, its validation (consent, flag, quota), its
audit, and its display on every owner and admin surface. It does not change which worker
claims a job; the SQL claim predicate, job holding for stale consent and the pool credential
are #1090 (slice 2). With the flag off (the default, and the deployed state) nothing changes
for any account.

## User stories

- AS an account owner I WANT to choose `runtime: managed` for my assistant SO THAT it can run
  without a machine or model credential of my own, once the platform worker exists.
- AS an account owner I WANT to be told exactly what data flow `managed` implies and to have to
  agree to it SO THAT message content never leaves for a third-party provider without my
  explicit consent.
- AS an account owner I WANT to switch back to `own` at any time without any extra step SO THAT
  I can withdraw from the managed data flow immediately.
- AS a platform operator I WANT `managed` to be refused unless `MANAGED_RUNTIME_ENABLED` is on
  and fewer than `MANAGED_RUNTIME_MAX_ACCOUNTS` accounts are managed SO THAT the rollout is
  controlled and spend is bounded.
- AS a platform operator I WANT every runtime change and its consent version recorded in the
  audit chain SO THAT a consent can be proven after the fact.
- AS a platform operator I WANT to know which managed installs consented to an older consent
  version SO THAT a provider change can hold them until they re-consent (holding is #1090).

## Acceptance criteria (EARS)

Schema and resolution
- WHEN an AssistantInstall document has `spec.runtime` equal to `own` or `managed` THE SYSTEM
  SHALL accept it; IF `spec.runtime` is any other value THEN THE SYSTEM SHALL reject the
  document as `invalid_install`.
- WHEN an AssistantInstall document carries `spec.consent` as a string (at most 64
  characters) THE SYSTEM SHALL accept it alongside `runtime`; IF it is not a string THEN THE
  SYSTEM SHALL reject the document.
- WHEN `assistant.Resolve` resolves an install without `spec.runtime` THE SYSTEM SHALL resolve
  `Profile.Runtime` to `own`.
- WHEN `assistant.ProfileRequest` builds the admin profile body THE SYSTEM SHALL include
  `runtime`, and `consent` when the install carries one.

Storage
- WHEN the server migrates its database THE SYSTEM SHALL add `agent_profiles.runtime TEXT NOT
  NULL DEFAULT 'own'`, `managed_consent_version TEXT NOT NULL DEFAULT ''`,
  `managed_consent_at` (nullable timestamp) and `budget_paused_until` (nullable timestamp,
  unused in this slice), on both Postgres and SQLite, idempotently.
- WHILE an account has never chosen a runtime THE SYSTEM SHALL report its runtime as `own`.
- THE SYSTEM SHALL never store `spec.consent` inside the encrypted install document; consent
  is a per-call assertion, recorded only as `managed_consent_version` and `managed_consent_at`.

Transition rules (install_assistant, update_install, manage page, admin profile route)
- IF a write would change the runtime from `own` to `managed` while `MANAGED_RUNTIME_ENABLED`
  is false THEN THE SYSTEM SHALL refuse it with `KindManagedDisabled` (MCP error
  `managed_disabled`) and change nothing; this check runs before the consent check so an owner
  is never asked to consent to something the server cannot offer.
- IF a write would change the runtime from `own` to `managed` and the call does not carry
  `consent` equal to `managed-data-flow/v1` THEN THE SYSTEM SHALL refuse it with
  `KindManagedConsentRequired` (MCP error `managed_consent_required`) and change nothing.
- IF a write would change the runtime from `own` to `managed` while the number of other
  accounts with `runtime = 'managed'` is at least `MANAGED_RUNTIME_MAX_ACCOUNTS` THEN THE
  SYSTEM SHALL refuse it with `KindManagedQuota` (MCP error `managed_quota`) and change
  nothing, also under concurrent writers.
- WHEN a write changes the runtime from `own` to `managed` and every check passes THE SYSTEM
  SHALL store `runtime = 'managed'`, `managed_consent_version = 'managed-data-flow/v1'` and
  `managed_consent_at = now` in the same UPDATE as the rest of the install, and bump
  `install_revision` as every install does.
- WHEN a write keeps the runtime `managed` and carries the current consent value THE SYSTEM
  SHALL refresh `managed_consent_version` and `managed_consent_at` (re-consent).
- WHEN a write keeps the runtime `managed` without a consent value THE SYSTEM SHALL leave the
  stored consent version and time unchanged and SHALL NOT apply the flag or quota checks.
- WHEN a write changes the runtime from `managed` to `own` THE SYSTEM SHALL accept it without
  consent, with the flag off, and regardless of quota, and SHALL clear nothing but the runtime
  (the stored consent stays as history).
- IF a call carries a `consent` value other than `managed-data-flow/v1` THEN THE SYSTEM SHALL
  refuse it with `KindManagedConsentRequired` when it is needed, and SHALL treat it as absent
  otherwise (it is never stored).
- WHEN the runtime changes, or the consent is refreshed, THE SYSTEM SHALL write an audit row
  for the account naming the new runtime and the consent version, never message content or
  install values.
- WHEN a refusal happens THE SYSTEM SHALL audit it by error kind only (existing
  `assistantinstall.AuditText` contract).

Re-consent
- WHILE an account has `runtime = 'managed'` and `managed_consent_version` differs from the
  server's current consent version THE SYSTEM SHALL report it as needing re-consent on
  `list_assistants.mine`, the manage page and `/mctl assistant`.

Surfaces
- WHEN `list_assistants` answers THE SYSTEM SHALL include `runtime` and
  `managed_reconsent_required` in `mine`.
- WHEN the owner sends `/mctl assistant` THE SYSTEM SHALL print `Runtime: managed (platform
  worker)` or `Runtime: own (your worker)`, plus a re-consent line when needed.
- WHEN the manage page renders the assistant section THE SYSTEM SHALL show a Runtime row and
  a runtime form whose `managed` option requires a consent checkbox labelled with the verbatim
  ADR text: "Messages needed to perform assistant tasks will be sent to MCTL's configured
  third-party AI provider through MCTL's AI gateway; gateway logging and caching are
  disabled."
- WHEN the admin route `PUT /api/admin/agent/profile` receives an optional `runtime` THE
  SYSTEM SHALL accept `own` always (no consent, flag or quota check); IF it is `managed` and the
  profile's stored `managed_consent_version` is not the current consent version THEN THE SYSTEM
  SHALL refuse with 409 `managed_consent_required` without accepting any consent from the admin
  (consent is given only by the account owner through `install_assistant`, `update_install` or
  the manage page); IF it is `managed` and the stored consent is current THEN THE SYSTEM SHALL
  apply the flag (403 `managed_disabled`) and quota (409 `managed_quota`) checks; a `consent`
  key on the admin route SHALL be rejected by the strict decoder (400); WHEN `runtime` is
  omitted THE SYSTEM SHALL leave it unchanged.
- WHEN the MCP tool surface changes THE SYSTEM SHALL update `docs/tool-descriptors.json` (and
  the per-profile snapshots) and add an approved entry under `docs/product-updates/` (ADR 0007).

Invariants
- WHILE `MANAGED_RUNTIME_ENABLED` is false and no account is managed THE SYSTEM SHALL behave
  exactly as before for every own-runtime install.
- THE SYSTEM SHALL NOT change job claim behaviour in this slice.

## Out of scope

- The runtime predicate in `ClaimAgentJobs` / `claimCoalesced`, `agent_jobs.runtime`, holding
  jobs of stale-consent managed accounts and the once-only owner notification (#1090).
- Pool credential, `/api/agent/pool-token`, `requireNotPool` (#1090).
- `OpenAIRunner`, `buildToolSet` (#1091); usage ledger, budgets and any use of
  `budget_paused_until` (#1092); C1 gate (#1093); CI image (#1094); gitops deployment
  (mctlhq/mctl-gitops#2345); docs (#1095). `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` is only parsed
  here.
- Turning the flag on in any environment.

## Open questions

- (Amended 2026-11-01 by the reviewer: check order is flag -> consent -> quota; the admin route
  never carries consent and may set `managed` only on a profile whose owner already consented.)
- Flag off while already managed: this proposal lets a managed account keep reinstalling
  (managed -> managed) and switch to own with the flag off, and only refuses own -> managed.
  The alternative (refuse any managed write with the flag off) would block an owner from
  editing other settings during a rollback. Reviewer should confirm.
- Whether `consent` belongs in the install document at all: the issue says the schema accepts
  it alongside `runtime`, so the schema accepts it, but the service strips it before storing so
  a stale consent can never authorise a later switch. update_install also takes a top-level
  `consent` argument for the same reason.
- `MANAGED_RUNTIME_MAX_ACCOUNTS=0`: treated as "no account may become managed" (not
  "unlimited"). Negative values fail config load.
- Audit placement: the runtime audit row is written after the profile UPDATE commits (as
  `LogToolCall` is non-fatal by contract), so a failed audit write leaves a chain gap that
  `VerifyAuditChain` reports rather than rolling back the switch.
