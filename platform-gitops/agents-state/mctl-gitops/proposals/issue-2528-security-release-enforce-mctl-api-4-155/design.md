# Design: issue-2528-security-release-enforce-mctl-api-4-155

## Context note

Revision of 2026-11-13. Per the R0 reconciliation (packet #2602) this design extends the existing gate:
`scripts/release-gate.py` and `platform-gitops/release-gates.yaml` `version_holds[].allow`. There is no
`release-hold.py`, no `release-holds.yaml` and no `release-grants/` directory in this design. The text is
not implementation, not an allow record, not a release GO and not a residual-risk acceptance.

Decision: `READY_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL`. The hold stays in force while any inventory row is
BLOCKING-UNKNOWN. P5b/P6 (write deploy keys through the ruleset bypass) are ACCEPTED-RISK for 4.155.0 only,
never resolved, until #2543 lands.

## Review history

| Round | Finding | Resolution (section) |
|---|---|---|
| 2026-11-09 P2-1 | Second write key; P5 rated on template code only | P5a/P5b split, P11; §8 records P5b/P6 as ACCEPTED-RISK |
| 2026-11-09 P2-2 | PR guard ran PR-controlled code | §4.2: base copy, `python3 -I` from `RUNNER_TEMP`, App-bound `release-hold` |
| 2026-11-09 P2-3 | No re-verification at merge/effect | §3 per-push re-read; §4.3 merge on exact head, strict ruleset race |
| R2 P1 (i) | Record-level provenance undefined | §1.3 |
| R2 P1 (ii) | `policy_digest` undefined | §1.2 |
| R2 P1 (iii) | `diff` refuses any policy change; grant/effect separation | §2 |
| R2 P1 (iv) | `owners` missing; `approved_by` unchecked | §1.1, §1.3 |
| R2 P2 | PR route (P4b) auto-merged without effect-time checks | §3.3, §4.1, §4.3, inventory P4b |
| R2 P2 | Watcher claim false | §7 |
| R2 P2 | Contradictions (files, Alternatives, chart pin, P9, T16) | whole text; §6; inventory P9; §2 |
| R2 P3 | Live facts, line refs, expiry migration, exit 7 on file list, test names | "Current state", §1.4, §4.2, tasks |

## Current state (mctl-gitops `main` 618cfe91, read 2026-11-13; no credential value read)

- **Policy.** `release-gates.yaml:38-50`: hold `mctl-api-bootstrap`, `file` = the bootstrap file,
  `repository: ghcr.io/mctlhq/mctl-api`, `held_from: "4.155.0"`, `allow: []`. Record shape today:
  `version`, `grant`, `approved_by`, `expires` (a YAML date; `release-gate.py:219-229`).
- **Gate.** `release-gate.py` has `check`, `verify`, `diff`, `--selftest`, `--policy-rev`, `--image`
  (`:729-755`). `hold_problems` (`:256-290`) refuses a held version without a record and, on a new write
  only, an expired one (`:288`). `diff` refuses any parsed change of the policy (`:480-483`) and any held-file
  change other than the tag line (`:555-557`). `run()` returns 6 even when a problem is UNKNOWN (`:350-358`);
  only `diff` returns 7.
- **Bootstrap file.** Tag `4.154.0` at `mctl-api.yaml:50` inside `values: |` (`:20`); chart source
  `targetRevision: a5b9ef9cf0f880f28b841033a8b2a6d9563ce050` (`:16`, #2599), which renders like production
  including the `/devloop` ingress path (runbook "P7: the pin is not neutral"). The comment at `:14-15`
  ("Move this pin in the same reviewed PR that bumps the image tag") contradicts §6 and is corrected in task 6.
- **Routes.** `release-bump-routes.yaml:17-18` routes `ghcr.io/mctlhq/mctl-api` to the PR route.
  `release-deploy.yaml`: `bump` `:199` (route `:228`, gate `check` `:354`), `publish-direct` `:543`
  (environment `:547`, key `:562`, `verify` `:598`, push `:605`), `publish-pr` `:629` (App token `:639-648`,
  diff guard `:677`, `verify` `:701`, branch push `:702`), `await-bump` `:773` (50-minute wait `:789`).
  `gitops-bump.yaml`: `bump` `:96` (route `:125`, `check` `:239`), `publish-direct` `:446` (`:453`, `:467`,
  `verify` `:485`, push `:486`), `publish-pr` `:493` (`:500`, `verify` `:564`, push `:565`), `await-bump` `:636`.
- **Auto-merge.** `auto-merge.yml:33` admits `release-bump/*`; `:40-45` checks out the default branch for the
  guard; `protected_re` (`:82`) does not name `mctl-api.yaml`; `:110-125` runs the diff guard; `:158-186`
  merges once `CLEAN`, up to 45 minutes, with `--match-head-commit`. No digest, provenance or expiry check.
- **Watcher.** `release-gate-watch.yml` runs `diff` (`:60`) and `verify` (`:82`) from the checkout of the
  pushed commit; its header (`:13`) says a push can change the file.
- **Ruleset 18465404** (`gh api`, 2026-11-13): bypass `[{DeployKey, actor_id: null, always}]`;
  `strict_required_status_checks_policy: true`; required contexts `cloudflare-plan`, `reserved-hosts`,
  `validate` (integration 15368) and `agy-formal-review` (5732062); one approving review;
  `require_extra_approval_for_unattributed_changes: true`.
- **Write deploy keys:** `gitops-bump` (165489378) and `argo-workflows-bot-2026-10` (166128843). Environment
  `gitops-bump`: branch policy only, `can_admins_bypass: true`. #2543 is OPEN.
- **Build label.** `build-image.yaml:488-498` resolves a 40-hex source revision and `:635` stamps
  `org.opencontainers.image.revision`.
- **mctl-api#934:** Draft. Any head recorded so far (`2fc67f31`, `70fcec0b`, `5b76cbc3`, `6241d5c8`) is
  evidence for that head only.

### Write-path inventory

| # | Path | Can change prod image/flags | Control after this design | Status |
|---|---|---|---|---|
| P1 | `release-deploy.yaml` (auto-dispatched by mctl-api release-please) | yes | `check` before write; route `pr` for mctl-api; held version refused on `--route direct` | KNOWN-ENFORCED |
| P2 | `gitops-bump.yaml` (any `actions: write` holder) | yes | same as P1 | KNOWN-ENFORCED |
| P3 | Human PR to `main` | yes | `release-hold` (§4.2), classification (§2), merge path (§4.3) | KNOWN-ENFORCED after tasks 7, 14 |
| P4 | `claude/*` PR auto-merged on bot approval | yes | `protected_re` gains every hold file (§4.1) | KNOWN-ENFORCED after task 7 |
| P4b | `release-bump/*` PR opened by `mctl-gitops-pr` App (`release-deploy.yaml:629-702`, `gitops-bump.yaml:493-565`), merged by `auto-merge.yml:158-186` | yes | auto-merge refuses held files; held PR merges only via `release-hold-merge` (§3.3, §4.3) | KNOWN-ENFORCED after task 7; first live use not observed |
| P5a | Argo `wft-deploy-service` / `wft-rollback-service` / `tpl-git-commit` as written | no: paths under `platform-gitops/services/` (`:399`, `:131`, `:342-345`) | T14 | KNOWN-NOT-A-PATH |
| P5b | Key `argo-workflows-bot-2026-10` used outside template code | yes, any path via the bypass | provenance makes a pushed record absent; detectors (§7) | **ACCEPTED-RISK** (4.155.0 only; §8) |
| P6 | mctl-agents CWFT `commit-and-push` (deploy key) | yes, same credential class | same as P5b | **ACCEPTED-RISK** (§8) |
| P7 | Chart source revision | yes, with no GitOps write if unpinned | pinned at a5b9ef9c (#2599); `verify` rule refusing a non-40-hex revision (task 6) | BLOCKING-UNKNOWN until task 6 |
| P8 | Argo CD override, `kubectl` by cluster admins | yes | admission (tasks 10-11); `selfHeal` | BLOCKING-UNKNOWN (owner disposition) |
| P9 | Optional Secrets via `envFromOptionalSecrets` (zitadel-iac Job, `mctl-api.yaml:398`) | yes, via `envFrom` | #2591 removed one entry; raw-text scan of `guarded` + admission Secret rule | BLOCKING-UNKNOWN until both are live (matches runbook P9) |
| P10 | Vault value on an existing `secretKey` | values only | admission env/Secret value rules | KNOWN-NOT-A-PATH for new names |
| P11 | Another workflow naming `environment: gitops-bump` | yes | `tests/test_gitops_write_credential_holders.py`; `protected_re` on workflows | KNOWN-ENFORCED |
| P12 | `validate` (15368) spoofed by a PR-defined job | yes, as a merge gate | App-bound `release-hold` (D1, D2) | BLOCKING-UNKNOWN until task 14 |
| P13 | `portal-allowlist-vendor.yml:62`, `cloudflare-drift.yml:728` (environment `app-gitops-pr`) | no direct write | PR controls | KNOWN-NOT-A-PATH |

## Proposed solution

Five layers, none trusted alone: L1 `check` before write; L2 re-verification before every push; L3 trusted
PR-time check and trusted merge; L4 admission; L5 detection.

### 1. Policy and allow record (`release-gates.yaml`)

#### 1.1 Shape

```yaml
version_holds:
  - name: mctl-api-bootstrap
    issue: mctlhq/mctl-gitops#2528
    file: platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
    repository: ghcr.io/mctlhq/mctl-api
    held_from: "4.155.0"
    owners:                                   # entered by the owner in the implementation PR
      - {login: <login>, id: <numeric id>}
    runtime_keys:
      forbidden: [MCTL_BRIDGE_PROVIDERS, MCTL_BRIDGE_PROVIDER_TOKENS]
      absent_or_false: [MCTL_BRIDGE_ENABLED, MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE]
    guarded:                                  # raw-text runtime-key scan
      - platform-gitops/bootstrap/templates/mctl-platform/mctl-api-*.yaml
      - platform-gitops/infra-components/mctl-platform/mctl-api/**
      - platform-gitops/helm-charts/zitadel-iac/iac/**
    chart_pin: {repo_url: https://github.com/mctlhq/mctl-api.git}
    admission_params: platform-gitops/bootstrap/templates/system/mctl-api-release-hold-params.yaml
    allow:
      - version: "4.155.0"
        grant: mctlhq/mctl-gitops#NNNN
        approved_by: <login>
        expires_at: "2026-MM-DDTHH:MM:SSZ"
        digest: "sha256:<64 hex>"
        source_commit: "<40 hex>"             # tag commit (release PR merge commit), never the PR head
        source_tree: "<40 hex>"
        reviewed_release_head: "<40 hex>"     # head the reviews and evidence covered
        policy_digest: "sha256:<64 hex>"
```

`_holds()` validates the new keys; a missing `owners` or a non-integer id is a malformed policy (refusal).

#### 1.2 `policy_digest`

`policy_digest = "sha256:" + sha256(canonical(H))`, where `H` is the hold mapping as parsed by
`yaml.safe_load` with the `allow` key removed, and `canonical` is
`json.dumps(H, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. A value that is
not a JSON type (a YAML date, a set) is exit 7. Gates, other holds and comments are outside `H`, so a worker
`min_tag` raise or an added allow record does not change it; any change of `held_from`, `owners`,
`runtime_keys`, `guarded`, `chart_pin` or `file` does. A new subcommand `release-gate.py policy-digest --hold
NAME [--policy-rev REV]` prints it, so the owner copies it rather than recomputes it. It is checked on new
writes and merges only, like expiry: changing the hold rules invalidates records for the next write, never the
deployed state.

#### 1.3 Record-level provenance

For the record `R` of version `V` on policy revision `P` (`origin/main`, or the merge base at PR time):

1. Walk `git rev-list --first-parent P -- platform-gitops/release-gates.yaml`, newest first. For each commit
   `C` with first parent `C^1`, compare `canonical(R@C)` with `canonical(R@C^1)` (absent counts as a value).
   The first `C` where they differ is `L`, the commit that last changed `R`. A shallow clone, a git error or a
   walk that ends without `L` is exit 7. (`git log -L`/`-S` are not used: they depend on line layout.)
2. `GET /repos/mctlhq/mctl-gitops/commits/L/pulls` must return a PR with `merged_at` set and
   `merge_commit_sha == L`. None is exit 6 (provenance absent: a deploy-key push or a direct commit); an API
   error is 7.
3. That PR: `merged_by.type == "User"`; `{merged_by.login, merged_by.id}` is in the hold's `owners` at `L^1`
   (the base policy, never the policy the PR itself adds); `merged_by.login == R.approved_by`. Its file list
   (paginated, count equal to `changed_files`, else 7) is a subset of `{release-gates.yaml,
   admission_params}`, and `diff L^1 L` classifies as ALLOW_CHANGE (§2).
4. `R.expires_at <= merged_at + 7 days`.

Consequences: a deploy-key push that edits an existing record's `digest` becomes `L` and fails step 2; a
record copied unchanged across later commits keeps its original provenance; owners cannot be added by the
same PR that uses them.

#### 1.4 External checks and expiry

On every new write or merge (bump `check`, pre-push `diff`, `release-hold-merge`), behind one injectable
function `_external()` so tests feed answers and failures:

- tag ref `refs/tags/V` dereferenced equals `source_commit`; `tree(source_commit) == source_tree ==
  tree(reviewed_release_head)` (GitHub git API);
- the GHCR manifest digest of `ghcr.io/mctlhq/mctl-api:V` equals `digest`; its config label
  `org.opencontainers.image.revision` equals `source_commit` (missing label = 7);
- `now + margin < expires_at` (margin 15 minutes at push and merge, 0 in `check`).

**Expiry migration.** `expires` (date) is replaced by `expires_at`, a quoted string matching
`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`, parsed as UTC. An unquoted value (YAML datetime) or `expires` is a
malformed record. `allow` is empty on `main`, so no record migrates; the comment at
`release-gates.yaml:45-49` is updated. The rule at `release-gate.py:262-266` is kept: in `verify` a held
version already in the tree needs only an existing record, so a lapsed or policy-stale record never freezes
other releases or pod restarts.

#### 1.5 Release head versus source commit

Merging #934 creates merge commit M; release-please tags M and the build uses M's tree. A review of the
release PR head is a review of M only if the trees are equal. The record binds `source_commit` (M) and the
digest, and ties them to `reviewed_release_head` by tree equality. If the trees differ, M needs its own review
(then `reviewed_release_head = source_commit`) or a new release. T18 proves which commit release-please tags;
the check compares trees, so it stays correct either way.

### 2. Change classification in `diff`

`diff --base B --head H` (policy always from `B`) assigns each change set the set of classes it contains:

| Class | Condition |
|---|---|
| NONE | no hold file, policy, admission params or guard-code path changed |
| ALLOW_CHANGE | `release-gates.yaml` changed and `canonical(policy minus every allow list)` is equal on both sides; and/or `admission_params` changed with every held entry matching a record in `H` |
| POLICY_CHANGE | the policy minus allow lists differs, or a guard-code path changed: `scripts/release-gate.py`, `scripts/release-bump-*.py`, `scripts/release-bump-apply.sh`, `platform-gitops/release-bump-routes.yaml`, `platform-gitops/argo-workflows/scripts/release-gate-guard.sh`, `.github/workflows/{auto-merge.yml,release-deploy.yaml,gitops-bump.yaml,validate-manifests.yml,release-gate-watch.yml,release-hold-pr.yml,release-hold-merge.yml}`, `tests/test_release_gate*.py`, `tests/test_release_bump*.py`, the admission policy file |
| HELD_TAG | a hold file changed only in its `repository`+`tag` line (`_strip_tag` equal) |
| HELD_CONTENT | a hold file changed elsewhere (env, chart pin, comments) |

Refused (6): ALLOW_CHANGE with HELD_TAG or HELD_CONTENT (grant and effect never in one change set);
POLICY_CHANGE with any other class (`HOLD_POLICY_CHANGED`); HELD_TAG with HELD_CONTENT. This keeps
`release-gate.py:555-557`: a release changes the tag line only. ALLOW_CHANGE also refuses an edit or removal
of a record whose version is the tag in `H`'s held file. Then, per class:

- HELD_TAG: the new tag is a new write: full §1.3/§1.4 checks against `B`'s records.
- ALLOW_CHANGE in a PR (`--context pr`): schema and `policy_digest` checked; provenance cannot exist yet and is
  checked when the record is used. In a push (`--context push`): §1.3 on `H` (the pushed commit must be the
  owner-merged PR's merge commit); else 6.
- HELD_CONTENT and POLICY_CHANGE: runtime-key and chart-pin rules on `H`; a human merge is required
  (`protected_re`). In the watcher they stay alerts, as today (`:557`), because a push cannot be told apart
  from a reviewed merge without provenance.

`diff` prints `classes=<list>` and keeps exit 0/6/7; any unreadable side is 7. `run()` is changed so that any
UNKNOWN problem in `check`/`verify` is 7 (unknown outranks refused); every caller already treats non-zero as
refusal.

### 3. Point of write

#### 3.1 Bump jobs (`release-deploy.yaml:354`, `gitops-bump.yaml:239`)

`check` gains `--route` (from the job's route output) and runs §1.3/§1.4 for a held version. A held version on
`--route direct` is refused even with a valid record. On a pass it prints `held=true|false`, which the bump job
exports as an output.

#### 3.2 Before every push

In `publish-direct` (`release-deploy.yaml:597-605`, `gitops-bump.yaml:485-486`) and `publish-pr`
(`:701-702`, `:564-565`), the last command before each push becomes, after the existing `verify --policy-rev
origin/main`: `release-gate.py diff --base origin/main --head HEAD --context push --expiry-margin 15m
--since "$START_SHA"`. It re-reads the policy, provenance, GHCR, tag ref, label and clock on each attempt,
nothing cached. The scripts come from the `main` checkout the job started from (`ref: main`). `START_SHA` is
recorded before the bump; `--since` refuses when the `policy_digest` of any hold at `START_SHA` differs from
`origin/main`, so a rebase onto a `main` whose hold rules changed aborts the run instead of pushing under them;
a fresh dispatch starts under the new policy.

#### 3.3 PR route and `await-bump`

The held-tag PR is opened by `publish-pr` as today (diff guard `:677` is the shape check). `await-bump`
(`release-deploy.yaml:773`, `gitops-bump.yaml:636`) runs only when `needs.bump.outputs.held == 'false'`. For a
held PR a step writes "PR #N awaits release-hold-merge" to the run summary and ends green: opening the PR is
the whole job, the merge is the owner's separate decision. A missing or unparseable `held` output counts as
held (no wait, never a merge). There is no designed 50-minute timeout on the held path.

### 4. Merge path

#### 4.1 `auto-merge.yml`

`protected_re` (`:82`) gains `^platform-gitops/bootstrap/templates/mctl-platform/mctl-api\.yaml$`, the
admission params and policy files, `release-hold-(pr|merge)\.yml`, and `^\.github/workflows/`. A test asserts
that every `version_holds[].file` in `release-gates.yaml` matches `protected_re`, so a new hold cannot be
added without it. Effect: no `claude/*` or `release-bump/*` PR touching a hold file is ever auto-merged; the
diff guard (`:110-125`) and the `CLEAN` loop (`:158-186`) remain for non-held images.

#### 4.2 Trusted PR-time check: `.github/workflows/release-hold-pr.yml`

- `pull_request_target` (`opened, reopened, synchronize, ready_for_review`) and `workflow_dispatch`. Checks out
  `pull_request.base.sha` with `persist-credentials: false`, `permissions: {contents: read}`.
- Copies `scripts/release-gate.py` and `scripts/requirements-ci-hashed.txt` from that checkout into
  `$RUNNER_TEMP/gate`, installs with `--require-hashes`, and runs only
  `python3 -I "$RUNNER_TEMP/gate/release-gate.py" --root "$GITHUB_WORKSPACE" diff --base <base_sha> --head
  <head_sha> --context pr`. It fetches `refs/pull/<n>/head` and refuses (7) unless it equals `head_sha`. Head
  content is read only through `git show`/`git ls-tree`; it is never checked out, executed, imported, sourced or
  passed to a shell.
- Result as check run `release-hold` on `head_sha`, posted by the checker App (D2): success for NONE,
  ALLOW_CHANGE (schema-valid; the owner must merge it personally, §1.3), and a valid HELD_CONTENT or
  POLICY_CHANGE on its own (both reach `main` only through a human merge, §4.1); failure
  "merge through release-hold-merge" for HELD_TAG; failure for refusals; failure "could not observe" for exit 7,
  including an unreadable PR, file list or diff. Exit 7 never posts success.

#### 4.3 Merge at effect time: `.github/workflows/release-hold-merge.yml`

- `workflow_dispatch` on `main`, inputs `pr`, `head_sha`. Environment `release-hold-merge`: required reviewer
  = owner, `can_admins_bypass: false`. The approver (deployment-review API) and `github.actor` must be `User`s
  in `owners` (login and id).
- Steps, all with the gate copied from the `main` checkout and run as `python3 -I` from `RUNNER_TEMP`:
  1. Read the PR: open, non-draft, head repo equals base repo, head equals `head_sha`, and
     `merge-base(main, head_sha) == main tip`. Any read failure is 7.
  2. `diff --base <main tip> --head <head_sha> --context merge --expiry-margin 15m`: class must be exactly
     HELD_TAG, with §1.3/§1.4 re-read now.
  3. Post `release-hold` = success on `head_sha` (checker App).
  4. `PUT /pulls/<pr>/merge` with `sha=<head_sha>`, `merge_method=merge` (merger App, not a bypass actor).
  5. If step 4 fails, re-post `release-hold` = failure on `head_sha`.
- Race: the ruleset already has `strict_required_status_checks_policy: true`, so if `main` moved after step 2
  (including a deploy-key push) the merge is refused as out of date; `sha=` refuses a moved head. The window
  between steps 3 and 4 is seconds and merges only the verified state. A success left by a failed run cannot
  be reused after `main` moves (strict) and is overwritten in step 5; the residual (a human merging that head
  within the same `main` tip before step 5) is covered by T25/T27.
- Whether a merger-App merge satisfies `require_extra_approval_for_unattributed_changes` is not verified;
  T31 proves it in a disposable repository. If it does not, the owner merges personally inside the expiry
  margin, and the run's re-verification is the record.

### 5. Point of deployment effect (admission)

A ValidatingAdmissionPolicy `mctl-api-release-hold` in `admission-policies.yaml`, bound to namespace
`mctl-api`, param ConfigMap from the static file `admission_params`:

- Deployment/ReplicaSet/Pod CREATE/UPDATE: a `ghcr.io/mctlhq/mctl-api` image must be `4.154.0` or a listed
  `{tag, digest}`; `forbidden` env names denied; `absent_or_false` must be `"false"` when present,
  `valueFrom` denied.
- Secret CREATE/UPDATE in `mctl-api`: keys must not include `forbidden`, or `MCTL_BRIDGE_ENABLED` other than
  `"false"` (covers P9 `envFrom`).
- `[Warn, Audit]` first, `failurePolicy: Fail`, `paramNotFoundAction: Deny`; `[Deny]` in a separate PR after one
  clean sync with the live digest added.

The params file is changed only in an ALLOW_CHANGE PR (with its record), never with the tag; `verify` refuses
a held entry without a matching record. Admission sees the tag string only (the chart renders `repo:tag`), so
the digest is enforced at push and merge, and the post-sync verifier (§7) detects a later tag overwrite. No
expiry at admission. A deploy-key writer can change tag and params in one commit (§8).

### 6. Chart pin

The pin stays at `a5b9ef9cf0f880f28b841033a8b2a6d9563ce050`. It is not tied to the 4.154.0 tag (that would
drop `/devloop`) or to `source_commit`. `verify` refuses a chart `targetRevision` for `chart_pin.repo_url` that
is not 40 hex. Moving it is a HELD_CONTENT PR (no tag change) with the `helm template` diff in its body, merged
by a human. The comment at `mctl-api.yaml:14-15` and step 6 of the readiness packet, which say tag and pin move
together (the packet also says "auto-merge"), are corrected in tasks 6 and 1.

### 7. Detection

**In-repo watcher, corrected claim.** On `push`, GitHub runs the workflow definition and the script from the
pushed commit, so a push that also edits `release-gate-watch.yml` or `release-gate.py` disables its own
detection; the daily run reads the then-current `main`. The watcher stays (cheap, catches honest mistakes), and
it is not counted as a control against a deploy-key writer.

**Out-of-repo detector (task 15).** A scheduled workflow (every 15 minutes) in a repository that no mctl-gitops
write credential can change (D7). It runs `release-gate.py` pinned by a reviewed mctl-gitops commit SHA kept in
that repository, clones mctl-gitops read-only with full history, and for every first-parent `main` commit `C`
of the last 26 hours runs `diff --base C^1 --head C --context push` plus `verify` at the tip. Exit 6 alerts
"violated", any other non-zero alerts "could not observe". Limitation: detection lags by the schedule plus
GitHub scheduling delay, and a scheduled workflow can be delayed or dropped; both are part of the P5b/P6
accepted risk.

**Post-sync digest verifier.** A read-only CronJob (ServiceAccount `get`/`list` pods in `mctl-api`) compares
`imageID` with the allowlisted digest and alerts on mismatch or unreadable state. Its manifest comes from
`main`, so it is detection, not a control against P5b/P6.

### 8. Deploy-key bypass (#2543): accepted risk

Both write keys can push any path to `main` with no PR or check. One commit can set the tag, add or edit an
allow record and extend the params file; L1-L4 do not stop it. What remains: such a record has no owner-merged
PR (§1.3) and counts as absent for every later write and merge; L5 detects. The owner accepted this residual
for 4.155.0 only (direction recorded in this revision's brief, 2026-11-13). It is ACCEPTED-RISK, not resolved:
the dated, attributed record (scope 4.155.0, expiry, incident and rollback owner) must be linked in the runbook
before GO; the readiness packet's "No acceptance has been obtained" is updated with that link. #2543 stays open;
its remediation (a write broker running the gate, or a no-bypass path restriction proven in a disposable
repository) turns P5b/P6 into KNOWN-ENFORCED. Nothing here changes keys or the ruleset.

### Resulting flow for 4.155.0 (described, not executed)

0. Preconditions: tasks 2-11 and 14 merged or applied, admission in Deny, P8 disposed, D3 record linked.
1. The owner merges #934. release-deploy builds the image (labelled with M); the bump `check` refuses: no
   record. Nothing is written.
2. The owner compares `tree(M)` with the reviewed head, reviews the digest, then opens and personally merges a
   PR that only adds the allow record (with `policy_digest` from `policy-digest`) and the params entry.
3. A release dispatch (or re-run) passes `check`; `publish-pr` opens `release-bump/mctl-api-4.155.0` changing
   only the tag line; `await-bump` is skipped; `release-hold` reads "merge through release-hold-merge".
4. The owner dispatches `release-hold-merge` and approves; it re-verifies and merges with `sha=`.
5. Admission admits the tag; the post-sync verifier confirms the digest.

## Alternatives

- **Separate `release-hold.py`, `release-holds.yaml`, `release-grants/`.** Rejected in R0: two readers of one
  `values: |` block, duplicate call sites, and two policies that can disagree.
- **Gate only in `release-deploy.yaml`.** Misses P2, P3, P4, P4b. Rejected.
- **Admission only.** Leaves git claiming a version production refuses; kept as L4.
- **Tie the chart pin to `source_commit`.** Rejected: the pin must render like production (§6), and a two-line
  held change breaks HELD_TAG separation.
- **Refuse the bootstrap path in the bump workflows.** Blocks unrelated services in the same directory and
  offers no granted path. Rejected.

## Platform impact

- No new policy file or script; `release-gates.yaml` gains hold fields; `release-gate.py` gains
  classification, provenance, external checks and `policy-digest`; two new workflows; admission policy and
  params; a detector outside the repository.
- Other services and the worker gate are unchanged (T15). Non-tag edits to `mctl-api.yaml` need a human merge.
  Every tag `>= 4.155.0` needs a record.
- Risks: an admission bug blocking restarts (Warn first, separate Deny PR, revert); unreadable GHCR blocks held
  releases (fail-closed, open question); `strict` already affects every PR.

## Owner decisions

- **D1.** Add required context `release-hold` bound to the checker App to ruleset 18465404 (`strict` is
  already `true`).
- **D2.** Checker App (`checks: write`, `metadata: read`; key in `release-hold-checker` and
  `release-hold-merge`) and merger App (`contents: write`, `pull_requests: write`; key only in
  `release-hold-merge`). Neither is a bypass actor; neither is the `mctl-agents` App.
- **D3.** P5b/P6 accepted for 4.155.0 (§8); link the attributed record.
- **D4.** Read credential for GHCR digest and label in the bump jobs and merge workflow.
- **D5.** Reach Deny before relying on the point of effect.
- **D6.** P8 disposition (accept with admission plus `selfHeal`, or Argo CD RBAC evidence).
- **D7.** The repository for the out-of-repo detector; it must not be writable by any automated credential
  that also writes mctl-gitops.

## Open questions

- GHCR readability (D4); live running digest not observed (read before Deny).
- Raw-text scan of `guarded` files and comments.
- Whether "2026-11-03" is a hold date or an intended expiry; treated as never-expiring.
