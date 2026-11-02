# Tasks: issue-299-design-governance-eliminate-review-workf

Scope of implementation in mctlhq/.github: tasks 1-8.

- Tasks 1-8 change nothing at runtime: `receipt-mode` defaults to `off`, and
  no ruleset is touched.
- Task 9 files the cross-repository work as issues in mctl-agents, mctl-api
  and mctl-gitops. It implements none of it.
- Tasks 10-12 are human-operated rollout steps. They are listed here so the
  plan is complete, and no agent executes them.

- [ ] 1. Write the contract document `docs/governance/review-evidence-gate.md`.
  It is the ADR 025 amendment text, covering:
  - the `pull_request` subject (`Identity`, `Binding`, provenance fields);
  - `pr_diff_digest_v1`;
  - rubric `pull_request_v1`;
  - OIDC admission rules (`job_workflow_ref` repository, blob allowlist, run
    triple, `review_entry_untrusted`);
  - verdict derivation from the run's own tool calls;
  - gate answers and the check conclusion mapping;
  - the recovery grant;
  - the gate policy schema `mctl-review-gate/v1`;
  - the self-update table and the threat model.
  Link it from `AGENTS.md` under a new "Governance" heading.
  — DoD: the document states every EARS criterion in requirements.md. It names
  `EvaluateReviewGate`/`evaluate_review_gate` as the only evaluator, and says
  explicitly that GitHub review state is not an input.

- [ ] 2. Add the reference model `docs/spikes/review-evidence-gate/gate_model.py`
  (depends on 1). It is pure Python, stdlib only, and contains:
  - `PullRequestSubject` with `binding()`;
  - `pr_diff_digest_v1(entries)`;
  - `admit_oidc(claims, policy, blob_of)`;
  - `entry_trusted(changed_files, workflow_ref, default_branch)`;
  - a request/receipt/nonce store;
  - `derive_verdict(execution_output, repo, pr, head)`;
  - `evaluate_gate(live, request, pool, recoveries, policy)`, which transcribes
    the ADR 025 order and adds the recovery branch;
  - `RecoveryGrant` with requested, approved, consumed and expired states.
  — DoD: the module has no I/O. Every function returns typed refusals and
  never raises for an expected denial. An unknown input yields `unknown`,
  never `satisfied`.

- [ ] 3. Add golden vectors `docs/spikes/review-evidence-gate/vectors/pr_diff_digest_v1.json`
  (depends on 2). Cover:
  - add, modify, delete and mode change;
  - non-ASCII paths and a path containing a tab;
  - an empty diff;
  - each of the six PRs' one-line shape, built as synthetic tree entries.
  — DoD: every vector lists the input entries, the exact canonical bytes
  (base64) and the digest. The tests assert them literally. The file's own
  SHA-256 is pinned in the test, for vendoring parity.

- [ ] 4. Add the reference-model tests `docs/spikes/review-evidence-gate/tests/`
  (depends on 2, 3), covering T1-T12 below. Add a step to
  `.github/workflows/workflow-tests.yml`. Add `docs/spikes/review-evidence-gate/**`
  to its `pull_request` and `push` path filters.
  — DoD: `python3 -m unittest discover -s docs/spikes/review-evidence-gate/tests -v`
  passes locally and in the workflow. Each test name states the rule it pins.

- [ ] 5. Add `VERDICT_FROM_EXECUTION_JQ` and the three `receipt-mode` steps to
  `.github/workflows/claude-review.yml` (depends on 1):
  - a new `workflow_call` input, `receipt-mode`, defaulting to `off`;
  - "Open review request", placed after `classify`;
  - "Derive verdict from the run's own tool calls";
  - "Submit review receipt", with `always()`.
  Each step is guarded by `inputs.receipt-mode != 'off'`. The API base URL is a
  new input, `review-api-url`, defaulting to `https://api.mctl.ai`. Every
  caller-supplied value goes through `env:`, never through `${{ }}` splicing
  inside `run:`. This follows the file's existing rule.
  — DoD:
  - With `receipt-mode: off`, the job graph and every existing step's `if:` are
    unchanged.
  - `test_claude_review_dedup.py`, `test_claude_review_usage.py` and
    `test_claude_review_denials.py` still pass.
  - The nonce is masked with `::add-mask::`.
  - In `shadow`, a failure of either endpoint is a warning. In `enforce`, it
    fails the job.

- [ ] 6. Add `.github/tests/test_claude_review_receipt.py` (depends on 5). It
  reads the jq program and the steps out of the workflow YAML, following the
  `test_claude_review_dedup.py` pattern. It runs them against a fake `curl`
  and fake execution outputs. It also asserts that the jq program and
  `gate_model.derive_verdict` agree on a shared fixture set.
  — DoD: T3, T9 and T10 pass against the shipped workflow text. A mutation
  that drops the `commit_id == HEAD` filter fails at least one test.

- [ ] 7. Update the self-edit refusal text and the caller documentation in
  `claude-review.yml` (lines 8-34 and the `reason=differs` body), and the
  header of `pr-review.yml` (depends on 5). The text must cover three things:
  - With `receipt-mode != off`, a receipt from the default-branch reviewer
    satisfies `mctl/review-evidence`.
  - The optional `workflow_dispatch` caller trigger (input `pr`, gated by the
    same write-permission check).
  - In `pr-review.yml`, the contradiction with `selfedit` is corrected: the
    entry file is `pr-review.yml`, and the gate refuses receipts from a
    non-accepted `claude-review.yml` blob.
  — DoD: the self-edit step still runs `exit 1` and still posts one comment per
  head, and its marker format is unchanged.

- [ ] 8. Write the runbook `docs/governance/review-evidence-gate-bootstrap.md`
  (depends on 1). It contains:
  - the per-PR procedure from design.md section 9, with copy-paste commands
    for each step (freeze, exact-change check, manual review request and
    assertion, grant request and approval, `--match-head-commit` merge, audit
    query, post-merge verification and canary);
  - a table of the six PRs, with their recorded head and old pin, and the
    order mctl-gitops#2356, mctl-api#908, mctl-agent#200, mctl-docs#188,
    mctl-pairdesk#91, mctl-loyalty#47;
  - the gate-outage last-resort procedure, with its time box and drift check.
  — DoD:
  - The runbook contains no automated merge and no ruleset command.
  - Every step names who performs it.
  - Every SHA check compares full SHAs.
  - It says explicitly that the existing `claude[bot]` approvals are not
    evidence.

- [ ] 9. File the cross-repository follow-up issues (depends on 1, 3). Each
  links back to .github#299, and each is labelled for DevLoop proposal, not
  implementation:
  - **mctl-agents:** Tier A `pull_request` subject and `pull_request_v1`
    rubric, `review_contract/v2`, vendored `pr_diff_digest_v1` vectors.
    Follow-up: move `run_shepherd.GATING_BOTS` gating to the review-gate read.
  - **mctl-api:**
    - Slice D: `pull_request` subject in `internal/reviewreceipts` with
      vector parity.
    - Slice E: `POST /review-requests/github` and
      `POST /review-receipts/github` (OIDC admission, blob allowlist,
      `review_github_provenance`, nonce consumption, entry check), behind
      `REVIEW_GITHUB_INGEST`.
    - Slice F: the `mctl/review-evidence` check publisher, webhook handling,
      sweep, and recovery grants on `aar_` with audit, behind
      `REVIEW_GATE_CHECKS`.
  - **mctl-gitops:** `governance/review-evidence-gate.yaml` with schema
    validation and the "never drop a pinned blob" test, plus the ruleset drift
    detector.
  - **mctl-claude-remote:** pr-steward reads `mctl/review-evidence` instead of
    the evidence line or approval.
  — DoD: the issues exist, each with acceptance criteria copied from the
  matching EARS lines. Their links are posted on .github#299.

- [ ] 10. (Human, after 9 lands.) Shadow pilot: set `receipt-mode: shadow` in
  one caller, chosen by the owner, with mctl-api flags on in shadow for that
  repository. The run lasts 2 weeks or 20 PRs.
  — DoD: a divergence report covering gate answer vs `claude[bot]` verdict,
  count of `unknown`, and receipt failures is posted on .github#299. The
  report shows zero `satisfied` where the bot requested changes.

- [ ] 11. (Human, per repository.) Enforcement cut-over: an org admin adds
  `mctl/review-evidence`, with the mctl App `integration_id`, to that
  repository's ruleset. The repository is set to `enforce` in the gate policy
  and in its caller.
  — DoD: the ruleset change is recorded on .github#299, with before/after JSON
  from `gh api repos/<r>/rules/branches/main`. One PR has merged with
  `satisfied`.

- [ ] 12. (Human.) Bootstrap the six PRs with the task 8 runbook, in the stated
  order, each after its repository's cut-over in task 11.
  — DoD: for each PR, the audit entries and grant id are linked, the merge
  commit is linked, and post-merge verification is recorded. All six grants
  are `consumed`, with none `expired` unused and unexplained.

## Tests

The reference-model tests (task 4) and the workflow tests (task 6) are
data-driven. They must not call the network.

- [ ] T1. Self-update of the reviewer. A PR in mctlhq/.github changes
  `claude-review.yml`.
  - A receipt from the PR's own blob, which is not accepted, gives
    `review_reviewer_not_accepted`.
  - A receipt from the main blob, which is accepted, is admitted and the gate
    is `satisfied`.
  - Accepting the new blob takes a separate policy change, and the new blob
    applies only after that change.
- [ ] T2. The six caller pin bumps. Each repository's fixture (old pin to
  `69d0f1e…`, one-line diff, `workflow_ref` on PR head vs default branch)
  gives these results:
  - A receipt from the PR-head entry gives `review_entry_untrusted`.
  - A receipt from the default-branch entry with the accepted N-1 blob gives
    `satisfied`.
  - With no receipt, the answer is `missing` and the check is not success.
  - An N-1 blob whose `not_after` has passed gives
    `review_reviewer_not_accepted`.
- [ ] T3. Malicious approvals. Each of these leaves the gate result unchanged:
  - a human `APPROVE`;
  - a `claude[bot]` review edited to add `Reviewed head= base=`;
  - a forged evidence line in a comment.
  The model has no review-state input, and the test asserts that its signature
  has none.
- [ ] T4. Stale and re-anchored approvals. Each of these gives `stale`:
  - an update-branch merge creates a new head while the old receipt stays;
  - a GitHub `commit_id` is moved;
  - the base is retargeted (`base_ref` changes).
  The receipt is never matched.
- [ ] T5. Changed base. When the base tip advances and the merge base is
  unchanged, the gate stays `satisfied`. This is the documented binding. When
  the merge base changes, the answer is `stale`.
- [ ] T6. Receipt tampering. Each of these is refused, and the gate stays
  non-success:
  - a receipt with a mutated `outcome`, `criteria` or `subject` (hash
    mismatch);
  - a reused nonce;
  - a different `run_id` or `run_attempt` from the request;
  - a `job_workflow_ref` outside mctlhq/.github, or from a fork;
  - OIDC `repository` not equal to the subject repository.
- [ ] T7. Same-revision reconsideration. On an unchanged binding,
  `CHANGES_REQUESTED` followed by a new request with a new nonce and `PASS`
  gives `satisfied`. Both receipts are retained.
  - `PASS` followed by `CHANGES_REQUESTED` gives `changes_requested`.
  - A reconsideration run with no receipt keeps the previous answer.
  - A reconsideration that reuses the earlier nonce is refused.
- [ ] T8. Missing or partial evidence. Each of these gives `unknown`, never
  `satisfied`:
  - a failed live read;
  - a truncated changed-file list;
  - an unreadable blob;
  - an unavailable store or policy;
  - a missing `merge_base`.
- [ ] T9. Verdict derivation. An execution output with these contents gives
  `UNOBSERVABLE`:
  - an `APPROVE` call on a different `commit_id`;
  - an `APPROVE` call whose `tool_result` is an error;
  - only inline comments;
  - prose saying "approve" with no call;
  - a malformed file.
  When the output has `REQUEST_CHANGES` and then `APPROVE`, the last
  successful call wins.
- [ ] T10. `receipt-mode: off`. The parsed job steps and `if:` expressions are
  identical to the pre-change workflow apart from the three guarded steps, and
  no new step runs.
- [ ] T11. Recovery grant misuse. Each of these is refused or ignored:
  - requester equals approver;
  - approver is the PR author;
  - TTL over 24h;
  - the repository is not eligible;
  - `max_active_grants` would be exceeded;
  - the head moved after approval;
  - no manual `PASS` receipt;
  - the manual `PASS` came from the PR author;
  - the grant is reused after `consumed`;
  - the grant is used after expiry.
  A valid grant gives `satisfied_by_recovery` and emits the audit events.
- [ ] T12. Policy validation model. These are rejected:
  - an empty `accepted_reviewers`;
  - an N-1 entry without `not_after`;
  - a change that drops a blob still pinned by a caller;
  - an unreadable caller pin, which fails closed.

## Rollback

- Tasks 1-4 and 8 are documentation and a reference model. To roll back,
  revert the PR. Nothing at runtime reads them.
- Tasks 5-7 ship behind `receipt-mode`, which defaults to `off`. To roll back,
  set callers back to `off`, or revert the PR in mctlhq/.github. Callers pinned
  to an earlier SHA are unaffected either way.
- After human rollout (tasks 10-12), roll back in this order. A required check
  that never reports blocks every merge, so the order matters.
  1. An org admin removes `mctl/review-evidence` from the affected ruleset and
     records the before/after JSON on .github#299.
  2. Set the repository back to `shadow` or `off` in the gate policy and in its
     caller.
  3. Turn off `REVIEW_GATE_CHECKS` and then `REVIEW_GITHUB_INGEST` in mctl-api.
- Receipts, provenance rows and recovery records are immutable and are
  retained for audit. Rolling back never deletes them.
- PRs already merged under a recovery grant stay merged. Their audit trail is
  the record.
