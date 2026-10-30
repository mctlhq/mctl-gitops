# SecurityFinding v1: durable store and REST API (slice 1 of .github#209)

## Context

mctlhq/.github#209 concluded `ADD_SECURITY_FINDING_CONTRACT`: MCTL has several
security signal representations but no provider-neutral lifecycle that
deduplicates observations, binds remediation to exact affected/fixed
revisions, verifies the fix and reopens on regression. Issue mctl-api#774 is
slice 1 of 3 and owns the normative durable contract, Postgres store and REST
API in `mctl-api`. The dependent slices (mctlhq/mctl-agents#778 remediation
and verification runner, mctlhq/mctl-gitops#2103 provider ingestion and
config) are gated on this contract and must not build against the spike's
non-normative flat D4 model.

The contract is a three-level model: `SecurityFinding` (canonical problem
identity and grouping) -> `SecurityOccurrence` (one concrete affected subject,
which owns the lifecycle) -> `RemediationAttempt[]` (durable history of fix
cycles). `ProviderObservation`s are append-only evidence on an occurrence,
and their provider identity comes only from the authenticated ingest
channel. Lessons from the PR #213 review (provider trust, batch delivery
dedup, repeated regression cycles) are normative here.

## User stories

- AS a configured security provider adapter (Trivy, CodeQL, Dependabot, Runtime Assurance, ...) I WANT to submit a batch of observations over my own authenticated channel SO THAT every finding in the batch is recorded once, under my server-known identity, without trusting any identity text in the payload.
- AS the remediation runner (mctl-agents#778) I WANT to start a remediation attempt for one occurrence, bound to an existing WorkItem, and record the landed fix and verification results SO THAT the occurrence moves through a semantic lifecycle without a second work or approval model.
- AS a tenant owner or platform admin I WANT to dismiss an occurrence with an authority reference and a supported reason SO THAT accepted risk is recorded separately from technical remediation.
- AS an auditor I WANT every finding to expose its occurrences, observations, remediation attempts, verifications and transition events SO THAT I can reconstruct why each state change happened across several fix and regression cycles.
- AS a platform operator I WANT provider prose and severity to be inert data SO THAT hostile scanner text can never change state, policy or authority.

## Acceptance criteria (EARS)

### Model and identity

- THE SYSTEM SHALL persist `SecurityFinding` (id prefix `sf_`), `SecurityOccurrence` (`soc_`), `ProviderObservation` (`sob_`), `RemediationAttempt` (`sra_`), `VerificationRecord` (`svr_`) and an append-only occurrence event log as distinct tables, with lifecycle state stored only on the occurrence.
- WHEN an observation is ingested THE SYSTEM SHALL resolve its finding by a normalized canonical problem identity (`cve:`, `ghsa:`, or `rule:<provider_ref>:<rule_id>`) scoped to the tenant, matching on any recorded alias.
- WHEN an observation is ingested THE SYSTEM SHALL compute the occurrence `subject_fingerprint` as SHA-256 over the canonical JSON of the normalized subject (repository/resource, package purl or path+location, artifact digest, service, and for `rule:` identities the rule id) and SHALL create a new occurrence when no occurrence of that finding has the same fingerprint.
- WHEN two observations share the canonical identity but differ in repository, artifact digest, package location or code location THE SYSTEM SHALL record them on two distinct occurrences with independent lifecycle state.
- WHEN observations from two different providers carry the same canonical identity and the same subject fingerprint THE SYSTEM SHALL attach both to one occurrence.
- IF an observation's subject names only a CVE/CWE/rule id and a repository with no package, path, location or artifact identity THEN THE SYSTEM SHALL reject that item with `subject_too_weak`.
- IF an observation's aliases resolve to two different existing findings THEN THE SYSTEM SHALL reject that item with `finding_alias_conflict` and merge nothing.

### Provider trust and ingestion

- WHEN a request reaches `POST /api/v1/security/observations` THE SYSTEM SHALL take `provider_ref` and the provider's maximum verification strength solely from the authenticated security-provider principal configured server-side.
- IF the payload carries a `provider` (or similar) field THEN THE SYSTEM SHALL store it only as untrusted evidence and SHALL NOT use it for identity, dedup scope, authority or verification strength.
- WHILE a security-provider principal is authenticated THE SYSTEM SHALL confine it to the observation ingest route and to tenants listed in its server-side configuration.
- WHEN a batch of up to 100 observations is submitted THE SYSTEM SHALL process each item independently and return one result per item (`created`, `duplicate`, or `rejected` with a code), so that one delivery creating or updating several occurrences never drops later items.
- WHEN the same source observation is redelivered (same provider, same delivery id and same observation content, or same content without a delivery id) THE SYSTEM SHALL return `duplicate` with the original observation id and create no new row or event.
- THE SYSTEM SHALL NOT use `(provider_ref, delivery_id)` alone as a uniqueness key.
- THE SYSTEM SHALL store provider title, description and severity only in a bounded `untrusted` object (title <= 256 bytes, severity <= 32 bytes, description <= 4096 bytes) that no transition, policy or authorization code reads.

### Lifecycle

- THE SYSTEM SHALL support exactly the occurrence states `open`, `triaged`, `fixing`, `awaiting_verification`, `resolved`, `reopened`, `unverifiable` and `dismissed`, and exactly the transitions listed in design.md "Transition table"; any other move SHALL be refused with `invalid_transition` (409).
- THE SYSTEM SHALL NOT expose any generic set-state operation.
- WHEN a remediation attempt is started on an occurrence in `open`, `triaged`, `reopened` or `unverifiable` THE SYSTEM SHALL create a new attempt referencing an existing WorkItem in the same tenant and move the occurrence to `fixing`.
- IF a remediation attempt is started while the occurrence already has an active attempt THEN THE SYSTEM SHALL refuse with `remediation_attempt_active` (409); a database partial unique index SHALL enforce at most one active attempt per occurrence.
- IF the referenced WorkItem does not exist or belongs to another tenant THEN THE SYSTEM SHALL refuse with `work_item_not_found` (404).
- WHEN a landed fix (merged PR / landed revision or artifact digest) is recorded on the active attempt THE SYSTEM SHALL move the occurrence to `awaiting_verification` and never directly to `resolved`.
- IF a verification record's revision or artifact digest does not equal the attempt's landed revision or artifact THEN THE SYSTEM SHALL reject it with `verification_not_bound` (422) and change nothing.
- WHEN a verification with result `passed`, bound to the landed revision/artifact, with a server-derived strength meeting the configured minimum (default `scanner_rerun_exact_revision`) is recorded THE SYSTEM SHALL close the attempt with outcome `resolved` and move the occurrence to `resolved`.
- IF a verification passes but its derived strength is below the configured minimum THEN THE SYSTEM SHALL record it and leave the occurrence in `awaiting_verification`.
- WHEN a provider observation claims `fixed` THE SYSTEM SHALL record it as `provider_claim` evidence and SHALL NOT resolve the occurrence under the default policy.
- WHEN a verification result is `failed` THE SYSTEM SHALL record it, keep the attempt active and move the occurrence back to `fixing`.
- WHEN a verification result is `unavailable`, `error` or `timeout` THE SYSTEM SHALL record it and leave the occurrence in `awaiting_verification`; such a result SHALL never be treated as absence or resolution.
- WHEN a verification result is `unverifiable` THE SYSTEM SHALL move the occurrence to `unverifiable` and keep the attempt history.
- WHEN an observation reporting the problem as present arrives for a `resolved` occurrence, observed after the resolution and not at a revision/artifact recorded as affected before the resolving fix, THE SYSTEM SHALL move the occurrence to `reopened` and record the regression evidence; the next remediation SHALL create a new attempt, preserving all prior attempts, fixes and verifications.
- WHEN an occurrence is dismissed THE SYSTEM SHALL require an authenticated human actor (a human platform admin, or a human holding at least the `owner` tenant role on the occurrence's tenant), an `authority_ref` and a reason in `false_positive|accepted_risk|duplicate|not_applicable|provider_withdrawn`, and SHALL close any active attempt with outcome `cancelled_dismissed`.
- IF a service, agent, surface or provider principal attempts a dismissal THEN THE SYSTEM SHALL refuse with 403.
- WHILE an occurrence is `dismissed` THE SYSTEM SHALL keep recording new observations without changing its state.

### Verification strength

- THE SYSTEM SHALL order strengths `deterministic_regression_test` > `assurance_replay` > `scanner_rerun_exact_revision` > `provider_claim` > `manual`.
- WHEN a verification is recorded THE SYSTEM SHALL derive its strength as the lower of the declared mechanism and the ceiling configured for the authenticated recorder (provider config, `security:remediate` agent/service, or human `manual`), never from free payload text.

### Persistence, audit and reads

- THE SYSTEM SHALL make observations, verification records and occurrence events immutable (BEFORE UPDATE triggers refuse updates) and SHALL record actor, actor principal id, source, reason and timestamp for every transition.
- THE SYSTEM SHALL store references, hashes, revisions and artifact digests, not scanner or code payloads.
- WHEN a caller lists or reads findings or occurrences THE SYSTEM SHALL return only rows in tenants the caller can access (admins see all), answering "not found" for others.
- WHEN `GET /api/v1/security/findings/{id}` is called THE SYSTEM SHALL return the finding with all occurrences, their observations, remediation attempts, verifications and events.
- IF the store is not configured or unavailable THEN THE SYSTEM SHALL answer 503 with `security_findings_store_unavailable`, never an empty list.
- WHEN a mutating request repeats an `Idempotency-Key` with the same body and actor THE SYSTEM SHALL return the original result; with a different body or actor it SHALL refuse with `idempotency_key_reused`.
- THE SYSTEM SHALL document the v1 contract in `internal/openapi/openapi.yaml` and `docs/security-findings.md`.

## Out of scope

- Provider webhook deployment, adapter code and provider token provisioning in gitops (mctl-gitops#2103).
- The remediation and verification execution runner (mctl-agents#778).
- Building a SAST/SCA scanner; Runtime Assurance probe/replay changes.
- Security UI, MCP tools, auto-merge/auto-deploy of fixes.
- A second WorkItem, approval or policy model.
- Claude Security-specific schema assumptions.
- Git ancestry checks for regression detection (see Open questions).

## Open questions

- Tenant attribution: the design requires each observation to name a tenant that is in the provider's configured allowlist. An alternative is deriving tenant from a repository-to-tenant mapping; the issue does not say which #2103 will provide.
- Regression detection without git ancestry: a "present" observation reopens a resolved occurrence only when observed after resolution and not at a revision/artifact recorded as affected before the fix. A scanner rescanning an old, unlisted revision could cause a false reopen; ancestry-aware detection is deferred.
- Placement of `manual` as the weakest strength and whether the minimum strength may be configured below `scanner_rerun_exact_revision` (the design allows it via config but defaults to `scanner_rerun_exact_revision`).
- GHSA-first-then-CVE alias merging: aliases are recorded and matched, but a later observation linking two already-separate findings is rejected (`finding_alias_conflict`) rather than merging them; a merge operation is deferred.
- The spike report `docs/spikes/security-finding-lifecycle.md` and D5 reference tests live in mctlhq/.github and were not readable from this run; the D5 test ports in tasks.md follow the issue text and must be checked against that source during implementation.
- mctl-api's deployed configuration (DB URL, secrets) was not observable from this run (see design.md "Deployed state checked").
