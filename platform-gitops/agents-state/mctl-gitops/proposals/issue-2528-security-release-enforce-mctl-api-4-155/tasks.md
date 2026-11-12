# Tasks and acceptance proof: amended #2528

All implementation boxes remain unchecked. This amendment is preparation only;
independent final-content review and a new digest-bound human implementation
grant are required. Do not edit .status.yaml or decide/consume the old grant.

## Delivery sequence

- [ ] 1. Pin the current bootstrap, API chart/source, ruleset/identity inventory
  and the existing positive/negative gate reproductions. Retain the R0 hold and
  record all unknown write/credential paths. DoD: source citations and the five
  findings below are linked to their replacement contracts, not marked fixed
  merely because this proposal merged.
- [ ] 2. Implement policy/packet/allow validation in the existing gate, with one
  canonicalization/hash algorithm and duplicate/unknown-field rejection. Add
  trusted owner IDs and protected-file hashing; leave live allow empty. DoD:
  R1 fields/relations and historical-state versus new-effect cases pass fixtures.
- [ ] 3. Implement the read adapter for MCTL decision/consume, GitHub PR/review/
  git provenance and GHCR digest/config evidence. Contract-test the release
  intent and direct-human binding against the actual pre-release API behavior;
  never weaken registered-policy or authority settings. Missing capabilities
  block readiness pending separate approved prerequisites. DoD: T1-T3 below.
- [ ] 4. Implement the credential-free Helm renderer and env-source graph,
  including key contracts proven against runtime producer source. Keep the
  existing values-block reader. DoD: the real baseline passes; T9-T10 fail
  closed; no live Secret or real credential is read.
- [ ] 5. Implement effect classes and separate detector/admission semantics.
  Update both bump producers, patch application/conflict rules, shape guard,
  auto-merge handoff and diff logic for the exact API tag+chart pair. Preserve
  all unrelated-service restrictions. DoD: the full positive path T7 and the
  mutation/negative controls T8 run against disposable bare remotes.
- [ ] 6. Add the default-branch pull_request_target checker, dedicated App
  context and explicit trusted-policy reads. DoD: head/workflow/script/policy
  substitutions and a same-named generic Actions success cannot satisfy T4.
- [ ] 7. Implement the broker's fresh base/head/evidence reads, atomic API
  consume, deadline, strict/exact-head merge and crash reconciliation. Remove
  direct guarded merges from auto-merge; fail closed if broker unavailable.
  DoD: T5-T6, including crash after green/consume, leave no unauthorized write.
- [ ] 8. Prepare exact checker/broker App, environment and ruleset payloads for
  the owner, including separate update-authority and PR/check enforcement rules.
  Coordinate writer migration with #2543 before cutover; prove normal DevLoop,
  deployment and rollback continuity. DoD: disposable GitHub repository tests
  show the broker can merge an authorized PR, cannot push main or skip checks,
  and all non-broker ordinary actors cannot merge even with a stale green check.
  No production actor/credential/ruleset mutation occurs under this task alone.
- [ ] 9. Owner/operator separately authorizes and performs the proven staged
  cutover. If capability or migration evidence is missing, keep the gate inert
  and release NO-GO. DoD: live authority/rules/checker IDs match approved
  payloads; representative ordinary workflows are healthy; bypass/cluster-admin
  residuals are explicitly inventoried. Do not report P2-2/P2-3 enforced early.
- [ ] 10. Update the write-path runbook and canonical R0 packet with final-head
  code links, implementation versus enforced status, approval provenance,
  positive/mutation evidence, residuals and rollback. Independent implementation
  review must have no unaddressed P1/P2. Implementation completion is not BUILD
  GO, DEPLOY GO, DDL permission or Glovo activation.

## Test groups (all necessary before enforcement)

Use synthetic identities/artifacts, injectable provider answers, exact baseline
fixtures and disposable remotes/repositories; never attack production. Every
negative effect test proves no target-main SHA change and no unauthorized
release-bump publication. UNKNOWN outranks a concurrent observed violation.

- [ ] T1 / P2-1: a valid packet and direct-human decision pass. Unrelated intent,
  implementation aar used as release grant, copied grant, missing decision
  binding, wrong owner, delegated/service decider, disabled principal, stale
  context, expired freshness, policy drift or failed ledger reads refuse.
  Test the atomic consume race: exactly one attempt can spend the decision.
- [ ] T2 / P2-1: reject arbitrary release_head, a different release PR, missing
  final-head reviews, changed source_tree, tag/source mismatch, wrong image
  label/digest, chart_revision != source_commit and changed trusted policy.
  Verify all OCI runnable platforms and explicit attestation handling. Provider
  pagination failure, malformed responses, registry/git reads failing and
  missing immutable packet/provenance are UNKNOWN, never an empty clean set.
- [ ] T3 / P2-1: owner decision on the packet reference/content is preserved
  through allow-only publication. Packet mutation, unrelated allow PR, missing exact-head owner review, unexpected
  merger, wrong numeric/principal mapping, policy hash including its own allow,
  a security-code change after approval and a missing configured owner refuse.
  Reject missing admission/revalidation capability; never silently relax it.
- [ ] T4 / P2-2: remove the PR's trusted step, replace its workflow/script or
  local dependencies, edit PR policy and forge release-hold via GitHub Actions.
  None satisfy the App-bound check. Canary code in the PR must never run in the
  privileged checker. Fail on head/base fetch mismatch or leaked render access.
- [ ] T5 / P2-3: between CI and merge expire the decision, retarget the registry
  tag, tighten base policy, move the head, change reviews and race the base.
  Each forces fresh evaluation or refusal; no stale merge. New merges/rollback
  writes require freshness, while unchanged deployments/restarts do not.
- [ ] T6 / P2-3: crash before/after consume and after posting a successful
  check; leave a stale green result; make a merge response ambiguous. Non-broker
  actors cannot merge, consumed grants cannot replay and UNKNOWN cannot retry
  a write blindly. A proven completed effect is reconciled once; a proven
  unperformed effect needs a new human decision. Test broker failure closed.
- [ ] T7 / P2-4 positive control: packet-only PR -> real synthetic human decision
  -> allow-only PR (grant remains approved/unspent) -> combined tag+chart PR
  -> guarded merge (one consume) -> observed exact
  deployment diff. Exercise BOTH bump producers, shape/apply/merge guards and
  detector/admission interfaces, including grant-only policy publication.
- [ ] T8 / P2-4 negative controls: wrong or absent pin, pin-only or tag-only API
  release, extra env/marker/second-source changes, mixed policy+effect, changed
  packet, conflict resolution reverting a neighboring line and stale bump all
  refuse. Other services' valid tag-only releases remain positive controls.
- [ ] T9 / P2-5: render the real bootstrap + pinned API chart successfully and
  detect each forbidden key in env, valueFrom, envFrom prefixes, desired
  ExternalSecret keys and proven producer output. New sources outside old
  globs must be resolved or UNKNOWN; they must not evade observation.
- [ ] T10 / P2-5: malformed/duplicate YAML, inline/unresolved Helm, escaped or
  computed keys, ambiguous references, incomplete render profiles, unknown
  producer keys, missing files and failed reads are UNKNOWN/refused. A regex
  scan cannot turn the failure green. Assert no credentials, network, live
  Secret payload access or execution of candidate scripts during rendering.
- [ ] T11 / mutation proof: remove each new binding, trusted-source rule,
  effect/authority check, expiry/deadline, read-failure branch and graph-coverage
  check in turn. A named T1-T10 test must fail; restore it and confirm pass.
  Run the existing worker gate, bootstrap hold, diff, route and write-path tests.

## Review closure map

| Finding | Replacement contract | Required evidence |
|---|---|---|
| P2-1 authority/head binding | requirements R1; design 2 | T1-T3 |
| P2-2 PR-controlled trust | requirements R2; design 3 | T4 and authority cutover |
| P2-3 stale merge | requirements R3; design 4 | T5-T6 and authority cutover |
| P2-4 impossible positive path | requirements R4; design 5 | T7-T8 through real callers |
| P2-5 parser fallback | requirements R5; design 6 | T9-T10 on baseline and failures |

All five require independent review of this new content before a fresh human
implementation grant. This mapping is a specification correction, not evidence
that unimplemented controls or production enforcement already pass.
