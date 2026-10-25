# Design: issue-774-feat-api-securityfinding-v1-store-and-ap

## Current state

There is no security-finding model in `mctl-api` today. `grep -ri
"SecurityFinding|assurance|security_finding"` over the clone finds nothing
outside OAuth code. The closest existing patterns, which this design reuses:

- **Durable Postgres stores, schema applied at startup.**
  `internal/evidence/store.go` (`NewStore`, `const schema`,
  `const schemaAmendment2`) and `internal/workitems/store.go` (`NewStore`
  runs `schema`, `snapshotSchema`, `actionApprovalSchema`, ...) open a shared
  pool through `internal/pgshared` (`pgshared.Open` / `pgshared.Release`) and
  apply idempotent `CREATE TABLE IF NOT EXISTS` DDL. Immutable tables are
  protected by a `BEFORE UPDATE` trigger (`execution_evidence_no_update`).
  Mutations are serialized per key with `pg_advisory_xact_lock(hashtext($1))`
  in a `withTx` helper (`internal/evidence/store.go`,
  `internal/workitems/store.go` `withTx`).
- **IDs.** `internal/workitems/types.go` defines prefixes
  (`WorkItemIDPrefix = "wi_"`, `ExecutionIDPrefix = "we_"`) and IDs are
  `prefix + uuid.NewString()` (`store.go` `Create`).
- **Semantic transitions, not set-state.** `workitems.Transitions` maps
  `state -> action -> state` as "the single enforcement point for lifecycle
  rules"; `Store.Transition` rejects anything else with
  `ErrInvalidTransition`, surfaced as 409 by `writeWorkItemError`
  (`internal/api/handlers_work_items.go`).
- **Idempotency.** `work_item_create_requests` / `work_item_requests` record
  `(key, request_hash, actor, result_id)`; a different hash or actor yields
  `ErrIdempotencyKeyReuse` (`replayed`, `remember` in `store.go`).
- **Append-only events with actor provenance.** `appendEvent` writes
  `work_item_events` with `actor_principal`, `acting_principal`, `surface`,
  `request_id`, `actor_principal_id`, `via_principal_id`, `via_execution_id`.
- **Narrow service principals from static tokens.** `internal/auth/oidc.go`
  defines the evidence-writer principal (`EvidenceWriterUserID =
  "service:mctl-agents-evidence"`, `PermissionEvidenceWrite`,
  `evidenceWriterToken()` refusing short tokens or tokens equal to any other
  configured token), verified by `evidenceWriterProvider` in
  `internal/auth/provider_static.go`. `evidenceWriterGate`
  (`internal/api/handlers_evidence.go`) confines that principal to its
  append routes; `router.go` installs it in the authenticated group next to
  `usageWriterGate`, `registryPublisherGate` and `ciPrincipalGate`.
  `User.HasPermission` lets agent principals hold exactly the permissions
  their run token was minted with (`internal/workitems/agent_run_tokens.go`
  `Permissions`), which is how #778's runner can receive a narrow permission.
- **Authorization helpers.** `canSeeWorkItem` / `visibleWorkItem`
  (tenant-scoped visibility, "not found" for invisible rows),
  `isDirectService`, `isHumanAdmin` (`handlers_action_approvals.go`),
  `requireTenantRole` with `operations.RoleOwner`
  (`internal/api/tenant_role.go`, `internal/operations/roles.go`).
- **Store wiring.** `cmd/api/main.go` builds the evidence store from
  `EVIDENCE_DB_URL` falling back to `AUDIT_DB_URL`, honours
  `EVIDENCE_DISABLED`, and passes `Evidence: evidenceStore` into router
  options; a nil store makes every route 503
  (`requireEvidenceWriter` returns `codeEvidenceStoreUnavailable`).
  Write-heavy producer routes live in their own `httprate` group
  (`/evidence/records`, `/decisions`) so retries are not throttled into
  gaps.
- **Contract docs.** `internal/openapi/openapi.yaml` (embedded, parsed by
  `internal/openapi/embed_test.go`) and `docs/execution-evidence.md`,
  `docs/work-context-contract.md` (correlation over foreign keys).
- **Tests.** Postgres-backed store tests skip unless `TEST_DATABASE_URL` is
  set (`internal/evidence/store_test.go`); handler tests use the in-package
  harness in `internal/api`.
- MCP: no tools are added, so the tool-count expectation in
  `internal/mcp/server_test.go` is untouched.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)`: returned
  "service not found: admins/mctl-api". mctl-api is not a catalogue tenant
  service; its deployed config could not be observed this way.
- `$MCTL_GITOPS_ROOT/services/*/`: listed `admins`, `karabu`, `labs`; no
  `mctl-api` directory exists there. Not observed, not "absent".
- `helm/values.yaml` in the clone (chart defaults, not deployed values):
  `replicaCount: 1`; documents the optional Secret holding
  `MCTL_EVIDENCE_WRITER_TOKEN` and the `AUDIT_DB_URL` CNPG wiring. Whether
  `EVIDENCE_DB_URL` is set in production was not observable.

## Proposed solution

### 1. New package `internal/securityfindings`

Files: `types.go` (constants, input structs, validation, transition table,
strength ordering), `identity.go` (canonical identity and subject
fingerprint), `store.go` (schema, `NewStore`, `withTx`), `ingest.go`,
`remediation.go`, `read.go`.

ID prefixes: `sf_` finding, `soc_` occurrence, `sob_` observation, `sra_`
remediation attempt, `svr_` verification record. Schema label
`securityfinding/v1`.

### 2. Schema (applied idempotently in `NewStore`)

```
security_findings(
  id PK 'sf_%', tenant, identity_kind ('cve'|'ghsa'|'rule'),
  identity_key,                      -- e.g. cve:CVE-2024-1234
  created_at, last_observed_at, schema_version,
  UNIQUE (tenant, identity_key))

security_finding_aliases(
  tenant, alias_key, finding_id -> security_findings,
  PRIMARY KEY (tenant, alias_key))

security_occurrences(
  id PK 'soc_%', finding_id -> security_findings, tenant,
  subject_fingerprint,               -- sha256 hex
  subject JSONB,                     -- normalized subject, no payloads
  state, state_version BIGINT,
  active_attempt_id TEXT NULL,       -- projection
  current_affected_revision, current_affected_artifact,   -- projection only
  dismissal_reason, dismissal_authority_ref, dismissed_by,
  created_at, updated_at, last_observed_at,
  UNIQUE (finding_id, subject_fingerprint),
  CHECK (state IN (...8 states...)))

security_observations(                -- immutable (trigger)
  id PK 'sob_%', occurrence_id, tenant,
  provider_ref,                      -- from authenticated principal
  observation_hash,                  -- dedup key, see section 4
  delivery_id, source_finding_id,
  claimed_action ('present'|'fixed'|'absent'|'withdrawn'),
  observed_revision, observed_artifact_digest,
  evidence_refs JSONB, evidence_digest,
  untrusted JSONB,                   -- title/description/severity/claimed provider
  observed_at, ingested_at, ingested_by_principal_id,
  UNIQUE (provider_ref, observation_hash))

security_remediation_attempts(
  id PK 'sra_%', occurrence_id, tenant, seq INT,
  work_item_id 'wi_%', execution_id, devloop_workflow_id,
  started_by, started_by_principal_id, start_source,
  affected_revisions JSONB,          -- revisions/artifacts observed present before start
  candidate_revision, landed_revision, landed_artifact_digest, landed_ref,
  outcome NULL | 'resolved'|'superseded'|'cancelled_dismissed',
  started_at, landed_at, ended_at,
  UNIQUE (occurrence_id, seq))
CREATE UNIQUE INDEX ... ON security_remediation_attempts (occurrence_id)
  WHERE outcome IS NULL;            -- at most one active attempt

security_verifications(               -- immutable (trigger)
  id PK 'svr_%', attempt_id, occurrence_id,
  mechanism, declared_strength, derived_strength,
  result ('passed'|'failed'|'unavailable'|'error'|'timeout'|'unverifiable'),
  revision, artifact_digest, evidence_refs JSONB,
  recorded_by, recorded_by_principal_id, source_observation_id NULL,
  recorded_at)

security_occurrence_events(           -- immutable (trigger)
  occurrence_id, seq, kind, from_state, to_state,
  actor_principal, actor_principal_id, via_principal_id, source,
  reason, refs JSONB, created_at, PRIMARY KEY (occurrence_id, seq))

security_requests(                    -- idempotency, like work_item_requests
  scope, idempotency_key, operation, request_hash, actor, result_id, created_at,
  PRIMARY KEY (scope, idempotency_key))
```

`work_item_id` is a correlation, not a foreign key, consistent with
`docs/work-context-contract.md` and the evidence store, so history survives
`WORKITEM_RETENTION_DAYS` purges. The WorkItem is validated at attempt start
through the work-items store (`workitems.Store.Get`) and tenant equality.

No mutable `vulnerable_rev`/`fixed_rev` pair is authoritative: revisions live
on observations, attempts (`affected_revisions`, `landed_*`) and
verifications. `current_affected_*` and `active_attempt_id` are read
projections, updated in the same transaction.

### 3. Canonical identity and subject fingerprint (`identity.go`)

- Problem identity: upper-cased `CVE-YYYY-N` -> `cve:`; `GHSA-xxxx-xxxx-xxxx`
  lower-cased -> `ghsa:`; otherwise `rule:<provider_ref>:<rule_id>` (rule
  identities are provider-scoped because rule ids are not portable). If an
  item carries a CVE and GHSA aliases the CVE is canonical and the GHSA is
  stored as an alias. Lookup is by any alias; aliases mapping to two
  findings -> `finding_alias_conflict` for that item.
- Subject: `{repository, resource, package_purl (name@version stripped of
  qualifiers order), path, location (start_line:end_line or symbol),
  artifact_digest (sha256:...), service, rule_id (rule identities only)}`.
  Normalized (lowercase host/owner/repo, trimmed paths), serialized as
  sorted-key canonical JSON, SHA-256. Minimum strength: repository or
  resource AND at least one of package_purl, path, location, artifact_digest;
  otherwise `subject_too_weak`. Revision is **not** part of the fingerprint
  (it changes across fixes); artifact digest is, so source and deployed
  artifact states remain distinct occurrences.

Cross-provider dedup is therefore exactly "same canonical identity + same
normalized subject". A CVE or rule id alone can never merge two
occurrences.

### 4. Ingestion and provider trust

New principal kind in `internal/auth`, modelled on the evidence writer:

- `SECURITY_PROVIDERS` (non-secret JSON from helm values):
  `[{"ref":"trivy","max_strength":"scanner_rerun_exact_revision","tenants":["admins"]}, ...]`.
- `MCTL_SECURITY_PROVIDER_TOKENS` (Secret; `ref=token` lines). Each token
  is validated like `evidenceWriterToken()` (>= `minSurfaceTokenLen`, unique
  across all other configured tokens, unique per provider); a provider with
  no token or no config entry is disabled with an error log.
- A `securityProviderProvider` in `provider_static.go` verifies the token and
  mints `User{ID: "service:security-provider:<ref>", securityProvider: ref}`.
  `User.SecurityProviderRef()` exposes it; `HasPermission(PermissionSecurityIngest)`
  is true for it and for admins.
- `securityProviderGate` in `internal/api/handlers_security_findings.go`
  confines that principal to `POST /api/v1/security/observations`, installed
  in `router.go` beside `evidenceWriterGate`; `evidenceWriterGate` and the
  others need no change since they only restrict their own principals.

The handler ignores any payload `provider` for authority; it is copied into
`untrusted.claimed_provider`. An admin ingesting directly (bootstrap/testing)
gets `provider_ref = "admin:<user id>"` with ceiling `provider_claim`.

Batch request: `{"delivery_id": "...", "observations": [ {tenant, identity,
aliases[], subject{}, source_finding_id, claimed_action, observed_revision,
observed_artifact_digest, evidence_refs[], observed_at, untrusted{}} ] }`,
max 100 items, body cap 1 MiB. Each item runs in its own transaction under
advisory lock `security-finding:<tenant>:<identity_key>`; the response is
200 with `results[i] = {status: created|duplicate|rejected, code?,
finding_id, occurrence_id, observation_id, transition?}`.

`observation_hash = sha256(canonical JSON {identity_key, subject_fingerprint,
source_finding_id, claimed_action, observed_revision,
observed_artifact_digest, delivery_id, evidence_digest})`, unique per
`provider_ref`. Consequences: redelivery of the same delivery is a
`duplicate`; several findings in one delivery get distinct hashes; the same
state seen in a new scan delivery is new evidence and updates
`last_observed_at`. `(provider_ref, delivery_id)` is never a key by itself.

Effects of an observation on the occurrence (no other code path reads
`untrusted`):

| claimed_action | occurrence state | effect |
|---|---|---|
| present | new | create in `open` |
| present | resolved | `reopened` if `observed_at > resolved_at` and revision/artifact not in the resolving attempt's `affected_revisions`; else recorded only |
| present | others | recorded, projection updated |
| fixed | any | recorded as `provider_claim`; if `awaiting_verification` and bound to landed revision, a `svr_` with derived_strength `provider_claim`, which cannot meet the default minimum |
| absent | awaiting_verification | if bound to the landed revision/artifact, a `passed` verification at strength `min(scanner_rerun_exact_revision, provider max_strength)`; unbound -> recorded only |
| withdrawn | any | recorded only; a human may dismiss with `provider_withdrawn` |

### 5. Transition table (occurrence)

```
open|reopened         --triage-------------> triaged
open|triaged|reopened|unverifiable --start_remediation--> fixing   (new attempt)
fixing                --record_fix(landed)--> awaiting_verification
awaiting_verification --verify(passed, bound, strength>=min)--> resolved (attempt outcome resolved)
awaiting_verification --verify(failed)-------> fixing (attempt stays active)
awaiting_verification --verify(unavailable|error|timeout)--> awaiting_verification
awaiting_verification --verify(unverifiable)--> unverifiable (attempt outcome superseded at next start)
resolved              --observe(present, regression rule)--> reopened
open|triaged|fixing|awaiting_verification|reopened|unverifiable --dismiss--> dismissed
```

Encoded as `Transitions map[string]map[string]string` in `types.go`, the
same single enforcement point as `workitems.Transitions`. `resolved` and
`dismissed` accept only the listed moves. Every transition writes a
`security_occurrence_events` row with actor, principal ids, source
(`provider:<ref>`, `api`, `agent:<name>`) and reason, and bumps
`state_version`. Mutating routes accept `expected_state_version` (optional)
and `Idempotency-Key`. When a new attempt starts on `unverifiable`, the
previous attempt is closed with outcome `superseded` in the same
transaction.

### 6. Verification strength

`types.go` defines the ordered enum. `derived_strength = min(declared
mechanism, recorder ceiling)` where the ceiling is: provider config
`max_strength` for provider principals; `deterministic_regression_test` for
direct service or agent principals holding `security:remediate`
(`PermissionSecurityRemediate`); `manual` for human admins / tenant owners
recording a manual verification. `assurance_replay` additionally requires an
evidence ref of kind `assurance_finding` (the existing AssuranceFinding /
replay reference, opaque to mctl-api). Minimum for resolution:
`SECURITY_FINDING_MIN_VERIFICATION_STRENGTH`, default
`scanner_rerun_exact_revision`; an unknown value fails startup of the
store (routes 503) rather than silently weakening policy.

Binding rule: a verification must carry `revision` equal to the attempt's
`landed_revision` and/or `artifact_digest` equal to `landed_artifact_digest`
(each one that the attempt has set must match); otherwise 422
`verification_not_bound`.

### 7. REST routes (`internal/api/handlers_security_findings.go`)

Reads (authenticated, tenant-filtered via `HasTenantAccess`, admins all):
- `GET /api/v1/security/findings?tenant=&state=&repository=&identity=&limit=&cursor=`
- `GET /api/v1/security/findings/{id}` — finding + occurrences + observations + attempts + verifications
- `GET /api/v1/security/occurrences?finding_id=&tenant=&state=&repository=`
- `GET /api/v1/security/occurrences/{id}` — occurrence with full history and events

Writes:
- `POST /api/v1/security/observations` — provider principal or admin (own httprate group, like `/evidence/records`).
- `POST /api/v1/security/occurrences/{id}/triage` — tenant `developer`+ human, admin, or `security:remediate`.
- `POST /api/v1/security/occurrences/{id}/remediation-attempts` — `{work_item_id, execution_id?, devloop_workflow_id?, start_source}`; direct service, `security:remediate` agent, or tenant `developer`+ human.
- `POST /api/v1/security/remediation-attempts/{id}/fix` — `{candidate_revision?, landed: bool, landed_revision?, landed_artifact_digest?, landed_ref?}`; same callers. `landed=true` requires a revision or digest.
- `POST /api/v1/security/remediation-attempts/{id}/verifications` — `{mechanism, result, revision?, artifact_digest?, evidence_refs[]}`.
- `POST /api/v1/security/occurrences/{id}/dismiss` — `{reason, authority_ref, note?}`; human only (`isHumanAdmin` or `requireTenantRole(..., operations.RoleOwner, ...)`, with `isDirectService`/agent/surface/provider refused).

Errors via `writeErrorCode` with typed codes: `security_findings_store_unavailable`
(503), `not_found`, `invalid_transition`, `remediation_attempt_active`,
`verification_not_bound`, `subject_too_weak`, `finding_alias_conflict`,
`idempotency_key_reused`, `version_conflict`, `invalid_request`.

### 8. Wiring

`cmd/api/main.go`: `SECURITY_FINDINGS_DB_URL` -> `EVIDENCE_DB_URL` ->
`AUDIT_DB_URL` fallback, `SECURITY_FINDINGS_DISABLED`, `initStore(...,
"security-findings", ...)`, `securityfindings.WithWorkItems(workItemsStore)`
for WorkItem validation. `RouterOptions.SecurityFindings
*securityfindings.Store`; nil -> 503. Helm: optional
`securityProviders` values -> `SECURITY_PROVIDERS` env and an optional
existing Secret for `MCTL_SECURITY_PROVIDER_TOKENS`, same shape as the
evidence-writer Secret block in `helm/values.yaml`.

### 9. Docs

`docs/security-findings.md`: normative v1 contract (model, identity and
fingerprint rules, provider trust, dedup key, transition table, strength
ordering and binding, dismissal, untrusted fields, error codes, rollout gate
for #778/#2103). `internal/openapi/openapi.yaml`: all routes and schemas
under a `SecurityFindings` tag.

## Alternatives

1. **Copy the spike's flat D4 model (one finding row with `vulnerable_rev`/`fixed_rev` and one WorkItem).** Dropped: the issue states D4 is non-normative; a single mutable revision pair loses history across regression cycles and cannot represent several independently remediated occurrences.
2. **Store findings as WorkItems (a `security` kind on `work_items`).** Dropped: WorkItem states (`active/waiting/completed/...`) are execution-oriented and terminal; reopen-on-regression and verification strength would need a parallel state model inside WorkItems, which is the "second work/approval model" the issue forbids in reverse. Attempts reference WorkItems instead.
3. **Trust a `provider` payload field with a shared ingest token (e.g. reuse the evidence writer).** Dropped: any holder could claim to be `mctl-assurance` and upgrade strength; reusing the evidence-writer principal would also widen its gate. Per-provider tokens give the server-derived `provider_ref` the issue requires.
4. **Dedup by `(provider, delivery_id)`.** Dropped: it drops all but the first finding in a batch (the PR #213 finding). Content-hash per provider, including delivery id, handles both batches and redelivery.

## Platform impact

- **Migrations:** new tables only, created idempotently at startup in the existing evidence/audit database; no change to existing tables. Constraints are created with the table, so no `NOT VALID` dance is needed.
- **Backward compatibility:** purely additive routes and principal kind; no MCP tool change; existing gates untouched. With no providers configured, only admins can ingest; with no DB URL the routes answer 503.
- **Resources:** a few small tables; observations grow with scan volume. Retention for observations is not in this slice (see Risks). Per-item transactions bounded to 100 items per request; dedicated rate-limit bucket.
- **Security risks and mitigations:**
  - Provider spoofing -> provider identity only from token; per-provider tenant allowlist; strength ceilings from server config.
  - Hostile provider text -> stored in bounded `untrusted` JSONB, never read by store transition code (typed inputs exclude it); tested with state-changing text.
  - False resolution -> binding to landed revision/artifact, minimum strength, `fixed` claims capped at `provider_claim`, error/timeout never resolves.
  - False reopen from rescans of old revisions -> `affected_revisions` exclusion and observed-after-resolution rule; residual risk recorded as an open question.
  - Token sprawl -> token validation refuses short or reused tokens, same as `evidenceWriterToken()`.
- **Rollout:** ship disabled-by-config (no providers); #2103 adds provider config/tokens; #778 is minted `security:remediate`. Both wait for this release.
