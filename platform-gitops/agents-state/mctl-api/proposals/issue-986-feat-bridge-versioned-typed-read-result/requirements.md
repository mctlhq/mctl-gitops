# Versioned typed read-result extension of the command bridge (fake-only Glovo reads)

## Context

The command bridge (mctl-api#962/#968, `internal/bridge/`) carries the frozen
wire contract `bridge.mctl.ai/v1alpha1`. That contract was vendored byte for byte
from mctlhq/mctl-agents#1045 and pinned by `schema/PROVENANCE`. It cannot return
read data. `result.schema.json` has only an optional `result_ref` (`^res_...`),
and nothing defines the payload behind that ref or a safe way to fetch it. The
command `kind` enum is closed to `quote`, `place_order_fake`, `cancel_order_fake`
and `read_status`. Because of this, four of the seven Glovo MCP tools (history,
preview, basket, prepare) answer `not_ready`.

The owner decided on 2026-11-09 (OPEN-1) that reads are required for P1
acceptance. P1 must prove the full fake-only flow `history -> preview -> basket
-> prepare -> aar_ approval -> fake-provider effect -> order status`, with
user-data isolation on the read path. This proposal covers the mctl-api part of
one versioned, additive read extension of the existing bridge: `v1alpha2`, a
superset of v1alpha1. It is not a second protocol. In mctl-api the extension
does three things. It vendors the canonical schema, which is authored in
mctl-agents. It stores each typed read result bound to tenant, principal,
connection and install revision, with a TTL and a digest. It serves the result
only through mctl-api, after the caller's rights are checked again. Nothing in
this proposal enables the bridge in any environment.

## User stories

- AS the end user of the Glovo MCP surface I WANT my order history, previews,
  basket and prepared order to come back as data SO THAT I can complete the
  fake-only P1 flow.
- AS the trusted control orchestration (mctl-agents DevLoop / mctl-assistants) I
  WANT to receive only a result reference and digest for a read SO THAT raw read
  payloads never enter Temporal history, signals or logs.
- AS the low-trust provider worker (mctl-telegram fake provider) I WANT a typed,
  bounded way to return synthetic read data through the existing result callback
  SO THAT I do not need a second protocol or a new credential.
- AS a security reviewer I WANT every read result bound to tenant, principal,
  connection and install revision and refused with an existing closed code
  otherwise SO THAT one user's read data can never reach another caller.
- AS an operator of existing v1alpha1 consumers I WANT v1alpha1 commands and
  results to keep working byte for byte SO THAT the extension cannot break them.

## Acceptance criteria (EARS)

Contract and compatibility
- THE SYSTEM SHALL vendor the v1alpha2 command, result and read-result schemas
  byte for byte from the canonical mctl-agents source. It SHALL record their
  sha256 in a PROVENANCE file and keep the v1alpha1 files and their PROVENANCE
  digests unchanged.
- WHEN a v1alpha1 command is enqueued or claimed, or a v1alpha1 result is
  submitted, THE SYSTEM SHALL validate it against the unchanged v1alpha1 schema.
  It SHALL produce the same projection and the same result digest as before this
  change, and pinned golden fixtures SHALL prove both.
- WHEN a command of a read kind (`read_history`, `read_preview`, `read_basket`,
  `read_prepare`; final names come from the canonical schema) is enqueued, THE
  SYSTEM SHALL record its wire version as `bridge.mctl.ai/v1alpha2` and emit it
  with that `schema_version` on claim.
- IF a submitted result's `schema_version` differs from the stored wire version
  of its command, THEN THE SYSTEM SHALL refuse it with `binding_mismatch` (409)
  and change no row.

Read-result submission (provider -> mctl-api)
- WHEN a provider submits a v1alpha2 result with `outcome=succeeded` for a read
  kind, THE SYSTEM SHALL validate the embedded `read_result` against the schema
  for that kind. It SHALL recompute the canonical sha256 over `read_result.data`
  and, in the same transaction as the existing result CAS, insert one
  `bridge_read_results` row bound to the command's stored tenant, owner
  principal, tenant_ref, principal_ref, connection_ref and install_revision,
  with a server-minted `res_` ref and `expires_at = now() + read TTL`.
- IF the declared `read_result.digest` differs from the server-computed digest,
  THEN THE SYSTEM SHALL refuse the submission with `binding_mismatch` (409).
- IF the `read_result` kind does not match the command's kind, or a read-kind
  success carries no `read_result`, or a non-read kind carries a `read_result`,
  or a read-kind result has `provider_effect` other than `none`, or a read-kind
  result carries a provider-chosen `result_ref`, THEN THE SYSTEM SHALL refuse it
  with `result_inconsistent` (422).
- IF a request body exceeds the bridge body limit, or the canonical
  `read_result.data` exceeds the per-read byte cap, THEN THE SYSTEM SHALL refuse
  it with `invalid_document` (400) and store nothing.
- IF `read_result.data` does not carry `provenance: "synthetic"`, THEN THE
  SYSTEM SHALL refuse it with `invalid_document` (400).
- WHEN the same result (same server-computed digest) is submitted again, THE
  SYSTEM SHALL answer `replayed: true` with the same `result_ref` and create no
  second read row. WHEN a different result is submitted for a completed command,
  THE SYSTEM SHALL refuse it with `result_conflict` (409).
- WHILE a command is of a read kind THE SYSTEM SHALL refuse a write permit with
  `not_mutating`. The write fence and `aar_` semantics SHALL stay exactly as
  they are for `place_order_fake` and `cancel_order_fake`.

Control path (refs only)
- WHEN a read result is stored, THE SYSTEM SHALL keep `bridge_commands.result`,
  the `bridge-result` Temporal signal, `ReadOutcome` and every audit entry and
  log line limited to ids, refs, digests, sizes and codes. The raw
  `read_result.data` SHALL NOT appear in any of them.

Read-result retrieval (user -> mctl-api)
- WHEN an authenticated caller requests `GET /api/v1/glovo/read-results/{result_ref}`
  with a `digest` query parameter, THE SYSTEM SHALL return the stored typed data
  only if all of these hold:
  - the caller's tenant equals the row's tenant;
  - the caller's principal id equals the row's owner principal;
  - the row is not expired;
  - the connection is still active at the stored install revision;
  - the presented digest equals the stored digest.
- IF the ref is unknown, or belongs to another tenant or another principal, THEN
  THE SYSTEM SHALL answer `command_not_found` (404) and disclose nothing about
  the row.
- IF the read result is past `expires_at`, THEN THE SYSTEM SHALL answer
  `command_expired` (409).
- IF the connection is revoked, or its install revision has changed, or the
  presented digest differs, THEN THE SYSTEM SHALL answer `binding_mismatch`
  (409).
- IF the connection status cannot be determined, THEN THE SYSTEM SHALL answer
  `bridge_unavailable` (503) and never serve the data.
- IF a bridge-provider principal calls the retrieval route, THEN THE SYSTEM
  SHALL refuse it through the existing `bridgeProviderGate` (403
  `bridge_provider_gate`).
- WHILE `MCTL_BRIDGE_ENABLED` is unset THE SYSTEM SHALL answer 404 on the
  retrieval route, exactly like the other bridge routes.
- WHEN concurrent retrievals of the same ref arrive, THE SYSTEM SHALL return
  byte-identical bodies. WHEN concurrent submissions for the same command
  arrive, exactly one SHALL create the read row.
- WHEN the expiry sweep runs, THE SYSTEM SHALL erase `data` from expired read
  rows. It SHALL keep only ref, bindings, digest, size and timestamps.

Synthetic only
- WHILE this extension is in force THE SYSTEM SHALL make no real provider call,
  account login or credential issuance. All fixtures and test data SHALL be
  synthetic.

## Out of scope

- Authoring the canonical schema. It is authored in mctl-agents, and this repo
  vendors it.
- The mctl-telegram fake provider (#1262) and the mctl-agents DevLoop changes
  (#1044).
- Enabling the bridge, issuing any provider credential, choosing the
  federated-issuer verifier (mctl-gitops#2506), the Temporal frontend auth
  gates, and deployment approvals.
- Any change to the write fence, `aar_` approvals or the mutating kinds.
- A connection registry (`gcn_` lifecycle). This proposal consumes one through
  an interface and does not build one.
- Real Glovo API calls and real user data.

## Open questions

- Canonical schema availability. The v1alpha2 schema files must first merge in
  mctl-agents. Until they do, the vendoring task cannot complete, and the
  implementer must not author the schema locally. The field shapes in
  design.md are this repo's expected input to that review, not the canonical
  ones.
- Exact read kind names and per-kind fields (history, preview, basket,
  prepare). The design assumes `read_history`, `read_preview`, `read_basket`,
  `read_prepare`, with the bounded shapes sketched in design.md.
- Whether `prepare` is truly effect-free. The design treats it as a read
  (provider_effect `none`, no permit). If prepare must reserve anything on the
  provider side, it belongs to the write path instead.
- Source of truth for connection revocation and install revision. mctl-api has
  no `gcn_` registry today (the `connection_ref` and `install_revision` columns
  exist only on `bridge_commands`). The design adds a `ConnectionChecker`
  interface whose default fails closed (503). Which component owns the real
  check is undecided.
- Who fetches the data. The design lets the end-user principal fetch it with a
  Glovo-audience token through the Glovo MCP surface (`glovoAudienceRoutes`).
  If a relaying surface identity fetches on the user's behalf instead (for
  example `GlovoWorkerUserID`), the principal check must use the relayed subject.
- TTL and size bounds. The design assumes a default read TTL of 600 s (max
  900 s, matching command TTL) and an 8 KiB cap on canonical `data` under the
  existing 16 KiB `bridgeMaxBody`.
- Whether "replay" in the acceptance list also means single-use retrieval. The
  design allows repeated reads within the TTL by the same principal; it does
  not make reads single-use.
