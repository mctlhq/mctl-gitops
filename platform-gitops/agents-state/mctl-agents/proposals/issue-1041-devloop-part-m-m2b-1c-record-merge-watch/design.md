# Design: issue-1041-devloop-part-m-m2b-1c-record-merge-watch

## Current state

All paths are in the `mctlhq/mctl-agents` clone at `883b3a1` (the merge of PR #1039, M2b-1b).

- `orchestrator/temporal/activities/issue_state.py` (143 lines) holds `IssueStateError(ProposalListingError)`, the
  `IssueState` dataclass, `_headers(token)`, `get_issue_state` and `post_issue_comment`. `post_issue_comment` returns
  `True` on 201 and a quiet `False` on a missing token or any 4xx. It raises only on transport errors, 429 and 5xx. It
  does not check for duplicates, which is why #1021's "Durable-write primitives examined" table rejects it as the
  record. Both activities resolve the token with `await asyncio.to_thread(_resolve_token)` and use
  `httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)`.
- `orchestrator/temporal/activities/pr_state.py` (218 lines) holds `PRState` and `get_pr_state`. That activity returns
  `found=False` on a status-file 404, on no or an unusable `pr:` line, and on a PR outside `mctlhq/<service>` or one
  answering 404. It decodes with `base64.b64decode(...).decode("utf-8", "replace")` and matches only
  `_PR_FIELD_RE = ^pr:\s*['"]?(\S+?)['"]?\s*$`. That match misses an indented, quoted-key or blank `pr:` line, so
  `found=False` cannot prove absence, as #1021 section "What `get_pr_state` can and cannot prove" states.
- `orchestrator/temporal/activities/proposals.py`: `GITOPS_REPO = "mctlhq/mctl-gitops"` (line 48),
  `AGENTS_STATE_PREFIX = "platform-gitops/agents-state"` (line 49), `REQUEST_TIMEOUT_SECONDS = 20.0` (line 50),
  `_resolve_token()` (line 58) and `ProposalListingError`.
- The implementer's branch is deterministic: `branch = branch or f"feat/agents-{ref.slug}"`
  (`orchestrator/run_implementer.py:1942`). Only an adopted PR overrides it, and an adopted PR always has a recorded `pr:`
  link, which blocks the proof anyway.
- GitHub App comments appear as `mctl-agents[bot]` (`orchestrator/directives.py:31-55`).
- Pagination precedent: `orchestrator/temporal/activities/workflow_dispatch.py:305-331` follows `resp.links["next"]`,
  refuses a next link outside `GITHUB_API + "/"`, treats a non-list body as malformed, and raises when it exceeds
  `ALERT_SEARCH_MAX_PAGES`.
- Registration: `orchestrator/temporal/worker.py:69,76` import the issue-state and pr-state activities.
  `short_activities` (line 680) lists `get_pr_state` (line 698), `get_issue_state` (line 700) and `post_issue_comment`
  (line 727). The control plans built at lines 787 and 800 use `[*short_activities, ...]`.
- Test pins that registration could touch:
  - `tests/test_worker_roles.py` asserts membership (`in control.activity_names`) for the control queue. Its exact-set
    assertions (lines 198, 211, 340) cover only the execution and implementation plans, which this slice leaves alone.
  - `tests/temporal_harness.py` mirrors only the execution-queue activity names.
  - `tests/test_pre_m1_compat.py:150` `M1_ADDED` pins carried dataclasses only (`ResumeDelivery`, `OpenDelivery`,
    `MergeWatchResume`, `IssueRef`, `ExecutionRequest`). Activity input and result dataclasses are not in it and stay
    out of it.
  - `tests/test_dev_loop_workflow.py:332` `_fake_activities` returns the fake list (lines 820-848), which already holds
    `fake_post_issue_comment` (line 292) and `fake_get_pr_state` (line 570).
- Existing activity test styles: `tests/test_post_issue_comment.py` monkeypatches `issue_state._resolve_token` and
  `issue_state.httpx.AsyncClient` with a fake client. `tests/test_temporal_activities.py:50-58` routes `httpx.AsyncClient`
  through an `httpx.MockTransport`. `tests/test_issue_state.py` does not exist.
- M2b-1b already landed `MERGE_WATCH_RECONCILE_PATCH` (`dev_loop.py:489`) and
  `MergeWatchResume.terminal_reconcile` (line 1646). Nothing reads them yet for the record path.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.117.0` (line 27). The other worker
  deployments `mctl-agents-worker-exec` and `mctl-agents-worker-implement` exist under `services/admins/`. This slice
  changes no image, environment variable or CWFT.
- The #1021 proposal files in `agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`:
  I read design sections 3 and 4 and tasks 5, 5a, 9, T-7 and T-17. They are the specification here.
- I made no mctl MCP calls. Nothing in this slice depends on a live service's runtime state.

## Proposed solution

### 1. `record_merge_watch_reconcile` (issue_state.py)

New module-level constants: `RECONCILE_MARKER_PREFIX = "merge-watch-reconcile-required"`,
`RECORD_WRITER_LOGIN = "mctl-agents[bot]"`, `TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})`,
`MAX_COMMENT_PAGES = 50` (5,000 comments), `GITHUB_API = "https://api.github.com"`.

```python
@dataclass(frozen=True)
class ReconcileRecordInput:
    repo: str
    issue_number: int
    workflow_id: str
    deadline: str
    exit_name: str
    last_observed: str          # caller-formatted "<STATE> <url> head=<sha>" or ""
    open_request_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class ReconcileRecordResult:
    status: str                 # "recorded" | "already-recorded" | "issue-gone"
    url: str = ""
```

Pure helpers, which are unit-testable and keep the mutations local:

- `reconcile_marker(workflow_id, deadline) -> str` raises `IssueStateError` on an empty value, whitespace or `--`, so the
  HTML comment cannot be broken.
- `_is_trusted_author(comment: dict) -> bool` returns `(user.login == RECORD_WRITER_LOGIN and user.type == "Bot") or
  author_association in TRUSTED_ASSOCIATIONS`. Mutations (l) and (af) act here.
- `reconcile_comment_body(inp) -> str` renders the fixed template: the marker line, a heading, then workflow id, exit,
  last observed PR (`inp.last_observed or "none"`), open request ids (`", ".join(...) or "none"`), and the fixed
  instruction "Read the pull request by hand, then re-trigger or close this loop deliberately." No other fields.

Activity flow:

1. Build the marker, which validates the input. Resolve the token off-loop. With no token, raise `IssueStateError`.
2. `async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)`: list comments from
   `GET {GITHUB_API}/repos/{repo}/issues/{n}/comments` with `params={"per_page": 100}`, at most `MAX_COMMENT_PAGES`
   pages.
   - Each page goes through `_read_comment_page(response)`. It returns `"gone"` on 410, raises `IssueStateError` on any
     other non-200 (404 included, mutation (ad)) and on a non-list body, a non-dict item, a non-string or null `body`, or
     a missing or non-dict `user`. Otherwise it returns the list. Mutation (k) acts on this path.
   - A transport error raises `IssueStateError`. A next link outside `GITHUB_API + "/"` raises, and so does running past
     the page bound.
   - The first trusted comment whose `body` contains the marker returns `already-recorded` with its `html_url`. That
     `html_url` must be a non-empty string, or the activity raises. The listing goes on past untrusted marker comments.
3. If no trusted marker is found, POST `{"body": reconcile_comment_body(inp)}`. A 201 whose JSON `html_url` is a
   non-empty string returns `recorded`. Everything else raises `IssueStateError`, and the activity logs the status
   code, never the body.

Idempotency comes from step 2 on every attempt, including the retry after a timed-out successful post (R12). This
holds because the comment is written under the same `mctl-agents[bot]` identity the trust check accepts. The
absolute deadline in the marker makes the record unique per watch and stable across hops and retries.

### 2. `confirm_no_pr` (pr_state.py)

```python
@dataclass(frozen=True)
class NoPrProof:
    confirmed: bool
    reason: str     # "no-link-no-pull" | "status-file-missing" | "status-file-empty"
                    # | "status-line-missing" | "pr-line-present" | "pull-request-listed" | "branch-exists"
```

New regexes, deliberately separate from `_PR_FIELD_RE` and `_STATUS_FIELD_RE` so `get_pr_state` stays byte-identical:
`_ANY_PR_KEY_RE = re.compile(r"""^\s*["']?pr["']?\s*:""", re.MULTILINE)`,
`_STRICT_STATUS_RE = re.compile(r"^status:\s*\S", re.MULTILINE)` and `_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")`.
`MAX_PULL_PAGES = 10`.

Pure helper `_strict_status_content(payload) -> str`. It raises `ProposalListingError` unless `payload` is a dict,
`payload.get("encoding") == "base64"`, `content` is a str, `base64.b64decode(content.replace("\n", ""), validate=True)`
succeeds, and the bytes decode as strict UTF-8. Mutation (ag-1) acts here.

Activity flow, `confirm_no_pr(service: str, slug: str) -> NoPrProof`:

1. Validate `service` and `slug` with `_NAME_RE`, resolve the token, and raise `ProposalListingError` when either fails.
2. Read the status file with the same URL and `ref=main` as `get_pr_state`. A 404 returns
   `NoPrProof(False, "status-file-missing")` (mutation (o)). Any other non-200, a transport error or non-JSON raises.
   Then call `_strict_status_content`.
3. On the decoded text: blank returns `status-file-empty`. No `_STRICT_STATUS_RE` match returns `status-line-missing`
   (mutation (ag-1)). Any `_ANY_PR_KEY_RE` match returns `pr-line-present` (mutations (p) and (ag-2)).
4. List `GET {GITHUB_API}/repos/mctlhq/{service}/pulls` with
   `params={"head": f"mctlhq:feat/agents-{slug}", "state": "all", "per_page": 100}`, following next links inside the API,
   up to `MAX_PULL_PAGES`. A non-200, non-list body, transport error, outside link or overflow raises (mutation (q)). A
   non-empty page returns `pull-request-listed`, whether or not the item's head matches. That is how a malformed `head`
   filter, which GitHub silently ignores, fails closed.
5. Call `GET {GITHUB_API}/repos/mctlhq/{service}/branches/feat/agents-{slug}`. A 200 returns `branch-exists` (mutation
   (ah)), a 404 continues, and anything else or a transport error raises.
6. Return `NoPrProof(True, "no-link-no-pull")` and log `service`, `slug` and the reason.

The branch read comes after the listing on purpose: a successful listing has already shown that the token can read
`mctlhq/<service>`, so the branch 404 is less likely to be a hidden permission 404. A 404 on a repository the token
cannot see would already have failed the listing.

### 3. Registration

- `worker.py`: extend the two imports (lines 69 and 76) and add `record_merge_watch_reconcile` and `confirm_no_pr` to
  `short_activities` beside `post_issue_comment` and `get_pr_state`, each with a one-line comment: "M2b-1c, registered
  but unscheduled until M2b-1d".
- `tests/test_dev_loop_workflow.py` `_fake_activities` gets two additive fakes,
  `@activity.defn(name="record_merge_watch_reconcile")`, which returns `ReconcileRecordResult("recorded", "https://example.invalid/c/1")`, and
  `@activity.defn(name="confirm_no_pr")`, which returns `NoPrProof(False, "fake")`. Both are appended to the returned list. No
  existing line changes. No caller exists, so no test exercises them through the workflow.

### 4. Tests (new files, existing files untouched except the R25 registration)

- `tests/test_record_merge_watch_reconcile.py` (T-7): uses an `httpx.MockTransport` routed through a patched
  `issue_state.httpx.AsyncClient`, the same technique as `tests/test_temporal_activities.py:50-58`. A stateful handler
  records POSTs and serves a configurable comment pool with `Link` headers.
- `tests/test_confirm_no_pr.py` (T-17): the same technique on `pr_state.httpx.AsyncClient`, with the routes keyed by path.

Activities run with `temporalio.testing.ActivityEnvironment().run(...)`, as `tests/test_temporal_activities.py:1232`
does.

## Alternatives

1. **Extend `post_issue_comment` with a dedupe flag.** Rejected. #1041 and #1021 require it to stay unchanged. Its
   quiet-`False` 4xx contract is pinned by `tests/test_post_issue_comment.py` and relied on by the #701 caller.
2. **Build `confirm_no_pr` on `get_pr_state`.** Rejected. `found=False` merges five distinct cases, and the permissive
   `_PR_FIELD_RE` plus the `"replace"` decode cannot prove absence. Tightening `get_pr_state` would change merge-watch
   behaviour that recorded histories replay against.
3. **Search issues for the marker (`/search/issues?q=...`) instead of listing comments.** Rejected. The search index is
   eventually consistent, so a just-posted record can be missed on retry, which gives duplicates. It also does not
   return comment authorship per match.
4. **Return `confirmed=False` on every read failure instead of raising.** Rejected. The specification wants a failure to
   be retryable and visibly distinct from "something blocks the proof". A raised `ProposalListingError` uses the existing
   retry classification in the workflow.

## Platform impact

- **Migrations and compatibility.** None. There are no new workflow commands, patch markers or carried fields. Existing
  histories and every replay fixture under `tests/fixtures/histories/` are unaffected because nothing schedules the new
  activity types. `get_pr_state`, `post_issue_comment` and the gap harness are untouched, and the harness still shows the
  defect (it changes in M2b-1d).
- **Release safety (B4).** The new activity type names are `record_merge_watch_reconcile` and `confirm_no_pr`. Rolling
  back to a build without them is safe only while no history has scheduled them, and no history can before M2b-1d wires
  a caller. Once 1d ships, both must stay registered until no history that scheduled them remains open or replayable.
  This slice changes no image, flag or deployment, and it decides nothing for B4 (#1007).
- **Resources.** None at rest. When called later, each call costs at most 50 comment-page GETs plus 1 POST, or 1 + 10 + 1
  GETs, under the existing GitHub App token.
- **Risks and mitigations.**
  - A third party pastes the marker to suppress the record. Mitigation: the author trust check, mutation-proved by (l)
    and (af).
  - A failed read is taken as absence. Mitigation: every non-specified status raises, mutation-proved by (k), (o), (q)
    and (ag).
  - The writer posts under a different identity and does not recognise its own record. Effect: a visible duplicate,
    never a suppressed record, which is accepted per #1021.
  - Issue transfer (301) is not followed and raises. This is a stated limit inherited from #1021.
