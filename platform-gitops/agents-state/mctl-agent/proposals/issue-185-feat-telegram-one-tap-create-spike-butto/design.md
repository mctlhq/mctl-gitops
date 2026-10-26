# Design: issue-185-feat-telegram-one-tap-create-spike-butto

## Current state

- `internal/api/router.go` `telegramWebhookHandler`:
  1. checks `X-Telegram-Bot-Api-Secret-Token` via `telegramSecretOK`;
  2. reads at most `maxWebhookBodyBytes` (1MB) and unmarshals it into `notify.TelegramUpdate`;
  3. returns 200 at once when `update.Message == nil || update.Message.Text == ""`, so every
     `callback_query` update is dropped here today;
  4. forwards a private `/start` through `opts.BotStart` before the allowlist;
  5. refuses commands unless both `opts.TelegramWebhookSecret` and
     `opts.Telegram.HasChatAllowlist()` are set, then checks
     `opts.Telegram.CommandChatAllowed(chat.id)` and logs refusals without the chat id;
  6. runs `handleTelegramCommand` synchronously on `r.Context()`.
- `internal/notify/telegram.go`: `TelegramUpdate` models only `update_id` and `message` (text,
  date, from.id, chat.id/type, entities). Outbound calls go through `doSendTo`, which posts
  `sendMessage` to `tg.apiBase` (overridable with `WithAPIBase` for tests). There is no generic
  Bot API caller and no `answerCallbackQuery`/`editMessageReplyMarkup`. `HasChatAllowlist` and
  `CommandChatAllowed` implement the chat allowlist from `TELEGRAM_CHAT_ID` and the tenant chat
  ids (`config.go` `TELEGRAM_TENANT_CHAT_IDS` / `TELEGRAM_CHAT_ID_<TENANT>`). No user-id
  (owner) check exists anywhere.
- `internal/fixer/github.go`: `GitHubFixer` wraps a `go-github/v68` client authenticated
  through `authTransport` + `tokenSource` (`internal/fixer/token.go`, which re-reads
  `GITHUB_TOKEN_FILE` per request so a rotated installation token is picked up). It is bound to
  `owner`/`repo` = `GITHUB_OWNER` (default `mctlhq`) / `GITHUB_REPO` (default `mctl-gitops`)
  and exposes `CreatePR`, `MergePR`, `ClosePR` and `GetFileContent`. `SetBaseURL` lets tests
  point it at an httptest server. Nothing creates or searches issues today.
- `cmd/agent/main.go` builds `fixer.NewGitHubFixer(...)` and `notify.NewTelegram(...)` and
  passes both into `agentapi.Options` (`GitHub`, `Telegram`).
- `internal/config/config.go` reads `GITHUB_TOKEN`, `GITHUB_TOKEN_FILE`, `TELEGRAM_*`. There is
  no owner-user-id or scout repo setting.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-agent)` returned
  `service not found: admins/mctl-agent`. mctl-agent is not a catalogue service, so its env
  (`TELEGRAM_CHAT_ID`, `GITHUB_TOKEN_FILE`, replicas) could not be observed this way.
- `$MCTL_GITOPS_ROOT/services/`: there is no `mctl-agent` directory. Only
  `admins/mctl-agents-worker*` exist, so the deployed mctl-agent values are unobserved. README.md
  says it runs in the `admins` namespace.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml`: the
  `mctl-agent` target mints from the mctl-agents App (id 4450852) into
  `secret/platform/mctl-agent/tokens#github-token`, synced to ExternalSecret
  `admins/admins-mctl-agent-base-service`. That target has **no `scope`**. The comment on the
  mctl-api target says the installation "carries write on contents, actions, issues,
  pull_requests and workflows across every repository it covers". So mctl-agent's existing
  token can already create issues in the repos the installation covers. No new credential is
  needed. Which repos the installation covers was not observed.
- `$MCTL_GITOPS_ROOT/infra-components/observability/blackbox/vmprobes.yaml`: mctl-agent's public
  host is `agent.mctl.ai`, consistent with the Telegram webhook being served there.

## Proposed solution

### 1. Model the callback (`internal/notify/telegram.go`)

Add `CallbackQuery *TelegramCallbackQuery \`json:"callback_query"\`` to `TelegramUpdate`:

```go
type TelegramCallbackQuery struct {
    ID      string `json:"id"`
    From    struct{ ID int64 `json:"id"` } `json:"from"`
    Data    string `json:"data"`
    Message *struct {
        MessageID   int64 `json:"message_id"`
        Date        int64 `json:"date"` // 0 => InaccessibleMessage
        Chat        struct{ ID int64 `json:"id"`; Type string `json:"type"` } `json:"chat"`
        ReplyMarkup *InlineKeyboardMarkup `json:"reply_markup"`
    } `json:"message"`
}
type InlineKeyboardMarkup struct { InlineKeyboard [][]InlineKeyboardButton `json:"inline_keyboard"` }
type InlineKeyboardButton struct {
    Text string `json:"text"`; URL string `json:"url,omitempty"`; CallbackData string `json:"callback_data,omitempty"`
}
```

Add a private `callAPI(ctx, method string, payload any) error`, factored out of `doSendTo`'s
HTTP code. Make it a no-op when `botToken == ""`. On top of it add two public methods,
`AnswerCallbackQuery(ctx, id, text string)` and
`EditMessageReplyMarkup(ctx, chatID, messageID int64, markup InlineKeyboardMarkup)`. Error
strings must not include the bot token. Return a short sanitised error, as `doSendTo` does
today with the URL removed. Also add `OwnerUserAllowed(userID int64) bool`, backed by a new
`ownerUserID int64` field set through `WithOwnerUserID`. When the owner id is unset it returns
`false`. Unlike `CommandChatAllowed`, there is no open mode.

### 2. Route it (`internal/api/router.go`)

In `telegramWebhookHandler`, insert a branch right after the unmarshal and before the
`update.Message == nil` early return:

```go
if update.CallbackQuery != nil {
    handleTelegramCallback(r.Context(), update.CallbackQuery, opts)
    w.WriteHeader(http.StatusOK)
    return
}
```

`handleTelegramCallback` runs these checks in order. Every refusal logs one `slog.Warn`
carrying only a `reason` and `chat_type`, never ids.
1. `opts.TelegramWebhookSecret != ""`, `opts.Telegram.HasChatAllowlist()`, and owner id set.
   If any is missing, refuse. This is the same fail-closed stance as the command path.
2. `cq.Message != nil` and `opts.Telegram.CommandChatAllowed(cq.Message.Chat.ID)`, otherwise
   refuse silently.
3. `opts.Telegram.OwnerUserAllowed(cq.From.ID)`, otherwise refuse silently.
4. `cq.Data` is parsed by `scoutspike.ParseCallbackData` (`^scout:create:([1-9][0-9]?)$`).
   Any other data is ignored. The query is still answered with empty text, so the client
   spinner stops.

"Silently" means no feedback text. The handler still calls `answerCallbackQuery` with empty
text for a refused press from an allowlisted context, but makes **no** Telegram call at all for
a non-allowlisted chat or user. That avoids talking to strangers, and the press fails without
side effects.

Then it calls `opts.ScoutSpikes.Create(ctx, cq)` (see below) under a 20s timeout derived from
`r.Context()`. The handler answers the callback with the result text and, on
success or already-exists, edits the keyboard.

### 3. New package `internal/scoutspike`

All draft logic lives in this package so it can be tested without HTTP routing.

- `ParseCallbackData(s string) (n int, ok bool)`.
- `FindDraft(markup InlineKeyboardMarkup, n int) (row int, rawURL string, err error)`. It
  looks for the single button with `Text == "Draft spike N"` (after `TrimSpace`) and a non-empty
  `URL`. Zero or several matches return `ErrDraftNotFound`.
- `ParseDraft(rawURL string, allowedRepos map[string]bool) (Draft, error)`. It uses
  `url.Parse` and requires `Scheme == "https"`, `Host == "github.com"` (exact, so no port and
  no subdomain), `User == nil`, and an escaped path that splits into exactly
  `["", "mctlhq", repo, "issues", "new"]`. `repo` must be in `allowedRepos`. The repo match is
  case-sensitive, and `.` and `..` are rejected. From the query it takes `title` (trimmed,
  must start with `spike:`, at most 256 runes) and `body` (at most 60000 bytes, must contain a
  line matching `^Source:\s*(\S+)`). `Labels` is always `[]string{"spike:scout"}`. The draft's
  own `labels` value is ignored, and a different value is logged as `labels_overridden`.
- `NormaliseURL(s string) string`. This is a Go port of mctl-agents `dedupe.normalise_url`
  (rule stated in requirements Open questions) and must be pinned with that module's test
  vectors.
- `Service` holds a `GitHub` interface (below), the repo allowlist, a clock, and an in-process
  guard: `map[normalisedSource]*entry` under a mutex. Each entry has its own mutex and a
  `created *Issue` with an expiry 10 minutes out. `Create` does the following:
  1. lock the per-source entry, so concurrent double taps are serialised;
  2. if `created` has not expired, return `AlreadyExists(created)`;
  3. `SearchSpikeIssues(ctx)`, a search for `org:mctlhq label:"spike:scout"` (no `is:` filter,
     so closed issues count), paged at 100 per page and capped at 10 pages. Any error, a
     non-2xx response, `incomplete_results == true`, or hitting the cap without exhausting
     results returns `ErrSearchFailed`: could not observe is never observed absent;
  4. compare `NormaliseURL(source(issue.body))` with the draft's normalised source. On a
     match, return `AlreadyExists`;
  5. otherwise `CreateIssue(ctx, repo, title, body, ["spike:scout"])`, record it in the guard,
     and return `Created`.
  Entries expire lazily, so the map stays small: a few digest items a day.

The `GitHub` interface is implemented by `*fixer.GitHubFixer` through two new methods in
`internal/fixer/github.go`, which reuse its `client` and so its rotating `tokenSource`:

```go
func (f *GitHubFixer) SearchIssues(ctx context.Context, query string, page int) (*github.IssuesSearchResult, error)
func (f *GitHubFixer) CreateIssue(ctx context.Context, repo, title, body string, labels []string) (number int, htmlURL string, err error)
```

`CreateIssue` always uses `f.owner` (`mctlhq`) as owner. It is not gated by `dryRun`, because
the issue is an explicit human request and not an autonomous fix. Both methods return the
wrapped go-github error, and the handler maps errors to a short reason (`github 403`,
`timeout`) without echoing the response body.

### 4. Feedback

- `answerCallbackQuery` text: `Created <repo>#<n>`, `Already exists: <repo>#<n>`, or
  `Failed: <reason>`, where reason is one of `draft not found`, `draft target not allowed`,
  `draft rejected`, `could not check for duplicates`, `create failed`, `message unavailable`.
  The text is at most 200 characters, as the Bot API limits it.
- On Created or Already exists: copy `cq.Message.ReplyMarkup`, replace row `row` (the row that
  held `Draft spike N`, which render.py also uses for `Create spike N`) with
  `[{Text: "#<n> ->", URL: htmlURL}]`, and call `editMessageReplyMarkup`. A failed edit is
  logged and does not change the answer, because the issue already exists.
- Ordering: answer first, then edit. That way the toast appears even if the edit fails.

### 5. Configuration (`internal/config/config.go`, `cmd/agent/main.go`)

- `TELEGRAM_OWNER_USER_ID`: int64, optional. Invalid values fail startup. Unset means the
  feature is refused.
- `SCOUT_SPIKE_REPOS`: comma-separated repo names, for example
  `mctl-agents,mctl-api,...,.github`. Each must match `^[A-Za-z0-9._-]+$` and must not be `.` or
  `..`. Empty means the feature is refused.
- `main.go` builds `scoutspike.NewService(githubFixer, cfg.ScoutSpikeRepos)` and passes it as
  `agentapi.Options.ScoutSpikes`, and applies `telegram.WithOwnerUserID(cfg.TelegramOwnerUserID)`.
- Startup logs one line with `scout_spike_enabled` and the count of allowlisted repos.
- Update CLAUDE.md's API Endpoints entry for `POST /api/v1/telegram` and the README env table.

### Credentials

There is no new secret. The existing mctl-agent installation token (`GITHUB_TOKEN_FILE`) is
minted unscoped from the mctl-agents App. Per the rotation template, that installation carries
`issues: write` across the repos it covers. The proposal does not verify, and cannot verify
from here, that every repo in `SCOUT_SPIKE_REPOS` is covered by the installation. A
non-covered repo answers 404/403 on create, which surfaces as `Failed: create failed`. The
search also only returns issues the token can see, so for an uncovered repo dedup would be
blind. To guard against that, `Create` first calls `GET /repos/mctlhq/<repo>` and refuses with
`Failed: repo not accessible` on any non-200, before searching.

## Alternatives

1. **Store drafts server-side and put a draft id in `callback_data`** (as mctl-agents could
   publish the drafts). Rejected: it needs a new store shared between mctl-agents and
   mctl-agent, and the issue explicitly asks for a stateless design. The URL button already is
   the single source of the draft, and Telegram echoes it back on the bot's own message.
2. **Have mctl-agent forward the callback to mctl-agents (as `internal/botstart` does for
   `/start`) and let the scout create the issue.** That would keep dedupe logic in Python next
   to `dedupe.normalise_url`. Rejected for now: mctl-agents has no HTTP endpoint for it, the
   feature would depend on two services being up, and it adds a forward token. It stays an
   option if the ported normaliser drifts.
3. **Dedupe only in memory, or only through search.** Memory alone is lost on restart and on
   a second replica. Search alone misses a just-created issue because of GitHub's search index
   lag, so a quick double tap would create a duplicate. Using both closes the realistic window.
   Search stays the authoritative check, and its failure blocks the create.
4. **A separate, narrowed GitHub token for issue creation.** That would be better least
   privilege, but it needs a new mint target in mctl-gitops `cwft-rotate-github-token.yaml`
   (`permissions: {issues: write, metadata: read}`, repositories = the allowlist) and a new
   mounted file. It is deferred and listed as a follow-up, because the existing token already
   holds the permission and the issue asks not to mint new credentials.

## Platform impact

- **Migrations:** none, and no SQLite schema change.
- **Backward compatibility:** text commands and `/start` forwarding are unchanged. The new
  branch only fires when `callback_query` is present, which was previously dropped. With
  `TELEGRAM_OWNER_USER_ID` or `SCOUT_SPIKE_REPOS` unset, the only behaviour change is that the
  callback is no longer silently dropped: the handler refuses it and logs. Safe to deploy
  before the gitops env change.
- **Resource impact:** negligible. A few GitHub calls per tap (repo GET, up to 10 search
  pages, one create) and two Telegram calls. The search API limit (30 per minute) is far above
  a human tap rate.
- **Risks and mitigations:**
  - *Forged callback through a direct POST:* the webhook secret is required, and the chat
    allowlist plus owner id are both checked. Telegram sets `from.id` itself.
  - *Draft URL pointing elsewhere:* the parser checks host, owner, repo and path exactly, and
    the labels are forced. Only the bot's own message carries the reply markup, but the check
    does not rely on that.
  - *Duplicate issue:* the authoritative search plus the per-source in-process guard. Search
    failure blocks the create. Residual risk: two replicas inside the index-lag window (see
    Open questions).
  - *Synchronous handler latency:* the 20s timeout keeps it inside Telegram's webhook timeout.
    If Telegram re-delivers anyway, idempotency makes that harmless.
  - *PII in logs:* no chat or user ids are logged, matching the existing non-allowlisted-chat
    log.
  - *Over-broad token:* pre-existing (unscoped mint). This feature uses only `issues: write`.
    Narrowing is the follow-up in Alternatives 4.
- **Rollout:** (1) merge and release mctl-agent; (2) set `TELEGRAM_OWNER_USER_ID` and
  `SCOUT_SPIKE_REPOS` in mctl-agent's deployment values in mctl-gitops; (3) ship the
  mctl-agents `render.py` change.
