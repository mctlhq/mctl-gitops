# Tasks and acceptance proof: #2528

All boxes are unchecked. Nothing starts before an independent review of this
content and a fresh digest-bound #1022 human implementation decision. Do not
edit .status.yaml or decide/consume an old grant. No task adds an allow record,
releases, tags, builds, bumps or syncs mctl-api, reads Secret data, or changes
keys, rulesets, Apps or environments; those are prepared here and applied by
the owner. Every PR below touches protected paths and is human-merged until
cutover; none is merged under "green gate = merge without asking".

## Delivery

- [ ] 0. Now, independent of the rest: add
  `^platform-gitops/bootstrap/templates/mctl-platform/mctl-api\.yaml$` to
  protected_re (auto-merge.yml:82) and a test that every version_holds[].file
  matches it. DoD: tests/test_auto_merge_protected_paths.py fails when the entry
  is removed; a bot-approved claude/* PR touching the file stays open.
- [ ] 1. Prerequisite (mctl-api#1022): release and contract-test the decide-page
  decision for intents release.mctl-api and policy.mctl-gitops.release-hold.
  DoD: T1 passes against the released API in a disposable environment.
- [ ] 2. Gate core (scripts/release-gate.py, release-gates.yaml): owners
  (principal IDs), decide-page client ID, baseline pin, expires_at, packet and
  allow schema, policy-digest, record and policy provenance, first-parent
  packet_ref, run() returning 7 on UNKNOWN, any-new-tag rule. allow stays [].
  DoD: T2-T5 pass; existing tests/test_release_gate*.py pass unchanged.
- [ ] 3. External reads behind one adapter: ledger decision, GitHub PR/files/
  git, GHCR digest/config/label. DoD: T3 and T6 failure cases are 7.
- [ ] 4. Bump jobs: `sys.exit(7 if rc == 7 else 6)` at release-deploy.yaml:358-360
  and gitops-bump.yaml:243-245 (and release-preflight.py check_gate); check
  --route, held output, START_SHA, pre-push diff before every push, await-bump
  only when held is 'false'. DoD: T7 through the real embedded scripts against
  bare remotes; exit 7 reaches the job summary as "could not observe".
- [ ] 5. Effect classes and the tag+pin release effect in both producers,
  release-bump-apply.sh, release-bump-diff-guard.py and auto-merge handoff.
  DoD: T8 positive path and T9 negatives; other services stay tag-only.
- [ ] 6. Repo-wide rendered image scan, credential-free Helm renderer, env
  graph and zitadel-iac key contract; no-overwrite without commit-named
  exemption for held repositories and post-push digest re-read in build-image.
  DoD: T10-T11; the real baseline passes.
- [ ] 7. release-hold-pr.yml (checker) and release-hold-merge.yml (broker),
  both refusing non-main refs. Auto-merge change: the protected/held branch
  that today says "need a human merge; leaving it open" dispatches the broker
  after cutover and never merges itself. DoD: T12-T14.
- [ ] 8. Environment and key migration payloads: release-hold-checker and
  release-hold-merge (main-only branch policy, can_admins_bypass false,
  environment secrets); plan to move APP_PRIVATE_KEY and AGENTS_APP_PRIVATE_KEY
  (app-key-ratchet.yml, build-image.yaml, release-deploy.yaml) into main-only
  environments. DoD: in a disposable repo a workflow pushed on a feature branch
  cannot read either environment's secret; the migration plan names every
  consumer.
- [ ] 9. Ruleset payloads: restrict-updates ruleset (broker App plus existing
  DeployKey only) and 18465404 plus release-hold bound to the checker App.
  Inventory and pin classic protection allow_force_pushes false. DoD: T13 in a
  disposable repo; applied by the owner only after DevLoop/deploy continuity.
- [ ] 10. Admission: cluster-wide binding, baseline pin, [Warn, Audit]; Deny in a
  separate PR after a clean sync. DoD: T15 in kind/envtest.
- [ ] 11. Out-of-repo detector (D7), post-sync digest verifier, heartbeat.
  DoD: T16; a run that cannot read mctl-gitops alerts "could not observe".
- [ ] 12. GO preconditions recorded in the readiness packet: link to the owner's
  dated GitHub residual-risk record naming deploy keys 165489378 and 166128843,
  cluster-admin, P9 and repository-level App keys; detector live with heartbeat.
  DoD: link resolves to an owner-authored record; until then the packet reads
  NO-GO.
- [ ] 13. Mutation proof and independent implementation review. DoD: T17.

## Tests

Synthetic identities, injected provider answers, disposable remotes, repos and
clusters. Every negative effect test asserts the bare main SHA is unchanged, no
PR merged and no unauthorized release-bump branch published. UNKNOWN outranks a
concurrent violation.

- [ ] T1 (A) Decision: bearer request and MCP tool call with a real owner
  token refused; fresh login without a second factor in amr, a token from
  another client ID, auth_time before the challenge start, expired challenge,
  missing or unparseable amr/auth_time refused. One credential acting as broker
  dispatcher, environment approver and PR merger (owner gh token) authorizes
  nothing without a ledger decision. Positive: a valid decide-page decision
  stores every field. Exactly one consume succeeds in a race.
- [ ] T2 (R1) Packet: arbitrary release_head, other release PR, tree mismatch,
  tag/source mismatch, wrong label or digest, chart_revision != source_commit,
  noncanonical bytes, packet_ref only reachable through a second parent refuse.
- [ ] T3 (R1) Allow provenance: deploy-key push adding a record; deploy-key
  edit of an existing record's digest; merge by a human or another App; extra
  file in the allow PR; allow_pr not matching L; decision for another packet;
  expires_at after the packet's or old `expires` field refuse. Shallow history
  and paginated file count mismatch are 7.
- [ ] T4 (B) Policy: owners, held_from or protected file changed by a direct
  push, by a non-broker merge or without a bound policy decision refuses every
  guarded merge; owners added in the PR that relies on them refuse.
  policy_digest is stable across key order, comments and an added record, and
  changes with each hold field and protected file; a YAML date value is 7.
- [ ] T5 (D) Tags: 4.154.1, 4.150.0, 4.156.0 and 5.0.0 without a record refuse;
  4.154.0 with a different registry digest alerts; deployed held version with a
  lapsed record still verifies.
- [ ] T6 Each unreadable input (ledger, GitHub, GHCR, label, git) is 7, never 6
  or pass.
- [ ] T7 (G) Bump: no record 6; injected UNKNOWN exits 7 through both jobs; held
  version on the direct route refused; --since aborts after a policy change.
- [ ] T8 Positive: packet-only PR, decide-page decision, allow-only PR (grant
  unspent), tag+pin PR, broker merge with one consume, exact deployment diff,
  through BOTH producers.
- [ ] T9 Negatives: pin-only, tag-only, wrong pin, extra env or marker, second
  source, mixed policy+effect, changed packet, conflict reverting a neighbor.
- [ ] T10 (C) A second manifest naming ghcr.io/mctlhq/mctl-api, an unparseable
  image reference and a render failure are UNKNOWN; forbidden keys found in env,
  valueFrom, envFrom prefixes, ExternalSecrets and producer output.
- [ ] T11 (D) build-image refuses an existing held tag, including a
  commit-named one; a post-push digest mismatch fails the run.
- [ ] T12 (E) Checker: head script canary never runs; head/base fetch mismatch
  is 7; a same-named Actions job does not satisfy the App-bound context; a
  dispatch from a non-main branch cannot reach the environment.
- [ ] T13 Broker and ruleset: non-broker actors (including owner login and
  mctl-agy-reviewer[bot] approvals) cannot merge with a stale green check;
  broker cannot push main or skip checks; App approvals do not count.
- [ ] T14 Broker transaction: expiry within 15 minutes, moved base or head,
  retagged registry, tightened policy, crash before/after consume, ambiguous
  merge response; consumed grants never replay.
- [ ] T15 Admission in any namespace denies a non-baseline mctl-api image,
  forbidden env and Secrets; missing params deny; baseline admitted.
- [ ] T16 (L, H, M) Detector: a push that also edits release-gate-watch.yml and
  release-gate.py silences the in-repo watcher (asserted limitation) while the
  pinned detector alerts; a fast-forward grafting a fabricated first-parent
  history alerts FIRST_PARENT_REWRITE; allow_force_pushes true alerts; a record
  valid at its merge commit's merged_at but expired now does not alert; missing
  heartbeat alerts.
- [ ] T17 Mutation: removing each binding, provenance step, class rule, exit-7
  path, expiry/deadline, first-parent check and coverage rule turns a named
  test red; restoring it turns it green.

## Finding map

| Finding | Requirements | Design | Tests |
|---|---|---|---|
| A human signal via #1022 | R0 | 2.1, 5 | T1, T13 |
| B policy provenance | R1, R3 | 3 | T4 |
| C image anywhere | R5 | 7.1, 7.3 | T10, T15 |
| D overwrite, lower tag, digest pin | R5 | 7.2 | T5, T11 |
| E main-only environments, App keys | R2 | 1, 4; task 8 | T12 |
| F #2543 accepted risk | R8 | 9; task 12 | record link |
| G exit 7 | R4 | 1; task 4 | T6, T7 |
| H expiry at merge commit time | R7 | 8 | T16 |
| L pinned detector, heartbeat | R7 | 8 | T16 |
| M first-parent soundness | R1, R7 | 2.2, 8 | T2, T16 |
| Donor: record provenance, policy_digest, RFC3339, P4b | R1 | 2.3, 3, 6 | T3, T4, T7 |
| Strict true, four contexts | baseline | 5 | T13 |
| protected_re vs broker | R3 | 5; tasks 0, 7 | T13 |

This map is a specification correction, not evidence that any control exists.
