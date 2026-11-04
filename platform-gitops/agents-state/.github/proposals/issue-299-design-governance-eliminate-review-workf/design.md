# Design: issue-299-design-governance-eliminate-review-workf

## Current state

### The shared reviewer (`.github/workflows/claude-review.yml`, clone at `69d0f1e`)

- **Caller contract.** Callers pin the reusable workflow by SHA, as shown in the
  usage example at lines 8-29. They grant `id-token: write`, and the reusable
  workflow's `review` job holds it too (line 297). OIDC is therefore already
  available to every reviewer run. Nothing uses it today.
- **The `gate` job (lines 150-258).**
  - It hard-checks that the `@claude review` commenter has write access and
    that the PR is not cross-repo.
  - It resolves `sha` and `base_sha` (`baseRefOid`, the base tip) and drops
    stale runs.
- **The `review` job's dedup step (`id: dedup`, lines 595-690).**
  - A verdict counts as "already reviewed" only when all of these hold:
    - it is a `claude[bot]` `APPROVED` or `CHANGES_REQUESTED` review;
    - its `commit_id` equals the head;
    - its body contains `Reviewed head=<HEAD> base=<BASE>`;
    - its GraphQL edit history shows no change
      (`lastEditedAt == null && updatedAt == submittedAt`).
  - The reasons are the .github#283 fix, documented at gap 5 (lines 585-594).
  - The step has three outcomes: `true`, `false` and `unknown`.
  - This is a cost dedup. GitHub's merge gate is still "one approving review"
    (prompt text at line 383: "this is the merge gate — `main` requires one
    approving review").
- **The verdict.** The model posts it itself, through the allowlisted
  `gh api .../reviews` call, with the evidence line appended (lines 364-401 and
  the allowlist at line 1166).
- **Self-edit detection.**
  - `id: selfedit` (lines 868-1021) compares the blob SHA of the entry workflow
    (`github.workflow_ref`) at the run's ref with the copy on the default
    branch.
  - "Explain the self-edit refusal" (lines 1027-1145) comments and then runs
    `exit 1`, failing closed.
  - This is the deadlock mechanism. A pin bump edits the entry workflow, so the
    `pull_request` run of the new version always fails. The only reviewer that
    can still run is the default-branch copy, triggered by `@claude review`,
    and that copy is the old version.
- **The execution output.** `$RUNNER_TEMP/claude-execution-output.json` is
  already parsed by `USAGE_CAPTURE_SH`, `DENIALS_LOG_SH` and the review-check
  steps (lines 427-544 and 1168-1191), so the run's own tool calls can be read
  locally.

### Callers in this repository

- `.github/workflows/pr-review.yml` calls `./.github/workflows/claude-review.yml`
  by local path.
  - Its header comment says a change to `claude-review.yml` cannot be reviewed.
  - However, `selfedit` compares only the entry file, `pr-review.yml`.
  - So a PR that edits only `claude-review.yml` may be reviewed by its own
    modified reviewer.
  - The in-repo comment and the step disagree. Which one matches
    `claude-code-action` behaviour was not observed. The design below does not
    depend on it, because receipts from a non-accepted reviewer blob are refused.
- `.github/workflows/agy-pr-review.yml` calls `agy-review.yml@main` with
  `blocking: false`.
  - Its header records the same gap: on `pull_request` the caller file is read
    from the PR head.
  - It says that a reviewer the PR cannot alter needs "a workflow run from the
    default branch (for example an org-level required workflow)".

### Tests

- `.github/tests/test_claude_review_dedup.py` reads the dedup step out of the
  workflow YAML and runs it against a fake `gh`. Its cases include:
  - `test_verdict_moved_onto_a_merge_head_is_not_evidence`;
  - `test_same_head_against_a_changed_base_is_not_evidence`;
  - `test_edited_verdict_is_not_evidence`.
- `.github/workflows/workflow-tests.yml` runs `.github/tests` and the spike
  reference models: Python `unittest` under `docs/spikes/*/tests`, and Go under
  `docs/spikes/mcp-gateway-g0`.

### Existing receipt infrastructure (reused, not duplicated)

Read from gitops `agents-state` proposals, all with `status: merged`:

- **mctl-agents#905** (PR #971, merge `577306dd`): ADR 025 and
  `orchestrator/review_receipts.py`. It defines:
  - `ReviewSubject` kinds `spike_report` and `proposal`;
  - `ReviewRequest`, which carries a `nonce`, `author_actors` and
    `authoring_execution_id`;
  - `ReviewReceipt`, whose outcome is `PASS | CHANGES_REQUESTED | NEEDS_HUMAN |
    UNOBSERVABLE` and which has `assurance` and `attempt_id`;
  - `evaluate_review_gate`, with the outcomes `unknown`, `missing`, `stale`,
    `not_independent`, `advisory_only` and `satisfied`.
  - The gate's signature has "no slot" for GitHub review state.
- **mctl-api#895** (Slice A): `internal/reviewreceipts`, a pure Go port with
  `EvaluateReviewGate` and parity vectors.
- **mctl-api#897** (Slice B, merge `33b292e`): `internal/reviewstore`.
  - Tables: `review_requests`, `review_receipts` and
    `review_nonce_consumptions`, all immutable through triggers.
  - Routes:
    - `POST /api/v1/review-requests` (evidence writer);
    - `POST /api/v1/review-receipts/manual` (human admin, always
      `advisory`);
    - `POST /api/v1/review-receipts`, which always answers 501
      `review_worker_ingest_disabled`;
    - `GET /api/v1/review-gate` (admin).
- **mctl-api#896** (Slice C, merge `4980d8a`): `internal/executionprovenance`.
  - `execution_attempt_v1` defines `AttemptID(engine, engineRef)` and
    `LineageRoot(root)`.
  - The `execution_provenance` table is immutable.
- `mctl_get_review_gate` and `mctl_submit_review_assertion` are the MCP faces of
  those routes. Both are described in this run's tool list.
- mctl-api action approvals (`aar_`, `internal/workitems/action_approvals.go`,
  `handlers_approval_grant.go`, `isHumanAdmin`) bind `artifact_hash` to a
  decision. Source: `docs/spikes/agent-governance-decision-assurance.md` in this
  repo.

### What consumes GitHub review state today

- mctl-agents `orchestrator/run_shepherd.py`:
  `GATING_BOTS = ("claude[bot]", "chatgpt-codex-connector[bot]")`. Source: the
  #905 design, "Review gating today".
- mctl-claude-remote `skills/pr-steward/SKILL.md`. It merges only when "the
  review is clean+approved and CI is green". It escalates with
  `review-missing-at-head`.

### Deployed state checked

- `mctl_whoami`: `agent:issue-investigator`, not admin, no teams.
- `mctl_get_review_gate(kind=pull-request, repository=mctlhq/mctl-api)` returned
  HTTP 403 `agent_scope_denied`. The deployed review-gate route, and whether it
  accepts any subject kind beyond `spike_report`/`proposal`, was not observed.
- `$MCTL_GITOPS_ROOT/services/` holds `admins`, `karabu`, `labs` and `namax66`.
  - There is no `mctl-api` directory, so mctl-api's deployed env was not
    observed. This includes `EVIDENCE_DB_URL` and the review-store kill switches.
  - `services/labs/mctl-pairdesk` and `services/labs/mctl-loyalty` exist; only
    their `values.yaml` and `catalog-info.yaml` are there.
- `$MCTL_GITOPS_ROOT/governance/`: `policy-checkpoint-coverage.yaml` (schema
  `mctl-policy-coverage/v1`, enforced by a gitops test) and two sibling files.
  This is the precedent for a governance policy file with CI validation.
- `$MCTL_GITOPS_ROOT/agents-state/{mctl-agents,mctl-api}/proposals/issue-{905,895,896,897}-*`:
  all `status: merged`. Their contents are summarised above.
- `gh pr view` on the six PRs (read-only). Each one:
  - is `OPEN`, authored by `app/dependabot` and targets `main`;
  - changes exactly one file, `.github/workflows/claude-review.yml +1/-1`;
  - bumps the pin to `69d0f1e1803b4c35d1c1e93f4e8b78f6816b6e4a`;
  - has `reviewDecision=APPROVED`.

  Head SHAs and old pins:

  | PR | Head | Old pin |
  | --- | --- | --- |
  | mctl-pairdesk#91 | `1f32fee7…` | `da248823…` |
  | mctl-docs#188 | `66f8f1b9…` | `7da00d10…` |
  | mctl-api#908 | `ed4938b2…` | `25478e95…` |
  | mctl-agent#200 | `b5214138…` | `50b66e3b…` |
  | mctl-loyalty#47 | `a76fd846…` | `50b66e3b…` |
  | mctl-gitops#2356 | `555b4b2a…` | `25478e95…` |

  - The three PRs whose checks were read (#91, #2356, #908) show
    `claude-review / gate: SUCCESS` and `claude-review / review: FAILURE`.
  - The `claude` review body carries no `Reviewed head=` line.
  - mctl-api#908 has the self-edit marker comment, then an `@claude review` by
    mashkovd, then the old-pin approval.
  - `mergeStateStatus` is `UNSTABLE` on #908 and #91, and `UNKNOWN` on #2356.
- `gh api repos/mctlhq/<repo>/rules/branches/main`:
  - mctl-api: `pull_request` requires 1 approving review,
    `dismiss_stale_reviews_on_push: true` and
    `require_extra_approval_for_unattributed_changes: true`. Required checks
    are `lint` and `test`.
  - mctl-gitops: 1 approval. Required checks are `cloudflare-plan` and
    `reserved-hosts` with `integration_id: 15368`.
  - mctl-pairdesk: 1 approval, plus the backend and web build checks.
  - mctl-docs: 1 approval, plus `build`.
  - mctl-agent: 1 approval, plus `lint` and `test`.
  - mctl-loyalty: `[]`.
  - `branches/main/protection` returned 403 "Resource not accessible by
    integration". Classic protection was therefore not observed.
- `gh search code "Reviewed head"` finds evidence-line consumers only in
  mctlhq/.github and in prose. It finds the pr-steward skill and the
  shepherd-merge-gate spec as review-state consumers.

## Proposed solution

### 1. Principle: one trust source, two inputs, no GitHub review state

The gate's decision is `EvaluateReviewGate(live, request, pool,
required_assurance=independent)`, computed in mctl-api over receipts in
`internal/reviewstore`. The only GitHub reads are facts addressed by content:
- the PR's current head, base ref and merge base;
- the changed-file list at those SHAs;
- blob SHAs at a commit.

The gate never reads reviews, review bodies or `reviewDecision`. Commit SHAs are
content addresses, so binding to `(merge_base_sha, head_sha)` fixes the exact
diff. `diff_digest` is recorded as a human-checkable cross-check, not as an
authority.

### 2. Contract extension: `pull_request` subject (ADR 025 amendment, `review_contract` v2)

New subject kind in both tiers. It is added to Tier A `review_receipts.py` and
to Tier B `internal/reviewreceipts/types.go`, with shared golden vectors:

```
kind: pull_request
repository: owner/name
pr_number: int
base_ref: refs/heads/<branch>
merge_base_sha: <full hex>        # binding
head_sha: <full hex>              # binding
base_sha: <full hex>              # provenance: base tip seen by the reviewer
diff_digest: sha256:<hex>         # provenance
digest_version: pr_diff_digest_v1
```

- `Identity()` is `(repository, pr_number)`.
- `Binding()` is `(repository, pr_number, base_ref, merge_base_sha, head_sha)`.
- Supersession and the stale/missing classification reuse the existing
  `identity_key`/`binding_key` columns unchanged.
- Rubric `pull_request_v1`, with criterion ids: `diff_read_in_full`,
  `no_blocking_findings`, `security_considered`, `tests_considered`.

`pr_diff_digest_v1` is computed over
`git diff-tree -r --no-renames --full-index -z <merge_base> <head>`:

```
"pr_diff_digest_v1\n"
+ for each entry sorted by path bytes:
    "<old_mode> <new_mode> <old_blob> <new_blob> <status>\t<len(path)>\n<path>\n"
+ "<count>\n"
```

The format is independent of the diff algorithm and of user config. It is
pinned by golden vectors.

### 3. Reviewer identity: GitHub OIDC, version = blob SHA

New mctl-api routes. Both are off unless `REVIEW_GITHUB_INGEST=on`.

- `POST /api/v1/review-requests/github`. The reviewer job calls it before the
  model runs. The server:
  1. verifies the OIDC token: issuer `token.actions.githubusercontent.com`,
     audience `https://api.mctl.ai`. The same audience is already used by the
     deploy-service OIDC path.
  2. requires that `repository` equals `subject.repository`, and that
     `job_workflow_ref` starts with
     `mctlhq/.github/.github/workflows/claude-review.yml@`.
  3. reads the blob SHA of `.github/workflows/claude-review.yml` at
     `job_workflow_sha` through the GitHub contents API. It requires that blob
     to be in `accepted_reviewers[]` of the gate policy (section 6) and within
     its `not_before`/`not_after` window. A blob is the version identity
     because it covers pinned callers and the local-path caller in
     mctlhq/.github alike.
  4. reads the PR live and requires that `head_sha` equals the PR head and
     that `merge_base_sha` equals the compare API's `merge_base_commit.sha`.
  5. derives `author_actors` from the PR author and the commit authors and
     committers in `merge_base..head`.
  6. stores the request with mode `worker` and the OIDC provenance (`run_id`,
     `run_attempt`, `job_workflow_sha`, reviewer blob, `workflow_ref`,
     `workflow_sha`, `event_name`, `actor`, `repository_id`). For the
     provenance it uses
     `attempt_id = AttemptID("github-actions", "<repository_id>/<run_id>/<run_attempt>")`
     from `execution_attempt_v1`.
  7. mints and returns `{request_id, nonce}`.
- `POST /api/v1/review-receipts/github`. The reviewer job calls it after the
  verdict. The server:
  - requires the same OIDC run triple as the request;
  - consumes the nonce in `review_nonce_consumptions`, a table that Slice B
    already created for the worker path;
  - seals the receipt through `SealReceipt` and stores it.
  - Assurance is `independent` when all of these hold:
    - the reviewer principal `gha:<repository_id>/<run_id>` is not in
      `author_actors`;
    - its `attempt_id` is not in `authoring_attempt_ids`;
    - for a DevLoop-authored PR, it does not share the authoring lineage. The
      authoring execution is taken from the PR's provenance where present.
  - Otherwise assurance is `advisory`.
  - Entry check: the PR's changed files are read at the bound SHAs, and a
    truncated listing means refusal. If they include the path in
    `workflow_ref`, and `workflow_ref` does not end in
    `@refs/heads/<default>`, the receipt is refused with
    `review_entry_untrusted`. This holds whatever `claude-code-action` does, so
    a PR that rewrites its caller's inputs (`conventions`, `skip-paths`)
    cannot produce an accepted receipt.

The existing worker route stays 501. It is the DevLoop run-token path, and its
#895 prerequisites are unchanged. The GitHub route is a separate principal type
with its own enable flag.

### 4. Reviewer workflow changes (`claude-review.yml`, this repository)

New input: `receipt-mode`, with values `off` (the default), `shadow` and
`enforce`. With `off`, no new step runs. With `shadow` or `enforce`:

- **"Open review request"** runs after `classify` and before `Claude review`.
  - It computes `merge_base_sha` (`git merge-base BASE_SHA HEAD_SHA` on the
    full-history checkout) and `pr_diff_digest_v1`.
  - It fetches an OIDC token (`ACTIONS_ID_TOKEN_REQUEST_*`).
  - It posts the request and exports `request_id` and nonce as step outputs.
    The nonce is masked.
  - Failure is a warning plus `receipt=unavailable`. The review still runs.
- **"Derive verdict from the run's own tool calls"** is a pure jq program,
  `VERDICT_FROM_EXECUTION_JQ`, held in `env` like `USAGE_RECORDS_JQ`.
  - It selects successful `Bash` tool uses whose command is
    `gh api repos/<repo>/pulls/<pr>/reviews --method POST` with
    `commit_id=<HEAD_SHA>` and an `event` of `APPROVE` or `REQUEST_CHANGES`.
    "Successful" means the matching `tool_result` is not an error.
  - It takes the last one.
  - It maps `APPROVE` to `PASS` with all criteria `met`, and `REQUEST_CHANGES`
    to `CHANGES_REQUESTED`.
  - Anything else maps to `UNOBSERVABLE` with criteria `unobserved`.
  - It never reads the review body back from GitHub.
- **"Submit review receipt"** runs with `always()` when `request_id` is set.
  - It posts the receipt with a fresh OIDC token.
  - On failure it emits `::warning::` (in `shadow`) or `::error::` (in
    `enforce`). In `enforce` the job fails, so a missing receipt is visible
    rather than silently green.
- **The self-edit step.** With `receipt-mode != off`, the comment posted when
  `reason=differs` also states that the gate will accept a receipt from the
  default-branch reviewer. The comment keeps the `@claude review` instruction.
  An optional `workflow_dispatch` trigger with input `pr` is added to the
  documented caller template, so that pr-steward can request the
  default-branch run without a human comment. That run is gated by the same
  write-permission check.
- **The dedup step.** It stays a cost-only skip. Its result never posts a
  receipt.

### 5. Gate surface: one required check, posted by the mctl GitHub App

mctl-api publishes the check run `mctl/review-evidence` on the PR head through
the mctl GitHub App. Repositories require it in their ruleset with that app's
`integration_id`. Rulesets already pin check sources this way: mctl-gitops
requires `reserved-hosts` with `integration_id: 15368`. Pinning the source
means the GitHub Actions token cannot spoof the check.

Re-evaluation happens on any of these events:
- a receipt is ingested;
- a recovery grant is decided, consumed or expires;
- a `pull_request` webhook arrives (`opened`, `synchronize`, `reopened`, or
  `edited` with a base change);
- a periodic sweep runs over open PRs in enforced repos. The sweep also covers
  missed webhooks.

The check conclusion is `success` only for `satisfied`. For a recovery grant it
is `satisfied_by_recovery`, and the summary names the `aar_` id and its expiry.
Every other answer is `failure`, with the gate answer and a reason code. Those
answers are `unknown`, `missing`, `stale`, `not_independent`, `advisory_only`,
`changes_requested`, `needs_human` and `unobservable`. A new head has no check
until the gate posts one, and GitHub treats a required check that is absent as
blocking, so the gate fails closed by construction.

### 6. Gate policy (versioned, in mctl-gitops)

The policy lives in `platform-gitops/governance/review-evidence-gate.yaml`,
with schema `mctl-review-gate/v1`. It is validated in mctl-gitops CI in the
same way as `policy-checkpoint-coverage.yaml`.

```yaml
schema: mctl-review-gate/v1
contract: review_contract/v2
accepted_reviewers:            # blob SHA of claude-review.yml
  - blob: <sha>                # version N
    source_commit: 69d0f1e1803b4c35d1c1e93f4e8b78f6816b6e4a
    not_before: 2026-..Z
  - blob: <sha>                # version N-1, sunset date required
    not_after: 2026-..Z
enforced_repositories:         # gate posts required-mode checks
  - repository: mctlhq/mctl-pairdesk
    mode: shadow | enforce
recovery:
  max_ttl_hours: 24
  eligible_repositories: [mctlhq/mctl-api, ...]
  max_active_grants: 3
```

CI refuses a policy in any of these cases:
- `accepted_reviewers` is empty;
- an N-1 entry lacks `not_after`;
- the change drops a blob that a caller still pins on its default branch.
  CI resolves this through the GitHub contents API and fails closed on a read
  error.

### 7. Self-update and bootstrapping analysis

| What changes | Who judges it | Why this does not deadlock | Residual risk |
| --- | --- | --- | --- |
| Caller pin bump N-1 to N | A receipt from the default-branch reviewer (N-1, accepted) via `@claude review` or `workflow_dispatch` | The gate accepts any accepted version. It never needs the version being installed. | Every first adoption, from a pre-receipt pin, is a one-time bootstrap (section 9). |
| `claude-review.yml` in mctlhq/.github | Only receipts from an already-accepted blob. The PR's own modified reviewer produces an unaccepted blob and is refused. | The new blob becomes accepted only through a separate mctl-gitops policy PR, which is reviewed by an accepted version. | Two PRs per reviewer release. This is intended. |
| Gate policy (mctl-gitops) | The deployed gate, using the current policy | The new policy applies after merge and sync. CI forbids removing every usable version. | A bad but CI-valid policy can be fixed by a policy PR reviewed under N-1. |
| Gate code (mctl-api) | The deployed mctl-api gate | The new code deploys after merge, and its receipt contract is versioned. The gate accepts `review_contract/v1` and `/v2` during transition. | A deployed gate bug that fails every PR also blocks its own fix. Recovery grant first. If mctl-api itself cannot evaluate, see the last-resort row. |
| mctl-api or the GitHub App unavailable | No one: the required check is absent, so the PR is blocked | Fail closed. | Last resort: an org owner manually removes `mctl/review-evidence` from the affected ruleset. This is a manual, time-boxed protection edit, recorded in the GitHub audit log and a tracking issue. A drift detector alarms on any ruleset that differs from its declared state for more than 4 hours. No bypass actor is configured. |

### 8. Recovery grant (owner-authorized, time-bound, single-use)

- `POST /api/v1/review-gate/recoveries` (direct human admin:
  `isHumanAdmin` + `checkHumanPrincipal`).
  - Body: `{subject (pull_request binding), reason, tracking_issue,
    ttl_hours <= policy.max_ttl_hours}`.
  - It creates an `aar_` action approval with
    `action_kind=review-gate:recovery` and
    `artifact_hash=sha256(canonical(Binding()))`.
- The approval is decided with the existing aar_ decision path. The decider
  must be a direct human admin who is not the requester and not the PR author.
  Otherwise the request is refused with `recovery_same_person`.
- The gate counts a grant only when all of these hold:
  - the grant is approved, unexpired and unconsumed;
  - its binding equals the live binding;
  - the repository is in `recovery.eligible_repositories`;
  - the number of active grants does not exceed `max_active_grants`;
  - a manual `PASS` receipt exists for the same binding, through
    `POST /review-receipts/manual` (already human-admin-only), from a reviewer
    who is not the PR author.
- The grant is consumed by the `pull_request.closed`/`merged` webhook, and also
  by the sweep. A head or base change makes it inapplicable, and it can never
  be re-pointed.
- Audit actions: `review_gate.recovery_{requested,approved,refused,evaluated,consumed,expired}`
  and `review_gate.decision_posted`, written through `h.logAudit`.
- The grant only ever affects the `mctl/review-evidence` conclusion. It cannot
  merge, enable auto-merge or change rulesets.

### 9. One-time bootstrap of the six PRs (`docs/governance/review-evidence-gate-bootstrap.md`)

The default ordering is to bootstrap each repository at its enforcement
cut-over. The procedure for each PR, run by humans:

1. **Freeze.** Record `head_sha`, `base_ref`, `base_sha` and `merge_base_sha`
   from `gh pr view` and `gh api .../compare`. Stop if the PR head differs from
   the table in "Deployed state checked", or from the newer Dependabot head
   recorded at the time.
2. **Exact-change check.**
   - `git diff-tree -r merge_base head` lists exactly
     `.github/workflows/claude-review.yml`.
   - The only changed line is the `uses:` pin, from the recorded old SHA to
     `69d0f1e1803b4c35d1c1e93f4e8b78f6816b6e4a`.
   - That SHA is reachable from mctlhq/.github `main`.
   - Its `claude-review.yml` blob is in `accepted_reviewers`.
   - The `pr_diff_digest_v1` from the reference model matches the value
     recorded in the request.
3. **Independent review.**
   - An admin opens a manual review request bound to the subject.
   - A human reviewer, who is not the PR author and not the grant approver,
     records a `PASS` with `mctl_submit_review_assertion`.
   - The existing `claude[bot]` approval is not evidence and is not cited.
4. **Owner grant.** The requester files the recovery grant (TTL 24h), and the
   owner approves it. The `mctl/review-evidence` check turns `success`
   (`satisfied_by_recovery`).
5. **Human merge** with
   `gh pr merge <n> --merge --match-head-commit <head_sha>`. There is no
   auto-merge and no ruleset change. The existing rulesets already allow the
   merge.
6. **Audit.** Confirm the six `review_gate.*` audit entries and the grant
   state `consumed`. Link them on .github#299.
7. **Post-merge verification.**
   - Main's caller pin equals `69d0f1e…`.
   - The next PR in that repository gets a `review_contract/v2` receipt from
     the accepted blob, and `mctl/review-evidence` is `satisfied` without
     recovery.
   - If no PR arrives within 7 days, a docs-only canary PR is opened.
8. **Order.**
   - mctl-gitops#2356 first, because the gate policy lives in that repository.
   - mctl-api#908 second, because the gate code lives there.
   - Then mctl-agent#200, mctl-docs#188, mctl-pairdesk#91 and mctl-loyalty#47.

If Dependabot rebases a PR in the meantime, the head changes and the procedure
restarts at step 1. The old grant is inapplicable by construction.

### 10. Reference model and regression tests in this repository

`docs/spikes/review-evidence-gate/` follows the pattern of the
`security-finding-lifecycle` and `cve-advisory-impact` reference models.
- `gate_model.py` is a pure Python model containing:
  - the subject binding;
  - `pr_diff_digest_v1`;
  - OIDC claim admission;
  - the blob allowlist;
  - the entry-trust rule;
  - receipt and nonce lifecycle;
  - reconsideration ordering;
  - recovery-grant evaluation.
  It delegates the final decision to a transcription of the ADR 025 gate order.
- `tests/` covers T1-T12 from tasks.md.
- The golden vectors (`vectors/pr_diff_digest_v1.json`) are the canonical file
  that mctl-agents and mctl-api vendor.

`.github/tests/test_claude_review_receipt.py` reads `VERDICT_FROM_EXECUTION_JQ`
and the new steps out of `claude-review.yml`, as `test_claude_review_dedup.py`
does.

### Threat model (summary)

| Threat | Control |
| --- | --- |
| Human or bot posts an `APPROVE`, or edits a bot review body to add an evidence line | Gate has no GitHub-review input |
| GitHub re-anchors an approval onto a new merge head (.github#283) | Binding includes `head_sha` and `merge_base_sha`; a new head has no receipt |
| PR retargets its base | `base_ref` is in the binding; the `edited` webhook re-evaluates |
| PR rewrites the reviewer (`claude-review.yml`) or the caller inputs | Blob allowlist; `review_entry_untrusted` |
| Fork or malicious `uses:` ref | `job_workflow_ref` repository check plus the blob allowlist |
| Receipt tampering or replay | Server-sealed receipts, immutable rows, nonce consumption, OIDC run-triple match |
| Reviewer quota failure posts nothing | `UNOBSERVABLE` or no receipt, so `failure`; never green |
| Reconsideration shopping | Every receipt retained and audited; reconsideration needs a write-access trigger; newest wins, which is the existing contract |
| Recovery abuse | Two-person rule, exact binding, 24h TTL, single use, eligible-repo list, active-grant cap, audit |
| Gate outage | Fail closed; last-resort manual ruleset edit with a drift alarm; no standing bypass |

## Alternatives

1. **Keep GitHub approvals and harden the evidence line** (the status quo plus
   #283). Dropped for three reasons:
   - The evidence is still a mutable review body, readable only through
     edit-history heuristics.
   - The approval is still the merge gate, and GitHub moves it.
   - The bootstrap deadlock remains for every reviewer version that is not yet
     on main.
2. **An org-level required workflow from mctlhq/.github that runs the reviewer
   or the gate.**
   - This removes the PR's control over the entry file, as `agy-pr-review.yml`
     notes.
   - It is kept as the fallback check surface if mctl-app cannot get
     `checks: write` (open question).
   - On its own it still needs a durable evidence store. Using workflow
     artifacts or GitHub reviews would be the "second competing trust source"
     the issue rules out.
   - Its availability depends on the GitHub plan, which was not observed.
3. **Floating `@main` callers, with no SHA pin.** This removes pin-bump PRs
   entirely. Dropped:
   - Every merge to mctlhq/.github would silently change the merge gate of all
     callers, with no per-repository review.
   - `agy-pr-review.yml` already documents that `@main` does not make the
     caller immutable.
4. **A standing bypass actor (bot or admin) for pin bumps.** Dropped, because
   the issue explicitly forbids a standing bypass. It would also apply to any
   PR, not only pin bumps.

## Platform impact

- **Migrations.**
  - mctl-api gains additive tables: `review_github_provenance`, which is
    immutable and keyed by `request_id`, and `review_gate_recoveries`.
  - The two new routes and the check publisher sit behind
    `REVIEW_GITHUB_INGEST` and `REVIEW_GATE_CHECKS`, both default off.
  - mctl-agents Tier A gains the `pull_request` subject kind and rubric under
    `review_contract/v2`, with v1 still parsed.
- **Backward compatibility.**
  - `receipt-mode: off` is the default, so existing callers are unchanged
    until they opt in.
  - The dedup, the evidence line and the self-edit behaviour stay.
  - Branch protection is unchanged until a human adds the required check per
    repository.
- **Resources.**
  - Each reviewer run adds two small HTTPS calls.
  - The gate adds one check-run write per evaluation, a few GitHub reads per
    evaluation (PR, compare, contents) and a periodic sweep over open PRs in
    enforced repositories.
  - The new rate group is `review-gate` at 30/min, inside the 300/min global
    budget that #897 accounts for.
- **Operational burden.**
  - Each reviewer release needs a policy PR adding the new blob and setting
    N-1's `not_after`.
  - Each first adoption in a repository is a one-time bootstrap.
  - Recovery grants need two humans.
  - The drift detector and the gate-outage runbook are new operational items.
- **Risks and mitigations.**
  - mctl-api becomes in-path for merges. Mitigations: fail-closed semantics, a
    shadow phase that measures agreement with the `claude[bot]` verdict, and
    per-repository enforcement.
  - Webhook loss. Mitigation: the periodic sweep.
  - GitHub API truncation. Changed-file listings over the limit are a refusal,
    not a pass.
  - The merge-base binding misses semantic conflicts with a newer base. This is
    the same as today's approval semantics; strict base-tip binding is an open
    question.
- **Rollout.**
  - P0: this repository's contract doc, reference model and runbook.
  - P1: Tier A and Tier B contract v2.
  - P2: the mctl-api GitHub ingest and gate, in shadow.
  - P3: `receipt-mode: shadow` in one pilot caller, for 2 weeks or 20 PRs, with
    divergence reported.
  - P4: per-repository `enforce`, done by a human ruleset edit that adds
    `mctl/review-evidence`. The approval requirement is kept in parallel at
    first, then removed after 10 clean PRs.
  - P5: bootstrap of the six PRs.
- **Rollback.** Remove the required check from the ruleset first (human). Then
  set `receipt-mode: off` and turn the mctl-api flags off. Receipts remain
  stored. Nothing else depends on them.
