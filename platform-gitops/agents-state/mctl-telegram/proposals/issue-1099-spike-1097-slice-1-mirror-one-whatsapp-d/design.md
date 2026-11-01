# Design: issue-1099-spike-1097-slice-1-mirror-one-whatsapp-d

## Current state
- The repo is a single Go module `github.com/mctlhq/mctl-telegram` (`go.mod`, `go 1.26.10`).
  It has no `go.work` and no `spikes/` directory today. Nothing in the tree references WhatsApp
  or whatsmeow, and #1097 appears only in `CHANGELOG.md`, where it is unrelated.
- Production code talks to Telegram as a *user account* over MTProto (`gotd/td`, see
  `internal/telegram/`). There is no Bot API client anywhere in the module. The spike needs only
  three Bot API calls, so it carries its own small `net/http` client and does not reuse
  `internal/telegram`.
- Logging hygiene: `internal/audit/redact.go` is an `slog` handler that drops sensitive attribute
  keys (`text`, `body`, `payload`, `phone`, `code`, `session`, `authorization`, `bearer`, ...) and
  scrubs quoted peers. It lives in the root module's `internal/` tree, so a separate module cannot
  import it. The spike mirrors the policy with a minimal rule: it never passes such values to the
  logger in the first place.
- SQLite: the root module already uses the pure-Go `modernc.org/sqlite v1.58.0`. The spike uses
  the same driver for whatsmeow's `sqlstore`, so no cgo is needed. The spike pins it in its
  *own* `go.mod`.
- Build and CI: `.github/workflows/build.yml` runs `go vet ./...`, `go build ./...` and
  `go test -race ./...` from the repo root, plus `GOOS=darwin/windows` cross-builds. The Go
  `./...` pattern does not descend into a subdirectory that has its own `go.mod`, so a nested
  module is invisible to these steps without any workflow edit. The `Dockerfile` does
  `COPY . .` but builds only `./cmd/server`, `./cmd/login` and `./cmd/canary`, so spike files in
  the build context are never compiled. `.dockerignore` already excludes `*.md`.
- `.gitignore` already ignores `*.db`, `*.sqlite*` and `.env*`. That is a second line of defence;
  the primary rule is that sessions live outside the checkout.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: production runs image tag
  `0.121.1` in tenant `labs`. The spike changes no image, values or env, so the deployed service is unaffected.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/catalog-info.yaml`: namespace `labs`, Argo app
  `labs-mctl-telegram`, source repo `mctlhq/mctl-telegram`. No change is needed.
- No mctl MCP calls were needed. The spike is operator-local and deploys nothing.

## Proposed solution
A new isolated module at `spikes/whatsapp-forum/`:

```
spikes/whatsapp-forum/
  go.mod            module github.com/mctlhq/mctl-telegram/spikes/whatsapp-forum
                    deps: go.mau.fi/whatsmeow, modernc.org/sqlite, github.com/mdp/qrterminal/v3,
                    google.golang.org/protobuf (transitive)
  go.sum
  main.go           wiring: load config -> verify destination -> open session -> connect -> event loop
  config.go         Config + Load(getenv, repoRoot) with validation (no values in errors)
  session.go        session dir checks (absolute, outside checkout, 0700) and sqlstore open (0600)
  route.go          pure routing: Inbound struct, Route(cfg, in, startedAt) Decision
  wa.go             adapter: *events.Message -> Inbound (only reads fields, no client sends)
  telegram.go       Bot API client: getMe, getChat, getChatMemberCount, getChatMember, sendMessage
  verify.go         VerifyDestination(ctx, bot, cfg) error
  route_test.go     table test with synthetic Inbound values
  config_test.go    refusal cases
  verify_test.go    httptest fake Bot API
  nosend_test.go    static guard: no WhatsApp send calls in non-test sources
  README.md         setup / run guide
  CHECKLIST.md      manual QR + end-device checklist, result PENDING
```

### Configuration (`config.go`)
The spike reads only environment variables, and every one is required:
- `WAF_SESSION_DIR`: an absolute path. It is refused if it resolves (after `filepath.EvalSymlinks`
  on the existing prefix) inside the repo toplevel. The toplevel is found by walking up from the
  working directory to the first `.git`. The directory is refused if it exists with any `0077`
  permission bits, and created with `0700` if absent.
- `WAF_WA_PEER`: a single JID, parsed with `types.ParseJID`. It must be a user server
  (`s.whatsapp.net` or `lid`), and group, broadcast and newsletter servers are refused.
- `WAF_PEER_CONSENT`: must equal `yes`.
- `WAF_TG_BOT_TOKEN`: matches `^\d+:[A-Za-z0-9_-]{30,}$`.
- `WAF_TG_CHAT_ID`: a negative int64 starting with `-100` (supergroup).
- `WAF_TG_TOPIC_ID`: a positive int.
- `WAF_TG_OWNER_ID`: a positive int64.

Errors name the variable and the rule, never the value.

### Destination check (`verify.go`)
Called once at startup and again before every send:
1. `getMe`: the bot id.
2. `getChat`: `type == "supergroup"` and `is_forum == true`.
3. `getChatMemberCount == 2`.
4. `getChatMember(owner)`: `status == "creator"`.
5. `getChatMember(bot id)`: `status` is `member` or `administrator`.

With exactly two members, and those two being the owner and the bot, the chat contains only the
owner and the bot. The Bot API cannot list members, but count plus identity proves the same
thing. Any failure at startup is fatal. A failure before a forward drops the message with reason
`destination_unverified`. Each check costs 3 requests and DM traffic is low, so caching is
unnecessary.

### Routing (`route.go`)
`Inbound{ID, Chat, Sender, SenderAlt, IsFromMe, IsGroup, Server, Timestamp, Text, HasNonText}`
is plain data. The result is `Route(...) Decision{Forward bool, Reason string}`, where Reason is one of
`forward`, `other_chat`, `group`, `broadcast`, `own`, `history`, `non_text`, `empty`,
`duplicate`. The order is own, then group/broadcast/newsletter, then other chat, then
history (timestamp before `startedAt`), then non-text, then empty text. Duplicates come from an
in-memory `map[string]struct{}` bounded at 1024 ids, held in the caller. Peer matching normalises
`Chat` and `SenderAlt` to `ToNonAD()` user JIDs and compares them with the configured peer.

### WhatsApp side (`main.go`, `wa.go`, `session.go`)
- `sqlstore.New(ctx, "sqlite", "file:<dir>/wa.db?_pragma=foreign_keys(1)", waLog.Noop)`. After
  the store is created, `os.Chmod` sets the file to `0600`, along with any `-wal`/`-shm` files.
- `whatsmeow.NewClient(device, waLog.Noop)`. whatsmeow's own logs can contain JIDs, so they are
  silenced.
- If `client.Store.ID == nil`, the spike runs the `GetQRChannel` flow and renders each code with `qrterminal`
  to **stdout only**, never through slog.
- The event handler handles only `*events.Message` (to `wa.go` adapter, `Route`, `verify`, then
  `sendMessage`) and logs `*events.Connected`, `*events.LoggedOut` and `*events.StreamReplaced` as
  plain reason strings. `*events.HistorySync` and all other events are ignored.
- Text extraction uses `msg.GetConversation()`, or `msg.GetExtendedTextMessage().GetText()` when
  the former is empty. Any other populated message field sets `HasNonText`.
- `SIGINT`/`SIGTERM` cancel the context and call `client.Disconnect()`.
- The program contains no calls to `SendMessage`, `MarkRead`, `SendPresence`,
  `SendChatPresence`, `SendMediaRetryReceipt`, `Upload`, `RevokeMessage` and the like.
  `nosend_test.go` enforces this.

### Telegram side (`telegram.go`)
- A plain `net/http` client with a 15s timeout and base URL `https://api.telegram.org`. The base
  URL is overridable only from tests.
- `sendMessage{chat_id, message_thread_id, text}` with no `parse_mode`, so no formatting
  injection is possible. Text over 4096 UTF-16 units is split into chunks.
- Error values carry only the method name, HTTP status and Bot API `error_code`. The token sits in
  the URL path, so the client wraps `url.Error` to strip the URL before returning it.

### Logging
`slog.NewJSONHandler(os.Stderr)`. The only attributes are `reason`, `count`, `method`,
`status` and `error_code`. No JIDs, text, token, QR code or paths inside the session dir are logged.

### One command
From `spikes/whatsapp-forum/`, run `go run .` with the env set (README shows an `env` file
kept outside the checkout and loaded with `set -a; . ~/.config/waf/env; set +a`). Tests run
with `go test ./...` in the same directory.

## Alternatives
- **Put the code under the root module (`cmd/whatsapp-forum`).** Dropped: whatsmeow and its
  protobuf dependency tree would land in the root `go.mod`/`go.sum` and be compiled by root CI and
  cross-builds. The issue requires production builds and dependencies to stay untouched.
- **Mirror through the operator's Telegram user account (gotd, reusing `internal/telegram`).**
  Dropped: the issue asks for a dedicated bot, a separate module cannot import `internal/`,
  and posting as the user blurs who authored mirrored content.
- **Use a Bot API library (for example `go-telegram-bot-api`).** Dropped: three or four endpoints don't
  justify an extra dependency, and a hand-rolled client gives control over token redaction in errors.
- **Add a `go.work` to wire the spike in.** Dropped: a workspace file would change how root
  commands resolve modules, which risks the root build.

## Platform impact
- **Migrations:** none. The spike has no database beyond the operator-local whatsmeow SQLite file.
- **Backward compatibility:** root module, Docker image, CI workflows, release-please config and
  deployed service (`labs/mctl-telegram`, tag `0.121.1`) are unchanged. Root `go list ./...` must
  not list any `spikes/` package, and a task verifies this.
- **Resources:** none on the platform. The spike runs only on the operator's machine.
- **Risks and mitigations:**
  - *Leaking private chat content to an unintended audience.* Mitigation: destination
    verification (forum, 2 members, owner is creator, bot present) at startup and before
    every forward. Single-DM allowlist. Explicit consent flag.
  - *Secrets or chat contents in logs.* Mitigation: whatsmeow loggers are `Noop`, the logged
    attribute set is fixed, token-stripped errors, and the QR goes to stdout only.
  - *Session material committed.* Mitigation: the session dir must be absolute and outside the
    checkout, with `0700`/`0600` permissions. `.gitignore` already covers `*.db`.
  - *Account ban / ToS risk of an unofficial client.* Mitigation: the README requires a disposable
    account. The spike is inbound-only and never sends.
  - *Accidental send to WhatsApp.* Mitigation: no send calls exist, and the static guard test
    enforces it.
  - *Licence:* whatsmeow is MPL-2.0. That is acceptable for an isolated spike module, and the
    README notes it.
  - *Dependabot/CodeQL noise from the nested `go.mod`.* This is acceptable for a spike. No config
    change is made in this slice.
