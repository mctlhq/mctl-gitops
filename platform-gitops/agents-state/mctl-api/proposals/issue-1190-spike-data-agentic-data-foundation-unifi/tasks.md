# Tasks: issue-1190-spike-data-agentic-data-foundation-unifi

Scope of this proposal's implementer grant: **Slice S0 only**. S0 is a docs-only PR under
`docs/research/agentic-data-foundation/`. Tasks S1 to S4 are specified here so that they can be
reviewed. Each of them needs its own proposal and its own owner approval before any work starts.

## S0: decision package (this proposal)

- [ ] 1. Write `inventory.md`. Start from the design.md tables. Give every row a SHA-pinned
  file:line link and one label: VERIFIED_CODE, desired state (manifest), VERIFIED_DEPLOYMENT,
  PROPOSED, UNKNOWN or BLOCKED.
  - Add a row for each of the following: mctl-telegram `internal/pa/memory.go`, mctl-agents
    `orchestrator/context_snapshot.py` and its importers (`human_input.py:31`,
    `capability.py:56`), and mctl-docs `package.json` with `scripts/generate-llms-full.ts`.
  - Record the gaps: `WORKITEM_RETENTION_DAYS` has no sweep in the code, and the env values and
    Argo health are not observable.
  - DoD: no row lacks a label or a pin. No manifest value is labelled VERIFIED_DEPLOYMENT.
- [ ] 2. Write `owners-duplicates.md`: the owner map for .github#342, .github#339,
  mctl-telegram#1488 and #1325, mctl-docs#237, mctl-agents#989 and #1127, and .github#309.
  - Include the duplicate list: the `cs_` versus `cs-` snapshot ids; the Python and Go
    ContextSnapshot contracts; `surface_identity_links` versus `external_identities` mirroring;
    and evidence refs as an existing projection.
  - DoD: each item has one owner, and #1190 owns only the vocabulary, the trace contract, the
    benchmark and the decision.
- [ ] 3. Write `vocabulary.md`: entity, assertion and event fields, the assertion kinds, the
  classification and trust domains, the stable assertion key and immutable revision identity (including ambiguous-source handling and same-version conflicts), the supersede and tombstone rules, reversible merges and
  splits, and the DevLoop edge set. Depends on 1.
  - DoD: every field maps to an existing column where one exists, or is marked NEW (logical
    only).
- [ ] 4. Write `threat-model.md`: assets, threats and controls as in design section 5. Each control
  references a negative test id below. Depends on 3.
  - DoD: no control is left without a test id.
- [ ] 5. Write `fixture-spec.md` and `queries.md`.
  - Cover the generator seed, the S and L parameters, the three export formats, Q1 to Q11 (including Q10a-c identity/conflict/retraction fixtures) and E1
    to E4, each with ground-truth semantics.
  - Add `fixture.lock.template` and `versions.lock.template` with empty digests, plus the
    `verify-lock` rule.
  - DoD: every acceptance item in the issue maps to at least one query.
- [ ] 6. Write `harness-spec.md`: the pre-dial checks, the post-dial identity checks, the sentinel,
  the internal network, the limits and owned-only cleanup, as in design section 4.
  - DoD: every check names its refusal test (H1 to H10).
- [ ] 7. Write `benchmark-plan.md`.
  - Cover the metrics list, cold and warm methodology, at least 30 repeats with 5 warmups, cgroup
    sources for peak cgroup memory (not RSS) and CPU, the pinned offline tokenizer labelled "estimate", the hardware
    record, the bootstrap confidence intervals and a sensitivity sweep over 10^2 to 10^6 queries
    per day.
  - Include an empty results matrix in which every cell is UNKNOWN.
  - DoD: the plan contains no numeric result.
- [ ] 8. Write `adr-candidate.md` (status Proposed) with the hard gates, the soft comparison, the
  outcome rules and the current recommendation of DEFER, with its falsifiable hypothesis.
  Depends on 4 to 7.
  - DoD: the 2x and 3x multipliers are absent. The budgets are marked "owner to confirm after S1
    baseline".
- [ ] 9. Write `traceability.md`: R2-1 to R2-6, mapped to design section, task, negative test and
  evidence artifact. Depends on 1 to 8.
  - DoD: every R2 item has a row with no empty cell.
- [ ] 10. Write a slice plan inside `README.md`: S1 to S4 and the conditional AGE slice, each with
  its scope, inputs, exit criteria and the statement "separate approval required".
  - DoD: no task in S0 creates code that is compiled or run.

## S1 (separate approval): harness guard, fixture, A and B

- [ ] 11. Write the `internal/research/agenticdata/guard` package (build tag `research`):
  - pure pre-dial checks;
  - a recording dialer;
  - post-dial identity checks;
  - sentinel verification;
  - label-scoped cleanup.

  DoD: H1 to H10 pass.
- [ ] 12. Write the fixture generator (seeded, JCS hash through `internal/jcs`, `secretscan` gate)
  with SQL, N-Quads and Graphiti exports.
  - DoD: two runs produce an identical `fixture.lock`.
- [ ] 13. Build candidate A: the trace composer over the existing store read methods. Depends on
  11 and 12.
  - DoD: Q1 to Q11 run, and each link is marked present, missing or conflict.
- [ ] 14. Build candidate B: `research_projection` with an idempotent build, `WITH RECURSIVE ...
  CYCLE`, tenant predicates applied inside the recursion, and tombstone invalidation. Depends on
  11 and 12.
  - DoD: Q1 to Q11 run, including Q10a-c; distinct assertion keys and revisions survive, exact replay dedupes, conflicting revisions remain visible, and targeted retraction prevents stale resurrection. No source/predicate upsert. Any query that cannot be expressed is recorded as "AGE trigger".

## S2 (separate approval): RDF candidates

- [ ] 15. Fuseki (Fuseki 2 line) with TDB2: per-tenant named graphs, union graph off, query
  timeout, restricted rule reasoner, Jena SHACL. Exact versions and digests are recorded in
  `versions.lock`.
  - DoD: Q1 to Q11 and E1 to E4 run, or are recorded as BLOCKED.
- [ ] 16. Oxigraph with an external materialization pass and pinned pySHACL. The overhead of
  those layers is measured separately.
  - DoD: the same as 15.

## S3 (separate approval): Graphiti

- [ ] 17. Write the semantics comparison: backend and model dependencies, the bi-temporal edge
  fields, and how invalidation maps to `inferred`. Then attempt a pre-extracted-facts replay with
  no external call.
  - DoD: the results are labelled PARTIAL_COVERAGE, or BLOCKED with the exact reason.

## S4 (separate approval): results and decision

- [ ] 18. Fill the results matrix, the confidence intervals and the sensitivity sweep. Apply the
  ADR decision rule and propose budgets from the baseline for owner confirmation.
  - DoD: one outcome is chosen. Every cell is MEASURED, UNKNOWN or BLOCKED.

## Tests

S0 review checks:
- [ ] T1. Every inventory row has a pin and a label, and no manifest-only value is labelled
  VERIFIED_DEPLOYMENT. Checked by grep in review.
- [ ] T2. The traceability matrix has no empty cell, and every threat-model control references a
  test id.
- [ ] T3. The S0 diff touches only `docs/research/**`. `go build ./cmd/api` and the
  `server_test.go` tool count are unchanged.

Harness refusal tests (S1). In every case the recording dialer asserts zero dials or zero writes:
- [ ] H1. The DSN host `shared-pg-rw.platform-db.svc` is refused before any dial.
- [ ] H2. A remote or public IP, and `*.cluster.local`, are refused before any dial.
- [ ] H3. `KUBECONFIG`, `VAULT_TOKEN`, `AUDIT_DB_URL` or `WORK_ITEMS_DB_URL` present in the
  environment: start is refused.
- [ ] H4. The generic CI `TEST_DATABASE_URL` (`postgres:postgres@localhost/mctl_api_test`) is
  refused: wrong database name, no sentinel.
- [ ] H5. A disposable container without a sentinel is refused before the first write.
- [ ] H6. A sentinel with the wrong nonce is refused.
- [ ] H7. A `system_identifier` that does not match the value captured at creation (a second
  container behind the same address) is refused.
- [ ] H8. Cleanup of an unlabelled container, a foreign label or a foreign schema is refused.
- [ ] H9. Limits: a runaway recursive query is killed by `statement_timeout`, and the SPARQL query
  timeout fires.
- [ ] H10. Running `go test ./...` without the `research` tag compiles and runs no harness code.

Negative benchmark tests (S1 to S3). Every candidate must pass:
- [ ] N1. Cross-tenant traversal or entailment returns zero rows or triples (Q1, E4).
- [ ] N2. A same-name or same-email decoy produces zero links. Reversing an erroneous link leaves
  the grants unchanged (Q8).
- [ ] N3. After revocation, the action is denied by the authority read even when the projection is
  stale. An unreachable authority also gives a denial (Q9).
- [ ] N4. After deletion, zero residual rows, triples, inferred edges, index entries or cache
  entries remain (Q9).
- [ ] N5. The public-docs query returns zero private nodes. An injected instruction string is
  returned as a literal only (Q6).
- [ ] N6. The negative causal control does not appear (Q3).
- [ ] N7. Feedback cannot promote an inferred assertion or change its kind.
- [ ] N8. Replay of duplicate or shuffled events gives identical projection digests (Q10). Q10a-c: same source/predicate across subjects and multiple values retain all keys; same-key/version divergent digests return an explicit conflict; targeted correction/tombstone does not delete sibling facts or resurrect on stale replay; tenant lookalikes cannot collide. Verify identical ground truth in A/B and RDF assertion/revision IRIs; distinguish source lacking stable fact ID as ambiguous, never auto-merge.
- [ ] N9. An invalid SHACL instance fails, a malformed shape errors, and an unsupported feature
  reports `unsupported` (E2, E3).
- [ ] N10. A missing review and a conflicting approval digest are marked as such, not silently
  dropped (Q11).
- [ ] N11. A run with an empty digest in `versions.lock` refuses to start.

## Rollback

S0 is documentation only. To roll back, revert the PR. No runtime, schema, helm or env change
exists to undo.

For S1 to S3, the harness removes only the containers, networks and volumes labelled
`mctl.research.run=<run_id>`. `docker ps -a --filter label=mctl.research.run` verifies that
nothing remains. Reverting the PR removes the build-tagged code. No production state is ever
created, so there is no production rollback.
