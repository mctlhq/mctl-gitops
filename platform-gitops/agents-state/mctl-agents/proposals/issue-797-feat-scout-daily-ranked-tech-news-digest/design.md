# Design: issue-797-feat-scout-daily-ranked-tech-news-digest

## Current state

Agent pattern (read in the clone):
- Every agent is an AgentManifest under `agents/_manifests/<name>/agent.yaml`
  (`apiVersion: agents.mctl.ai/v1alpha1`, `kind: Agent`). Each one names a
  `runtime.entrypoint`, a `runtime.optionsBuilder` in `orchestrator/options.py`,
  `prompt.sources`, `modelPolicy.task`, `toolPolicy.allow` and
  `execution.{budgetUsd, sandbox.clusterWorkflowTemplate}`. Examples are
  `agents/_manifests/mentor/agent.yaml` and `agents/_manifests/authoring-canary/agent.yaml`.
- `orchestrator/validate_manifest.py` checks those claims against the real code:
  - `_check_tool_policy_and_budget_match_options_py` calls the builder and compares
    `allowed_tools` and `max_budget_usd`;
  - `_check_model_policy_task` requires the task to exist in `config/model-policy.yaml`;
  - `_check_cluster_workflow_template` requires the CWFT name to exist in mctl-gitops
    `argo-workflows/cluster-templates/cwft-*.yaml` (an error under CI);
  - `check_manifests_match_inventory` requires a matching entry in
    `docs/agent-inventory.yaml`;
  - `_builder_call_args` defaults to `(dir, model)`.
- `orchestrator/options.py` is the single place that constructs `ClaudeAgentOptions`.
  `build_authoring_canary_options` (no MCP, no hooks, `setting_sources=[]`, a constant
  budget) is the closest precedent for a minimal, side-effect-free agent. Budgets are
  module constants that read env with a default, for example `MENTOR_BUDGET_USD`.
- `config/model-policy.yaml` defines the profiles `cheap` (claude-haiku-5-5) and
  `balanced` (claude-sonnet-5-5), and the tasks
  `service_agent`, `mentor_digest` and `review_findings_normalize`. Its comment says
  that routing any task to `cheap` needs a separate evaluation.
  `config/settings.py` resolves selections with `resolve_model(task, legacy_model_env=...)`.
- `orchestrator/run_usage_collector.py` is the precedent for a model-free, stateless,
  read-only cron module. It uses `argparse` with `--dry-run`, runs `gh api` GETs only
  through `orchestrator.proc.run_capturing`, refreshes the token with
  `orchestrator.github_token.refresh_github_token`, uses `httpx` with explicit
  timeouts, and keeps per-source failure accounting. `tests/test_usage_collector_readonly.py`
  pins its read-only property by scanning the module source.
- `orchestrator/spike_issue.py` defines `SPIKES_REPO = "mctlhq/.github"`,
  `SPIKES_DIR = "roadmap/spikes"` and `SPIKE_TITLE_RE`. These are reused here to collect
  the spike backlog.
- `orchestrator/auth.py` selects `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`.
- The pinned `claude-agent-sdk==0.2.168` exposes `ClaudeAgentOptions.tools` (an empty
  list disables every built-in tool) and `output_format` (JSON-schema structured
  output). Both are confirmed in `.venv/.../claude_agent_sdk/types.py`.
- `config/settings.py:SERVICES` is the list of mctlhq repositories the agents know.
  It is used here as the target-repository allowlist.
- No module in the repo talks to Telegram today. `httpx==0.28.1` is already a pinned
  direct dependency. No feed parser is a dependency.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/`: the agent family is
  `cwft-mctl-agents-{approve,daily,implement,investigate,reconcile,run,shepherd,usage-collector}.yaml`
  plus `cronworkflow-mctl-agents-{incidents,shepherd,usage-collector}.yaml`. There is no
  `mctl-agents-scout` template yet, which the manifest validator will need (see tasks).
- `cronworkflow-mctl-agents-usage-collector.yaml`: `schedule: "21 * * * *"`,
  `timezone: UTC`, `concurrencyPolicy: Forbid`, first applied suspended and unsuspended
  after a dry-run one-shot. Its comment lists the hourly minutes in use as :00, :03,
  :07, :09, :11, :15 and :21. The other schedules found are `0 3 * * 0`, `15 * * * *`,
  `0 0 * * 6` and `*/30 * * * *`. Minute 40 of hour 06 is free, so `40 6 * * *` does
  not collide with them.
- `cwft-mctl-agents-implement.yaml` `notify-telegram` already reads
  `telegram-bot-token` and `telegram-chat-id` from the `mctl-agents-secrets` Secret,
  with `optional: true`. Which bot that token belongs to was not observed. The scout
  uses its own `SCOUT_TELEGRAM_*` names as the issue specifies.
- `$MCTL_GITOPS_ROOT/services/`: the tenants are admins, karabu, labs and namax66.
  mctl-agents runs as `admins/mctl-agents-worker*`. The mctl-agent webhook service
  behind agent.mctl.ai was not located under `services/`. Its webhook ownership of
  @MCTL_AI_bot is taken from the issue's owner decision, not observed.
- The mctl MCP tools were not called. No deployed-state fact in this design depends on
  them.

## Proposed solution

### Files

```
agents/_manifests/scout/agent.yaml
agents/_scout/sources.yaml        # feeds, weights, ranking config
agents/_scout/PLATFORM.md         # short component map + priorities
orchestrator/scout/__init__.py
orchestrator/scout/feeds.py       # fetch + parse + window
orchestrator/scout/dedupe.py      # URL normalisation + spike:scout lookup
orchestrator/scout/backlog.py     # open spikes + SpikeDefinitions (read-only gh)
orchestrator/scout/scoring.py     # two model passes, schemas, rank
orchestrator/scout/render.py      # Telegram text, draft URL, fallback, footer
orchestrator/scout/telegram.py    # sendMessage only
orchestrator/run_scout.py         # run_scout() entrypoint + argparse main()
```

The prompt templates are module constants in `orchestrator/run_scout.py`
(`RELEVANCE_PROMPT` and `SCORING_PROMPT`). The manifest declares them as `inline`
prompt sources, plus `file: agents/_scout/PLATFORM.md`. This follows the canary's
`inline: orchestrator/run_authoring_canary.py:PROMPT`.

### Manifest

```yaml
apiVersion: agents.mctl.ai/v1alpha1
kind: Agent
metadata: {name: scout, owner: mctl-agents}
spec:
  runtime:
    type: claude-agent-sdk
    entrypoint: orchestrator.run_scout:run_scout
    optionsBuilder: orchestrator.options:build_scout_options
  prompt:
    sources:
      - inline: orchestrator/run_scout.py:RELEVANCE_PROMPT
      - inline: orchestrator/run_scout.py:SCORING_PROMPT
      - file: agents/_scout/PLATFORM.md
      - file: agents/_scout/sources.yaml
  triggers: [cron mctl-agents-scout]   # informational
  modelPolicy:
    task: scout_scoring
  toolPolicy:
    allow: []
  execution:
    budgetUsd: 1.00     # SCOUT_BUDGET_USD
    sandbox:
      backend: argo
      clusterWorkflowTemplate: mctl-agents-scout
```

### Options builder (`orchestrator/options.py`)

```python
SCOUT_BUDGET_USD = float(os.getenv("SCOUT_BUDGET_USD", "1.00"))

def build_scout_options(agent_dir: Path, model: str,
                        output_schema: dict | None = None) -> ClaudeAgentOptions:
    return _scrubbed(ClaudeAgentOptions(
        cwd=str(agent_dir), model=model,
        tools=[], allowed_tools=[], mcp_servers={}, setting_sources=[],
        output_format={"type": "json_schema", "schema": output_schema} if output_schema else None,
        max_budget_usd=SCOUT_BUDGET_USD, max_turns=2,
    ))
```

There are no hooks and no MCP, and `_scrubbed` removes the mctl token from the env.
`allowed_tools=[]` satisfies the validator. `tools=[]` is what actually removes the
built-ins. A unit test asserts both. `SCOUT_BUDGET_USD` is added to the validator's
list of budget env vars, which are cleared before the builder is called.
`_builder_call_args` already handles `(dir, model)`.

### Model policy

`config/model-policy.yaml` gains:
```yaml
  scout_relevance: cheap     # title+summary yes/no; a miss drops an article, never acts
  scout_scoring: balanced
```
`config/settings.py` gains `SCOUT_RELEVANCE_SELECTION` and `SCOUT_SCORING_SELECTION`
via `resolve_model`, with no legacy env override. See Open questions for the `cheap`
caveat.

### Pipeline (`run_scout`)

1. **Load config.** `sources.yaml` has this shape:
   `sources: [{name, url, weight?, enabled?, note?}]`,
   `ranking: {top_n: 10, weights: {impact, novelty, urgency, cost}}`, `window_hours: 26`,
   `dedupe_days: 90`, `repos: [...]` (an optional subset of `SERVICES`).
   An invalid file raises before anything is fetched.
2. **Fetch** (`feeds.fetch_source`). Uses `httpx.Client` with the User-Agent
   `mctl-agents-scout/1 (+https://github.com/mctlhq/mctl-agents)`, a 15 s timeout and
   `follow_redirects=True` (max 5). The body is streamed with a 2 MiB cap. The result
   is a `SourceResult(name, status: Literal["ok","failed","malformed","disabled"],
   reason, items)`:
   - timeouts, transport errors, non-2xx responses and size overruns become `failed`;
   - a parse error, a root that is neither `rss` nor Atom `feed`, or any
     `<!DOCTYPE`/`<!ENTITY` in the first bytes becomes `malformed`.

   Parsing uses stdlib `xml.etree.ElementTree` after the DOCTYPE/ENTITY rejection, so
   no new dependency is needed and entity expansion is refused. Each item carries
   title, link, summary (stripped of HTML and truncated to 600 characters) and
   published time (`pubDate` RFC 2822, or Atom `published`/`updated` RFC 3339). Sources
   are fetched sequentially. There are about 7 of them, so concurrency adds nothing.
3. **Window.** The run keeps items with `now - 26h <= published <= now + 1h`. Undated
   items are dropped and counted.
4. **Dedupe** (`dedupe.py`).
   - `normalise_url()` implements the rule in requirements.md and removes duplicates
     within the run.
   - `scout_issue_urls()` runs
     `gh api -X GET search/issues -f q='org:mctlhq label:"spike:scout" created:>=<date>' --paginate`
     through `run_capturing`, after `refresh_github_token()`. It parses each body's
     `^Source:\s*(\S+)` line and normalises it.
   - On failure the result is `None`, which the footer reports as `dedupe: unavailable`.
     An empty set means the search ran and found nothing. The two cases are never
     conflated.
5. **Backlog** (`backlog.py`). This step is read-only.
   - Open spike issues come from a search for `org:mctlhq is:issue is:open in:title spike`,
     filtered with `SPIKE_TITLE_RE`.
   - SpikeDefinition files come from
     `gh api repos/mctlhq/.github/contents/roadmap/spikes` plus each file's content,
     reusing the base64 and YAML handling idea from `spike_issue.py`.
   - The backlog is reduced to `{ref, title, question, lifecycle}` and capped at 60
     entries and about 8 KB of text.
   - A failure leaves the backlog empty and adds `backlog: unavailable` to the footer.
     Scoring still runs, but novelty is then less reliable, and the footer says so.
6. **Relevance pass.** One SDK session per batch of up to 60 items, on
   `SCOUT_RELEVANCE_SELECTION.model`. The input is JSON
   `[{id, title, source, summary}]`, wrapped in `<untrusted_articles>` tags. The prompt
   states that the content is data. The schema is
   `{items: [{id: str, relevant: bool, why: str(maxLength 200)}]}`.
7. **Scoring pass.** One session per batch of up to 15 relevant items, on
   `SCOUT_SCORING_SELECTION.model`. The context is PLATFORM.md, the backlog JSON and
   the items. The schema requires `impact`/`novelty`/`urgency`/`cost` as integers 0-5,
   `repo` as an enum of the allowlist, `related` as an array of `owner/repo#n` strings
   (maxItems 3), `question` (maxLength 240), `outcomes` (maxLength 60), `pitch_ru`
   (maxLength 160) and `why_en` (maxLength 200). Python then validates the result
   again:
   - an unknown id or an out-of-range value drops the item into `unscored`;
   - an off-allowlist repo is replaced by `.github`;
   - `related` entries that do not match `^mctlhq/[\w.-]+#\d+$` (or the short `.github#41`
     form) are dropped.
8. **Budget.** The run sums `ResultMessage.total_cost_usd` across sessions. Each
   session's `max_budget_usd` is `SCOUT_BUDGET_USD - spent_so_far`. Once the remaining
   budget is 0 or less, the run stops calling the model and counts the remaining
   items as `unscored (budget)`.
9. **Rank.** The score is `source.weight * sum(w_k * v_k)`. Ties break on `urgency`,
   then on recency. The run takes the top N. Each item is classed as a new spike or as
   "adds to X" (when `related` is non-empty and `novelty <= 1`).
10. **Render** (`render.py`).
    - The message uses `parse_mode=HTML`, and every untrusted string goes through
      `html.escape`.
    - Each line reads `<n>. <title> (<source>) score <s>`, then the pitch, then
      `related: ...` or `adds to ...`.
    - `draft_url(item, run_id)` builds
      `https://github.com/mctlhq/{repo}/issues/new?` + `urlencode({title: "spike: <question>", body, labels: "spike:scout"})`.
      If that exceeds `MAX_BUTTON_URL_CHARS = 2000`, it uses the short body
      `Source: <url>`, and the full draft text is appended to the message.
    - The "Draft spike" button goes in `reply_markup.inline_keyboard`, one row per item.
      Every item gets the same draft button. An "adds to #N" item differs only in its
      text line, and its draft's `Related:` names that issue.
    - The footer gives each source's status, then
      `fetched X | in window Y | deduped Z | relevant R | scored S | unscored U`, plus
      `dedupe: unavailable` or `backlog: unavailable` when applicable.
    - The all-sources-failed and nothing-relevant variants are rendered as described
      in requirements.md.
    - The message is capped at 4096 characters. Overflowing fallback drafts are moved
      to reply messages, so the item list itself always fits. When the list is long,
      the item count is reduced before any pitch is truncated.
    - `run_id = os.getenv("WORKFLOW_NAME") or "local-<utc timestamp>"`.
11. **Send** (`telegram.py`). One function, `send_message(token, chat_id, text, markup,
    reply_to=None)`, POSTs to `https://api.telegram.org/bot{token}/sendMessage` with
    `disable_web_page_preview=true`. The method name is a module constant, and no other
    method exists in the module. Errors are raised with the token redacted
    (`orchestrator/redaction.py`, if it fits, or a local replacement).
12. **Exit codes.** The run exits 0 on success, including a day with nothing relevant.
    It exits 1 when all sources failed (after the message is sent), when Telegram
    fails, when secrets are missing without `--dry-run`, or when the config is
    invalid. `--dry-run` prints the text and each button URL, and never needs the
    Telegram env.

The CLI is `python -m orchestrator.run_scout [--dry-run] [--top-n N] [--sources PATH]`.
`run_scout()` is an `async` entrypoint, in line with `run_mentor`.

### Inventory and validator

- `docs/agent-inventory.yaml` gains a `scout` entry with
  `riskLevel: low`, `writes: nothing (Telegram sendMessage only)` and
  `triggeredBy: cronworkflow-mctl-agents-scout`.
- `validate_manifest.py` lists `SCOUT_BUDGET_USD` among the cleared budget env vars.
  There is no catalog profile, so `_AGENT_BY_CATALOG_PROFILE` is unchanged unless
  slice 2 adds a `scout-default` profile.

## Alternatives

1. **Call the Anthropic Messages API directly with httpx** (no Agent SDK). This gives
   cheaper sessions and true tool-free calls. It was dropped because the platform
   authenticates mostly with `CLAUDE_CODE_OAUTH_TOKEN` (`orchestrator/auth.py`). It
   would also bypass the AgentManifest and validator contract and the model-policy
   resolution that every other agent uses. `tools=[]` plus `output_format` achieves
   the same isolation through the SDK.
2. **One model pass (Sonnet over every item).** This is simpler, but there are about
   150-250 items a day with backlog context, which costs several times more and
   pressures the 1.00 USD cap. It was kept as a fallback: setting
   `scout_relevance: balanced` in the model policy gives the same behaviour without a
   code change.
3. **A persistent seen-set (gitops file or mctl-api).** This removes duplicates in the
   overlap window. It was dropped because the issue makes GitHub's `spike:scout`
   issues the only state, and the usage collector shows that stateless runs are the
   house style. A new store would need writes from an agent that must not write.
4. **Adding `feedparser`/`defusedxml`.** These handle more feed variants, but they are
   new pinned dependencies in an image whose dependency list is deliberately minimal.
   Seven known feeds are covered by RSS 2.0 and Atom on ElementTree with a DOCTYPE
   rejection. This can be revisited if a feed comes back `malformed` for a legitimate
   reason.

## Platform impact

- **Migrations:** none. No existing agent, template or schema changes. The model
  policy gains two tasks, which is additive.
- **Backward compatibility:** the validator's set-equality checks
  (inventory and manifests, CWFT existence) gain one agent. CI goes red until the
  mctl-gitops `mctl-agents-scout` CWFT exists on main. Mitigation: merge that gitops PR
  first, with the CronWorkflow `suspend: true`. A template that only runs on manual
  submit is harmless before the module exists.
- **Resources:** one short pod a day (a few minutes) and a few USD a month of model
  spend, capped at 1.00 USD per run by `SCOUT_BUDGET_USD`.
- **Risks and mitigations:**
  - *Prompt injection through articles.* Model calls have no tools, no MCP and no
    settings sources, and return schema-validated output only. The output only becomes
    text, plus a URL to a fixed `github.com/mctlhq/<allowlisted repo>/issues/new` form.
    Article links are shown, never fetched beyond the feed.
  - *Breaking the mctl-agent operator channel.* The module calls only `sendMessage`. A
    source-scan test forbids `getUpdates`, `deleteWebhook` and `setWebhook`.
  - *Silent feed failures.* The tri-state `SourceResult` plus tests that fail if an
    error collapses into an empty list.
  - *Token leakage.* The bot token appears only in the request path, and exceptions are
    redacted.
  - *XML attacks.* DOCTYPE and ENTITY are rejected before parsing, and size is capped.
  - *Cheap-model misses.* The impact is limited to articles not shown. The footer's
    relevant/fetched ratio makes a drop visible.
- **Slice 2 (mctl-gitops, not built here):**
  - `cwft-mctl-agents-scout.yaml` and `cronworkflow-mctl-agents-scout.yaml`
    (`schedule: "40 6 * * *"`, UTC, Forbid, `suspend: true`);
  - env from `mctl-agents-secrets` keys for `SCOUT_TELEGRAM_BOT_TOKEN` and
    `SCOUT_TELEGRAM_CHAT_ID`, plus the existing GitHub read token;
  - unsuspend after a reviewed `--dry-run` one-shot.

## Open questions

- Should `scout_relevance` be `cheap`, as the issue asks, or `balanced`, given the
  model-policy note? This proposal uses `cheap`.
- `MAX_BUTTON_URL_CHARS` (2000) has to be confirmed against real Telegram behaviour.
- Is it acceptable to send overflow fallback drafts as replies under "one message per
  day"?
- The actual RSS URLs for Anthropic news and the claude.com blog were not verified
  here (there was no network check in this run).
- Whether the bot token is copied into `mctl-agents-secrets` or referenced from
  `secret/platform/mctl-telegram/login` is deferred to slice 2.
- Which bot the existing `mctl-agents-secrets` `telegram-bot-token` belongs to was not
  observed.
