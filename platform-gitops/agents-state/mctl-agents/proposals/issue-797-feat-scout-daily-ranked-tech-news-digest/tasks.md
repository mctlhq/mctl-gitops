# Tasks: issue-797-feat-scout-daily-ranked-tech-news-digest

- [ ] 0. Prerequisite outside this repo: open the mctl-gitops PR that adds
  `argo-workflows/cluster-templates/cwft-mctl-agents-scout.yaml` (CWFT
  `mctl-agents-scout`) and `cronworkflow-mctl-agents-scout.yaml`
  (`schedule: "40 6 * * *"`, `timezone: UTC`, `concurrencyPolicy: Forbid`,
  `suspend: true`). Pod env: the GitHub read token, plus `SCOUT_TELEGRAM_BOT_TOKEN`
  and `SCOUT_TELEGRAM_CHAT_ID` as `optional: true` secretKeyRefs. This belongs to
  slice 2 of the issue, but it has to land first or together, because
  `_check_cluster_workflow_template` fails CI otherwise. Record the link in the PR
  description. DoD: `mctl-agents-scout` exists on mctl-gitops main, still suspended.
- [ ] 1. Add the model-policy tasks `scout_relevance: cheap` and
  `scout_scoring: balanced` to `config/model-policy.yaml`, with a comment on the
  cheap-tier rationale. Add `SCOUT_RELEVANCE_SELECTION` and `SCOUT_SCORING_SELECTION`
  to `config/settings.py`. DoD: `resolve_model("scout_relevance")` and
  `resolve_model("scout_scoring")` resolve, and the existing model-policy tests pass.
- [ ] 2. Add `SCOUT_BUDGET_USD` (default `1.00`) and `build_scout_options(agent_dir,
  model, output_schema=None)` to `orchestrator/options.py`. The builder sets
  `tools=[]`, `allowed_tools=[]`, `mcp_servers={}` and `setting_sources=[]`, adds no
  hooks, sets `output_format` from the schema, and is wrapped in `_scrubbed`. Add
  `SCOUT_BUDGET_USD` to the cleared budget env vars in
  `orchestrator/validate_manifest.py`. DoD: the builder returns those fields exactly,
  and `uv run --locked mypy` is clean.
- [ ] 3. Add `agents/_scout/sources.yaml` with the seven sources from the issue,
  `ranking.top_n: 10`, `ranking.weights`, `window_hours: 26` and `dedupe_days: 90`.
  Verify each feed URL by hand. A source with no official feed is marked
  `enabled: false` with a `note`. Add `agents/_scout/PLATFORM.md`: a map of no more
  than about 60 lines covering api, gitops, agents/DevLoop, MCP gateway, tg, portal,
  web, docs and alice, with current priorities and each component's repository name.
  DoD: both files exist, and the loader (task 4) accepts `sources.yaml`.
- [ ] 4. Add `orchestrator/scout/feeds.py` (depends on 3). It provides
  `load_sources()`, `fetch_source()` returning
  `SourceResult(status ok|failed|malformed|disabled)`, RSS/Atom parsing with
  DOCTYPE/ENTITY rejection, a 2 MiB cap, a 15 s timeout and the custom UA, plus
  `in_window()`. DoD: unit tests T1-T4 pass.
- [ ] 5. Add `orchestrator/scout/dedupe.py`. It provides `normalise_url()` and
  `scout_issue_urls(days)`, which runs `gh api` GET search through `run_capturing`
  after `refresh_github_token()`. It returns a `set[str]`, or `None` on failure. DoD:
  T5-T6 pass.
- [ ] 6. Add `orchestrator/scout/backlog.py`. It reads open spike issues (filtered with
  `SPIKE_TITLE_RE`) and the `mctlhq/.github` `roadmap/spikes/` SpikeDefinitions
  (reusing the `orchestrator/spike_issue.py` constants), reduces them to
  `{ref, title, question, lifecycle}` and caps the result. It returns `None` on
  failure. DoD: T7 passes.
- [ ] 7. Add `orchestrator/scout/scoring.py` (depends on 1, 2). It holds the relevance
  and scoring JSON schemas, `relevance_pass()` and `scoring_pass()`, which batch items
  through `ClaudeSDKClient` with `build_scout_options`, and a run-level budget
  accumulator. It also does Python-side re-validation (unknown ids, ranges, repo
  allowlist from `config.settings.SERVICES` with a `.github` fallback, `related`
  format) and `rank()`. The SDK client is injectable for tests. DoD: T8-T11 pass.
- [ ] 8. Add `orchestrator/scout/render.py`. It provides `draft_body()`, `draft_url()`
  with the `MAX_BUTTON_URL_CHARS = 2000` fallback, `render_digest()` (HTML-escaped,
  4096-character cap, overflow drafts as replies) and `render_footer()`, with the
  all-failed and nothing-relevant variants. DoD: T12-T15 pass.
- [ ] 9. Add `orchestrator/scout/telegram.py`. `send_message()` is the only function,
  with the method constant `sendMessage` and token-redacted errors. DoD: T16-T17 pass.
- [ ] 10. Add `orchestrator/run_scout.py` (depends on 4-9). It holds the
  `RELEVANCE_PROMPT` and `SCORING_PROMPT` constants, which treat articles as
  untrusted data. It provides `async run_scout(dry_run=False, top_n=None,
  sources_path=None)` and `main()` with argparse `--dry-run/--top-n/--sources`, plus
  the exit codes from design.md. DoD: `python -m orchestrator.run_scout --dry-run`
  runs locally against live feeds and prints a digest with a footer (acceptance 1),
  and T18-T19 pass.
- [ ] 11. Add `agents/_manifests/scout/agent.yaml` as in design.md, and a `scout`
  entry in `docs/agent-inventory.yaml` (depends on 0, 2, 10). DoD:
  `uv run python -m orchestrator.validate_manifest` passes with mctl-gitops checked
  out (CI).
- [ ] 12. Add `docs/operations/scout.md`, modelled on the usage-collector operations
  doc. It covers what the scout does, the dry-run one-shot, the unsuspend checklist,
  the rule never to call `getUpdates` or `deleteWebhook` on @MCTL_AI_bot, how to add
  or disable a source, and how to tune weights. DoD: the doc exists and is linked from
  the inventory entry.

## Tests

All tests are offline. HTTP is faked with `httpx.MockTransport`, `gh` with a fake
`run_capturing`, and the SDK with a stub client.
- [ ] T1. A feed that times out, a feed that returns 503, and a feed that returns HTML
  or non-XML each produce `failed(...)` or `malformed`. The footer shows that status,
  never `ok(0)`, and the source is not counted in `fetched`. The test asserts the
  status. It fails if `fetch_source` returns `ok` with an empty list; verify this by
  temporarily changing the error path to `return ok([])`.
- [ ] T2. A body that declares `<!DOCTYPE` or `<!ENTITY` is `malformed`, and a body
  over the size cap is `failed(size)`.
- [ ] T3. Valid RSS 2.0 and Atom fixtures parse title, link, summary and date. A
  `disabled` source is never requested (MockTransport asserts no call).
- [ ] T4. The window keeps an item 25 h old, drops one 27 h old, and counts an undated
  item under `undated`.
- [ ] T5. `normalise_url` strips `utm_*`, `fbclid`, the fragment and the trailing
  slash, and lowercases the host. Two variants of one URL dedupe to one item.
- [ ] T6. An item whose URL (after normalisation) appears as `Source:` in a
  `spike:scout` issue returned by the fake search is excluded, and an item with a new
  URL is kept. When the search fails, `None` leads to `dedupe: unavailable` in the
  footer and both items are kept.
- [ ] T7. Backlog collection filters titles by `SPIKE_TITLE_RE`, parses a
  SpikeDefinition fixture, and returns `None` when `gh` fails.
- [ ] T8. Every scoring and relevance session is built with `tools == []`,
  `allowed_tools == []`, `mcp_servers == {}`, `setting_sources == []` and a non-null
  `output_format`. The test captures the options the stub client received.
- [ ] T9. Schema violations (an unknown id, `impact: 7`, a repo off the allowlist, a
  malformed `related`) lead respectively to the item being dropped as unscored, the
  item being dropped, the repo becoming `.github`, and the `related` entry being
  removed.
- [ ] T10. The budget accumulator stops calling the model when the stubbed
  `total_cost_usd` reaches 1.00, and the remaining items are counted as
  `unscored (budget)`.
- [ ] T11. `rank()` applies the weights and the source weight, and an item with
  `related` set and `novelty <= 1` is marked as "adds to".
- [ ] T12. A short draft gives a full-body URL under
  `https://github.com/mctlhq/<repo>/issues/new` with `labels=spike:scout`, and the
  decoded body contains every template line, including `Lifecycle: proposed` and the
  run id.
- [ ] T13. A long draft makes the URL fall back to the short form, which is at or
  below `MAX_BUTTON_URL_CHARS`, and the full draft appears in the message text or in a
  reply.
- [ ] T14. Article titles containing `<`, `&` or `<a href>` are escaped in the HTML
  message. The rendered digest never exceeds 4096 characters.
- [ ] T15. When every source fails, the text says all sources failed and lists each
  reason, does not contain "nothing today", and the exit code is 1. With one source
  `ok` and no relevant items, the text says no relevant items were found and the exit
  code is 0.
- [ ] T16. `send_message` posts to `.../sendMessage` with the chat id and the inline
  keyboard. On `ok: false` it raises an error that does not contain the token.
- [ ] T17. A source-scan test (in the style of `tests/test_usage_collector_readonly.py`)
  checks that the files under `orchestrator/scout/` and `orchestrator/run_scout.py`
  contain no `getUpdates`, `deleteWebhook`, `setWebhook`, `gh issue`, `gh pr`,
  `-X POST`, `-X PATCH` or `git push`.
- [ ] T18. `--dry-run` with the Telegram env unset prints the digest and makes no
  Telegram request. Without `--dry-run`, missing secrets exit 1 before any feed is
  fetched.
- [ ] T19. Manifest tests: `validate(load("scout"))` returns no errors when the CWFT
  directory contains `mctl-agents-scout`, and the inventory and manifest name sets
  still match.

## Rollback

- Before slice 2 is unsuspended, the scout never runs on a schedule. To roll back,
  revert the mctl-agents PR. The model-policy tasks are additive and unused elsewhere.
  The gitops CWFT can stay. An unreferenced CWFT with a suspended CronWorkflow is
  inert, and the validator only checks CWFTs that manifests name.
- After unsuspension, set `suspend: true` on `cronworkflow-mctl-agents-scout` in
  mctl-gitops. This stops delivery immediately and touches no other agent. The
  mctl-agent webhook on @MCTL_AI_bot is unaffected, because the scout only ever calls
  `sendMessage`.
- No state needs cleaning up. The scout writes nothing, and any `spike:scout` issues
  the owner filed by hand stay as ordinary issues.
