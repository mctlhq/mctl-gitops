# Spike: Glovo Assistant basket handoff and shared Temporal namespace tenant isolation (inert PoC)

## Context

The owner asked for a time-boxed spike that answers two coupled questions. Can a
catalog-driven "Glovo Assistant" let a user say, from Telegram or another MCTL
surface, "repeat my lunch from last Wednesday, without the drink" or "prepare this
meal on Wednesday at 12:30", and then prepare a basket and hand off to the user's own
Glovo app or site for final review and payment? And which Temporal namespace and
tenant model should a reusable assistant runtime use? The candidates are the existing
`mctl-agents` namespace, a shared `mctl-assistants` namespace with tenant-scoped
internal isolation, and one Temporal namespace per tenant. MCTL must never pay, never
store card data, and never report an order as paid because the user opened a handoff.

Today mctl-telegram ships exactly one assistant (`assistants/hr-recruiter`). It runs
one install per Telegram account and is driven by inbound DMs. The mctl Temporal
cluster has no client authentication, and a NetworkPolicy is its only isolation
boundary. So the spike authorizes only research, a canonical proposal, and a
**local, inert, mock-only** PoC: a fake Glovo API, synthetic tenants, and the Temporal
test server. Production deployment, GitOps changes, a live Glovo session, and any
purchase are excluded. The result is a decision record
(`GO_SHARED_AFTER_HARDENING | GO_DEDICATED_TENANT | MOCK_ONLY_PENDING_CONNECTOR | NO_FIT`)
and a breakdown of child issues for each owning repo. Implementation needs its own
separately approved proposal.

## User stories

- AS an MCTL user WANT to ask from Telegram to repeat or adjust a previous Glovo order SO THAT a basket is ready for me to review and pay in Glovo, without retyping the order.
- AS an MCTL user WANT to say "prepare this meal Wednesday at 12:30" SO THAT the assistant prepares the basket at that time and asks me to finish it in Glovo, and never orders on its own.
- AS a platform owner WANT a source-backed comparison of the three Temporal tenancy options SO THAT I can decide the assistant runtime topology before any multi-tenant rollout.
- AS a security reviewer WANT negative tests showing that tenant A cannot list, query, signal or replay tenant B's assistant workflows through any MCTL surface SO THAT shared-namespace isolation is evidenced and not assumed.
- AS a user whose Telegram account is not linked to an MCTL tenant WANT the assistant to refuse, or to use an explicit personal scope, SO THAT my orders are never placed under the shared `mctl` work-item tenant.
- AS the assistant author WANT a provider-neutral checkout-handoff contract SO THAT later Claude and ChatGPT surfaces can reuse it, and no surface claims a deep link it cannot prove.

## Acceptance criteria (EARS)

Inventory and decision
- WHEN the spike report is delivered THE SYSTEM SHALL list every Temporal namespace, retention, search attribute, task queue and gRPC client that is in effect today, each with an exact mctl-gitops path. Each entry is marked `deployed` or `candidate`.
- WHEN the spike report is delivered THE SYSTEM SHALL compare option A (existing `mctl-agents`), option B (shared `mctl-assistants` with tenant-scoped internal isolation, including the per-tenant task queue variant) and option C (a Temporal namespace per tenant) on blast radius, operations cost, retention, worker sizing, queue topology, Kubernetes namespaces and auth prerequisites. It SHALL record exactly one decision value.
- WHILE the Temporal frontend has no client authentication and authorizer THE SYSTEM SHALL record multi-tenant production rollout as BLOCKED, whatever decision value is recorded.

Identity and scope
- WHEN a Telegram user issues an owner command to the Glovo Assistant THE SYSTEM SHALL resolve the chain Telegram user, verified MCTL principal (surface identity link), authorized tenant or explicit personal scope, `assistant_install_id` with `install_revision`, and `glovo_connection_id` before it creates any order.
- IF any link in that chain is missing, revoked, expired or ambiguous THEN THE SYSTEM SHALL refuse with a typed reason. It SHALL NOT default to the deployment's configured work-context tenant (`mctl`).
- IF an order, signal, query, approval or schedule fire names a `tenant_id`, `owner_principal_id` or `order_id` that does not match the server-side resolved scope THEN THE SYSTEM SHALL refuse it with an error that does not disclose whether the target exists.
- WHERE an LLM client takes part THE SYSTEM SHALL expose only opaque `order_id` handles. It SHALL never expose a Temporal namespace, workflow ID, run ID or task queue name.

Owner commands versus inbound messages
- WHEN a message arrives from a third party in a DM THE SYSTEM SHALL NOT treat it as a Glovo command. Only owner-originated commands (Saved Messages `/mctl`, or an authenticated MCTL surface) and server-fired schedules can start an order.
- WHEN an order needs owner attention (basket ready, price changed, outcome unknown) THE SYSTEM SHALL notify through the owner channel (Saved Messages or bot), never into an unrelated DM.

Checkout protocol
- WHEN an order runs THE SYSTEM SHALL pass through `prepare -> quote -> basket_mutation (only if authorized) -> verify -> human_handoff -> outcome_unknown`, in that order, with no step skipped.
- WHEN a quote is produced THE SYSTEM SHALL compute a basket fingerprint over store, item IDs, quantities, modifiers, unit and total price, fees, currency and delivery-address reference. The owner's consent SHALL be bound to that exact fingerprint.
- IF availability, price, fees, modifiers or address differ from the consented fingerprint at verify time THEN THE SYSTEM SHALL invalidate the consent and ask the owner again. It SHALL NOT hand off the changed basket.
- WHEN a handoff is issued THE SYSTEM SHALL make it single-use and bound to the order, the owner and the fingerprint, with a TTL (default 15 minutes in the PoC).
- IF a handoff is used a second time, after its TTL, or by another principal THEN THE SYSTEM SHALL refuse it, and the order SHALL remain unchanged.
- WHEN the owner opens the handoff THE SYSTEM SHALL record `handoff_opened` and report the order outcome as `OUTCOME_UNKNOWN` unless verifiable external confirmation exists. It SHALL never report `paid` or `placed`.
- THE SYSTEM SHALL provide no `pay_order`, card-storage or auto-checkout operation.

Schedules and idempotency
- WHEN a scheduled occurrence fires THE SYSTEM SHALL start at most one order workflow for that occurrence. The workflow ID is derived from `(install_id, schedule_id, occurrence_time)` and the run uses Temporal's reject-duplicate policy.
- WHEN a schedule fires or an approval signal arrives THE SYSTEM SHALL revalidate install state, revision, tenant membership and connection before any provider write.
- IF the install was cancelled or revoked, or its revision changed, since the order snapshot THEN THE SYSTEM SHALL stop the order as `stale_install` and perform no provider write.
- THE SYSTEM SHALL use the Automation Control Plane (mctlhq/.github#318) as the only schedule owner, mocked in the PoC. The assistant SHALL have no scheduler of its own.
- WHEN the same approval button is pressed twice, or two overlapping requests arrive for the same occurrence, THE SYSTEM SHALL apply the first and acknowledge the rest as duplicates.

Data handling
- WHILE an order workflow runs THE SYSTEM SHALL keep Glovo session tokens, cookies, delivery addresses, cart contents, raw menu text and payment details out of Temporal history, visibility, search attributes, logs and LLM tool results. Workflows carry only opaque references to encrypted, tenant-owned state.
- IF a provider call times out or returns an unknown result THEN THE SYSTEM SHALL retry only idempotent reads. A basket write SHALL be followed by a read-back verify, never a blind retry.
- WHEN an install is revoked or a connection deleted THE SYSTEM SHALL delete its encrypted order state and session reference. Workflow history then holds only opaque IDs, which expire with namespace retention.

PoC evidence
- WHEN the PoC test suite runs THE SYSTEM SHALL use only a fake Glovo API, the Temporal dev test server, two synthetic tenants, one synthetic unauthorized tenant and fake credentials. Every scenario listed in tasks.md T1 to T18 SHALL pass with no network egress.
- WHEN real-phone basket continuity has not been verified with explicit owner consent and no payment THE SYSTEM SHALL mark it `UNVERIFIED` and use the fallback UI (open the Glovo app and review the basket there) with no claimed deep link.

## Out of scope

- Any real payment, card storage, order placement, live delivery, production Glovo login or session, real user schedule, or auto-checkout.
- Publishing a Glovo assistant into the production catalog (`assistants/` embed or the registry), turning on `MANAGED_RUNTIME_ENABLED` or other runtime flags, or any change to mctl-gitops, cluster namespaces or Temporal namespace registration.
- Building a generic commerce ledger, a new approval engine, a second scheduler, or a new epic. Granting the provider adapter Vault, Temporal gRPC or cluster credentials.
- mctl-api#549 payment interoperability.
- Implementing Temporal client authentication or an authorizer. That belongs to mctl-gitops / platform and is a rollout prerequisite named here.

## Open questions

- Montenegro coverage, the Glovo terms of service for automated basket preparation, and partner API availability cannot be verified from this repository. The proposal treats them as `UNVERIFIED` and assumes a mock-only adapter.
- Whether `denya/glovo-skill`'s unofficial session API may be used at all, even for a manual owner-controlled proof, depends on Glovo's terms. The PoC copies no code from it and only documents its approach.
- Personal scope for Telegram users without MCTL tenant membership: this proposal assumes the owner chooses explicit refusal, and the PoC models a `personal:<principal>` scope only as a refused-by-default path. If personal scopes should be allowed, mctl-api must define them (mctlhq/.github#309).
- The Automation Control Plane contract (mctlhq/.github#318) is still a proposed spike. The PoC mocks a minimal `ScheduleFire{schedule_id, occurrence_time, install_ref}` contract that may change.
- Whether the PoC Temporal test should live in this repository (a separate Go module, so the server binary gains no Temporal SDK dependency) or in mctl-agents, the existing Temporal owner (Python). This proposal puts it in a separate module under `test/glovo-poc/` in mctl-telegram, because the install and identity contracts live here.
- Deployed values were read from the mctl-gitops checkout only. No live mctl MCP read was made, so whether the live cluster matches GitOps is not observed.
