# Scout: a daily ranked tech-news digest that turns approved items into spike drafts

## Context

The owner finds spike ideas for mctl by reading InfoQ, The New Stack, the Cloudflare
blog, Anthropic news, the claude.com blog, the GitHub Blog and the GitHub Changelog on
a phone, then writes each spike by hand. The bottleneck is reading, not deciding: most
articles are irrelevant to mctl, and the relevant ones need the same mapping work each
time (which component, whether a spike already exists, what the outcomes would be).

Issue mctlhq/mctl-agents#797 asks for a new `scout` agent in mctl-agents (slice 1 of
3). Once a day it fetches a checked-in list of RSS/Atom feeds and keeps the items from
the last 26 hours. It removes items already filed as `spike:scout` issues, filters
them with a cheap relevance pass, then scores the survivors against a platform map
and the existing spike backlog. It sends the owner one Telegram message with the top
10. Each item carries a URL button that opens GitHub's new-issue form, pre-filled with
a spike draft, in the target repository. The agent never writes to GitHub. Nothing is
created until the owner taps the button and submits the form. The CronWorkflow and
the Vault secret wiring in mctl-gitops are slice 2, which is out of scope here.

## User stories

- AS the platform owner I WANT one daily Telegram message with the 10 most relevant new
  articles, each scored and mapped to an mctl repository, SO THAT I stop reading
  irrelevant articles to find spike ideas.
- AS the platform owner I WANT a one-tap "Draft spike" button that opens a pre-filled
  GitHub issue form in the right repository SO THAT turning an article into a spike
  takes one review instead of a hand-written issue.
- AS the platform owner I WANT each source's fetch status shown in the message SO THAT
  a broken feed is never mistaken for a quiet news day.
- AS the platform operator I WANT a `--dry-run` that prints the message instead of
  sending it SO THAT the CronWorkflow can be reviewed before it is unsuspended.
- AS a security reviewer I WANT article content handled by model calls that have no
  tools and return only structured output SO THAT a hostile article cannot reach a
  shell, a GitHub write or any other side effect.

## Acceptance criteria (EARS)

Fetch and window
- WHEN a run starts THE SYSTEM SHALL fetch every `enabled: true` source in
  `agents/_scout/sources.yaml`, sending a custom User-Agent, with a per-request timeout
  and a response-size cap.
- WHEN a source returns a parseable RSS 2.0 or Atom document THE SYSTEM SHALL record
  that source's status as `ok(n)`, where n is the number of items parsed.
- IF a source times out, fails at the connection level, returns a non-2xx status, or
  exceeds the size cap THEN THE SYSTEM SHALL record the status `failed(<reason>)` and
  SHALL NOT count it as a source with zero items.
- IF a source returns a body that is not well-formed XML, that is neither RSS nor
  Atom, or that declares a DOCTYPE or ENTITY THEN THE SYSTEM SHALL record the status
  `malformed` and SHALL NOT count it as a source with zero items.
- WHILE a source has `enabled: false` THE SYSTEM SHALL NOT fetch it, and SHALL list it
  in the footer as `disabled` with its note.
- WHEN items are parsed THE SYSTEM SHALL keep only those published within the last 26
  hours of the run's start time. IF an item has no parseable publication date THEN THE
  SYSTEM SHALL drop it and count it under `undated`.

Dedupe
- WHEN items are kept THE SYSTEM SHALL normalise each URL: lowercase the scheme and
  host, drop the fragment, remove `utm_*`, `ref`, `fbclid`, `gclid` and `mc_*` query
  parameters, and remove a trailing slash. It SHALL then drop items whose normalised
  URL duplicates another item's.
- WHEN an item's normalised URL equals the normalised `Source:` URL of any mctlhq
  issue labelled `spike:scout` and created in the last 90 days, open or closed, THE
  SYSTEM SHALL exclude that item.
- WHEN an item's normalised URL does not appear in any such issue THE SYSTEM SHALL NOT
  exclude it on dedupe grounds.
- IF the `spike:scout` issue search fails THEN THE SYSTEM SHALL continue without that
  dedupe and SHALL state `dedupe: unavailable` in the footer. It SHALL NOT report the
  failure as "no duplicates".

Relevance and scoring
- WHEN deduped items exist THE SYSTEM SHALL run one relevance pass on the
  `scout_relevance` model task. Each item yields `relevant: bool` and a one-line
  reason. Only relevant items continue.
- WHEN relevant items exist THE SYSTEM SHALL score them on the `scout_scoring` model
  task. The context is `agents/_scout/PLATFORM.md` plus the current spike backlog
  (title, question and lifecycle of each open spike issue and each SpikeDefinition in
  `mctlhq/.github` `roadmap/spikes/`). Each item yields `impact`, `novelty`, `urgency`
  and `cost` (integers 0-5), plus `repo`, `related`, `question`, `outcomes`,
  `pitch_ru` and `why_en`.
- WHILE any model call is made THE SYSTEM SHALL build its options with
  `tools=[]`, `allowed_tools=[]`, `mcp_servers={}` and `setting_sources=[]`, and SHALL
  require JSON-schema structured output (`output_format`).
- IF a model response does not match the schema, or names an item id that was not
  sent THEN THE SYSTEM SHALL drop that item and count it under `unscored`. It SHALL
  NOT guess values.
- IF the scoring model returns a `repo` outside the configured allowlist of mctlhq
  repositories THEN THE SYSTEM SHALL use `.github` as the target repository.
- WHEN items are scored THE SYSTEM SHALL rank them by the weighted sum
  `w_impact*impact + w_novelty*novelty + w_urgency*urgency + w_cost*cost`, multiplied
  by the source's `weight` (default 1.0). The weights are read from `sources.yaml`.
- IF an item's `related` names an existing spike AND `novelty <= 1` THEN THE SYSTEM
  SHALL render it as "adds to <repo>#<n>" instead of as a new spike.
- WHILE a run is in progress THE SYSTEM SHALL stop making model calls once the
  accumulated `total_cost_usd` reaches the run budget (1.00 USD by default). Items not
  yet processed SHALL be counted under `unscored (budget)`.

Delivery
- WHEN ranking completes THE SYSTEM SHALL send one Telegram `sendMessage` to
  `SCOUT_TELEGRAM_CHAT_ID`. The message lists the top N items (default 10). Each item
  shows its title, source, score, Russian pitch and related issues, and has one inline
  URL button, "Draft spike".
- WHEN a "Draft spike" URL is built THE SYSTEM SHALL target
  `https://github.com/mctlhq/<repo>/issues/new` with `title`, `body` and
  `labels=spike:scout` query parameters. The body follows the draft template in the
  issue: Source, Question, Outcomes, `Lifecycle: proposed`, Related, Why mctl, and the
  generated-by line with the run id.
- IF the encoded URL exceeds `MAX_BUTTON_URL_CHARS` THEN THE SYSTEM SHALL emit the
  short form instead (title plus `Source:` URL only), and SHALL print the full draft
  body in the message text.
- WHEN the message is rendered THE SYSTEM SHALL append a footer listing every source
  with its status, and the counts fetched, in-window, deduped, relevant, scored and
  unscored.
- IF every enabled source is `failed` or `malformed` THEN THE SYSTEM SHALL send a
  message that says all sources failed and lists each reason. It SHALL NOT say
  "nothing today", and the process SHALL exit non-zero after sending.
- IF there are zero ranked items AND at least one source is `ok` THEN THE SYSTEM SHALL
  send a message that says no relevant items were found, with the full footer.
- WHEN `--dry-run` is given THE SYSTEM SHALL print the exact message text and button
  URLs to stdout. It SHALL NOT call Telegram and SHALL NOT need the Telegram secrets.
- IF a run is not a dry run AND `SCOUT_TELEGRAM_BOT_TOKEN` or `SCOUT_TELEGRAM_CHAT_ID`
  is unset THEN THE SYSTEM SHALL exit non-zero before fetching anything.
- IF Telegram's `sendMessage` returns `ok: false` or a non-2xx status THEN THE SYSTEM
  SHALL exit non-zero, and the bot token SHALL NOT appear in any log line.
- WHILE the scout runs THE SYSTEM SHALL call no Telegram method other than
  `sendMessage`. In particular it SHALL NOT call `getUpdates`, `deleteWebhook` or
  `setWebhook`.
- WHILE the scout runs THE SYSTEM SHALL make only read calls to GitHub (`gh api` GET
  and search). It SHALL NOT create, edit, label or comment on any issue.

Manifest and contract
- WHEN `orchestrator/validate_manifest.py` runs THE SYSTEM SHALL validate
  `agents/_manifests/scout/agent.yaml`: the entrypoint resolves, `toolPolicy.allow: []`
  equals the builder's `allowed_tools`, `execution.budgetUsd` equals
  `SCOUT_BUDGET_USD`, and the scout appears in `docs/agent-inventory.yaml`.

## Out of scope

- X/Twitter, share-to-bot intake, and sharing links from the phone.
- Callback buttons (Parked / Skip), a decision log, and learning or weight tuning from
  approvals. These need an inbound webhook, and the chosen bot's webhook belongs to
  mctl-agent.
- Creating issues automatically, creating the `spike:scout` label, starting a DevLoop,
  or writing SpikeDefinition manifests.
- Persistent run state (a seen-set or a cursor). Duplicates across the 2-hour overlap
  are tolerated.
- Sources without an RSS or Atom feed, and HTML scraping of any kind.
- The mctl-gitops ClusterWorkflowTemplate, the CronWorkflow, and Vault writes (slice 2).

## Open questions

- Model tier for the relevance filter. The issue asks for Haiku, but
  `config/model-policy.yaml` says "routing any task to `cheap` needs a separate
  evaluation". This proposal maps `scout_relevance: cheap`. Its failure mode is a
  missed article, not an unattended action, and the dry-run review before unsuspension
  serves as the evaluation. The reviewer should confirm this or switch it to
  `balanced`.
- Telegram does not document a URL length limit for inline buttons.
  `MAX_BUTTON_URL_CHARS` defaults to 2000 (a conservative browser-safe bound) and must
  be confirmed during the real-run acceptance.
- The 4096-character Telegram message limit, when several items fall back to printing
  their full draft. This proposal keeps the digest as one message. Fallback drafts that
  would push it past 4096 characters are sent as replies to that message. Confirm this
  is acceptable under "one message per day".
- Bot token source (Vault copy or reference to `secret/platform/mctl-telegram/login`).
  The issue defers this to slice 2. Slice 1 only reads `SCOUT_TELEGRAM_BOT_TOKEN` and
  `SCOUT_TELEGRAM_CHAT_ID` from the environment.
- Several feeds in the initial list (Anthropic news, the claude.com blog) may have no
  official RSS. Each one's feed URL must be verified when `sources.yaml` is written. A
  source with no feed is listed `enabled: false` with a note, as the issue requires.
- Ordering against mctl-gitops: the manifest validator requires
  `execution.sandbox.clusterWorkflowTemplate` to exist on mctl-gitops main. The
  `mctl-agents-scout` CWFT (with a suspended CronWorkflow) must therefore land first,
  or in the same window. See tasks.md.
