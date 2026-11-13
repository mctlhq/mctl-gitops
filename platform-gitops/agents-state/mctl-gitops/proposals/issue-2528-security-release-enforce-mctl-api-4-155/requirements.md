# Enforce the mctl-api 4.155.0 owner release hold at the GitOps write and deployment point

## Context note

Revision of 2026-11-13. The R0 reconciliation (packet #2602) decided that this proposal extends the
existing gate (`scripts/release-gate.py`, `platform-gitops/release-gates.yaml` `version_holds[].allow`)
instead of adding a second script, policy file or grant directory. This revision rewrites the whole
proposal to describe only that design and resolves the second independent review (P1, three P2, P3).
It is not implementation, not an allow record, not a release GO and not a residual-risk acceptance.
Any change to this text changes the content digest and needs a fresh independent review and a fresh
digest-bound owner approval. The coordination packet is `docs/plans/mctl-api-4-155-release-readiness.md`;
the write-path runbook is `docs/runbooks/mctl-api-release-hold.md`.

## Context

Issue mctlhq/mctl-gitops#2528 asks for a design, not a release. Production mctl-api is the Argo CD
Application `admins-mctl-api` (`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`): image
tag `4.154.0` (line 50) inside a `values: |` block (line 20), chart pinned to mctl-api commit
`a5b9ef9cf0f880f28b841033a8b2a6d9563ce050` (line 16, #2599). The candidate 4.155.0 is the Draft
release-please PR mctlhq/mctl-api#934, under the 2026-11-03 owner hold.

Already on `main` (618cfe91): `version_holds` hold `mctl-api-bootstrap` with `held_from: "4.155.0"` and
`allow: []` (`release-gates.yaml:38-50`), the bootstrap reader (`release-gate.py:179-253`), the PR route
for `ghcr.io/mctlhq/mctl-api` (`release-bump-routes.yaml:17-18`), the revision label in
`build-image.yaml:488-498,635`, and the chart pin. What is missing: binding an allow record to a digest,
source and owner identity; record-level provenance; runtime-key rules; trusted PR-time and merge-time
checks; a merge path for held-tag PRs that re-verifies at effect time; admission; and a detector a push
to `main` cannot disable.

## User stories

- AS the mctl-api release owner I WANT every path that can change the production mctl-api image or its
  Bridge/queue flags to refuse a held version unless an allow record I merged binds the exact digest and
  source SO THAT a release-please dispatch, a bot-approved PR or a newer tag cannot bypass the hold.
- AS a security reviewer I WANT the allow record to name digest, source commit, source tree, reviewed
  head, policy digest, my identity and an expiry, and its provenance to be checked per record, SO THAT a
  CI result, a "GO" comment or a deploy-key edit can never stand in for approval.
- AS a platform operator I WANT other services and the mctl-agents worker gate to behave as today SO
  THAT the hold costs nothing outside its scope.
- AS an on-call engineer I WANT admission to refuse a held image or a Bridge credential in the `mctl-api`
  namespace even if git is wrong.
- AS the author of #2523 I WANT the dark-rollout rules (no `MCTL_BRIDGE_PROVIDERS`, no
  `MCTL_BRIDGE_PROVIDER_TOKENS`, `MCTL_BRIDGE_ENABLED` and `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`
  absent or `"false"`) checked by machine.

## Acceptance criteria (EARS)

Inventory
- THE SYSTEM SHALL keep the source-cited inventory of design.md "Write-path inventory" in the runbook,
  each row KNOWN-ENFORCED, KNOWN-NOT-A-PATH, ACCEPTED-RISK or BLOCKING-UNKNOWN. WHILE any row is
  BLOCKING-UNKNOWN the hold SHALL stay in force for every held version. An ACCEPTED-RISK row SHALL link a
  dated, attributed owner record with scope and expiry; it is never reported as resolved.

Policy (existing file, extended)
- THE SYSTEM SHALL keep the hold in `platform-gitops/release-gates.yaml` `version_holds` and its allow
  records in that hold's `allow` list. No other policy file, script or grant directory SHALL exist.
- WHILE a hold is in force THE SYSTEM SHALL treat every SemVer tag `>= held_from` as held.
- THE hold SHALL carry `owners` (GitHub login and numeric id), `runtime_keys`, `guarded` (extra files for
  the runtime-key scan) and `chart_pin` (source repoURL; revision must be 40-hex). The owner enters
  `owners`, not an agent.
- A hold SHALL NOT lapse with time. It is lifted only by a human-merged PR.

Allow record (grant)
- THE SYSTEM SHALL accept a held version for a new write or merge only WHEN an allow record names that
  exact version and passes every check below; each check is fail-closed (6 refused, 7 could not observe):
  1. Shape: `version`, `grant`, `approved_by`, `expires_at` (quoted RFC 3339 UTC `YYYY-MM-DDTHH:MM:SSZ`),
     `digest` (`sha256:` + 64 hex), `source_commit`, `source_tree`, `reviewed_release_head` (40 hex) and
     `policy_digest` (`sha256:` + 64 hex). The old date field `expires` is refused.
  2. `policy_digest` equals the canonical digest of the hold with `allow` removed (design.md §1.2).
  3. Record-level provenance: the first-parent commit on the policy revision that last changed THIS
     record is the merge commit of a merged PR (`merge_commit_sha` equal), merged by a `User` whose login
     and id are in `owners` and whose login equals `approved_by`; that PR changed only the allow list (and
     the admission param file). A record last changed by any other commit (a deploy-key push, an edit of
     an existing record's digest) SHALL be treated as absent.
  4. `expires_at` is in the future by the margin (15 minutes at push and merge) and at most 7 days after
     the provenance PR's `merged_at`.
  5. The mctl-api tag ref of `version` dereferences to `source_commit`;
     `tree(source_commit) == source_tree == tree(reviewed_release_head)`.
  6. The live GHCR manifest digest of `ghcr.io/mctlhq/mctl-api:<version>` equals `digest`, and its image
     config label `org.opencontainers.image.revision` equals `source_commit` (label missing = 7).
- THE SYSTEM SHALL NOT treat a CI result, check run, PR approval or comment as an allow record, and SHALL
  NOT accept evidence for a release PR head whose tree differs from the tag commit's tree.
- Expiry and `policy_digest` SHALL gate new writes and merges only. A held version already deployed stays
  valid in `verify` while its record exists (existing rule, `release-gate.py:262-266`); admission SHALL
  NOT enforce expiry.

Change classification and separation
- `release-gate.py diff` SHALL classify a change set as NONE, ALLOW_CHANGE, POLICY_CHANGE, HELD_TAG or
  HELD_CONTENT (design.md §2) instead of refusing every policy content change.
- THE SYSTEM SHALL refuse a change set that combines ALLOW_CHANGE with HELD_TAG or HELD_CONTENT, combines
  POLICY_CHANGE with any other class, or combines HELD_TAG with HELD_CONTENT. A held-tag change SHALL be the
  tag line only (agrees with `release-gate.py:555-557`).

Point of write
- `check` in both bump jobs SHALL run the allow-record checks before any file is written, and SHALL refuse a
  held version on the direct route (`--route direct`) even with a valid record.
- Before every push attempt, the last command SHALL be `release-gate.py diff --base origin/main --head HEAD`
  with all external reads repeated and nothing cached between attempts.
- `environment: gitops-bump` and `GITOPS_BUMP_DEPLOY_KEY` SHALL appear only in the two bump workflows
  (existing `tests/test_gitops_write_credential_holders.py`).

Merge path
- `auto-merge.yml` SHALL never merge a PR that changes a `version_holds[].file` or the gate files; every
  hold file SHALL match `protected_re`, enforced by a test.
- A held-tag `release-bump/*` PR SHALL merge only through `release-hold-merge.yml`, which re-runs the full
  check at merge on the exact head against the current `main` tip and merges with `sha=<head>`. The release
  run SHALL report such a PR as awaiting that merge, not wait for it.
- THE PR-time result SHALL be check `release-hold`, computed by `release-hold-pr.yml` on
  `pull_request_target` with `release-gate.py` and the policy copied from the base commit and run as
  `python3 -I` from `RUNNER_TEMP`; PR-head content is read only as data via `git show`, never executed. It
  SHALL be posted by a dedicated checker App whose integration id the ruleset requires.
- An unreadable PR, file list or diff SHALL be exit 7 and SHALL never yield `release-hold` success.

Point of deployment effect
- A ValidatingAdmissionPolicy bound to namespace `mctl-api` SHALL deny a `ghcr.io/mctlhq/mctl-api` image not
  in a static, guarded allowlist; the four runtime keys in container `env` outside the rules; and Secrets
  carrying them. It SHALL roll out as `[Warn, Audit]`, and the hold SHALL NOT be reported as enforced at the
  point of effect before a separate PR switches it to `[Deny]`.

Runtime keys and chart
- `verify` SHALL refuse the forbidden or non-`"false"` runtime keys in the parsed values block and, by raw
  text, in every `guarded` file. It SHALL refuse a chart `targetRevision` that is not 40 hex. The chart pin
  is not tied to the tag or `source_commit`; moving it is a separate reviewed HELD_CONTENT PR.

Fail-closed
- Any input that cannot be read or decided (policy, history, held file, GitHub API, GHCR) SHALL be exit 7,
  which outranks exit 6 and is never a pass.

Detection
- THE SYSTEM SHALL NOT claim that a push to `main` cannot disable the in-repo watcher: on `push`,
  `release-gate-watch.yml` runs from the pushed commit (its line 13). A detector in a repository that no
  mctl-gitops write credential can change, running a pinned `release-gate.py`, SHALL alert on violation or
  unknown; until it exists the limitation is recorded as part of the P5b/P6 accepted risk.

Tests
- Every negative test SHALL prove no write: the bare `main` SHA is unchanged and no PR merged. Positive
  controls: an ordinary bump of another service, and a granted held-tag PR through `release-hold-merge`.

## Out of scope

- Any change to mctl-api#934, any mctl-api release, tag, build or bump; any allow record.
- Deploy keys, ruleset, Vault, credentials; Argo apply, sync or rollback; reading Secret data.
- Bridge activation; the mctl-agents worker gate semantics; #1040, #1007, #1292 (coordination only).

## Open questions

- D1-D7 in design.md "Owner decisions".
- GHCR digest and label readability from the bump jobs and the merge workflow (`packages: read`): not
  observed. If unreadable, every held write is exit 7 (safe, blocks the release).
- Whether raw-text scanning of non-values guarded files should strip comments (today: a comment naming a
  forbidden key refuses).
