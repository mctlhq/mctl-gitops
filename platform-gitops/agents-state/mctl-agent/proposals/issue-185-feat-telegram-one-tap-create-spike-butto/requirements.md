# One-tap "Create spike N" for the scout digest (mctl-agent callback handler)

## Context

The mctl-agents scout digest (mctlhq/mctl-agents#797) gives each item a "Draft spike N"
URL button. The button opens a pre-filled GitHub `issues/new` form. On Android the GitHub
app intercepts the link and drops the `title`/`body`/`labels` prefill, so the owner has to
copy the link into a browser before submitting it. The issue asks for a second inline button,
`Create spike N` with `callback_data = "scout:create:N"`, which creates the issue directly from
the bot. The design is stateless: the draft is read back from the "Draft spike N" URL button
on the bot's own message, which Telegram returns in `callback_query.message.reply_markup`.

This proposal covers only the mctl-agent half: handling `callback_query` updates on
`POST /api/v1/telegram`. Today `telegramWebhookHandler` (`internal/api/router.go`) returns
200 for every update that has no `message.text`, so a callback is dropped and its spinner
never stops. The handler must ship before the mctl-agents `render.py` change that adds the
button, so the button never goes live while nothing handles it.

## User stories

- AS the platform owner I WANT to tap `Create spike N` on a scout digest item SO THAT the
  spike issue is created in the right mctlhq repo without leaving Telegram.
- AS the platform owner I WANT a second tap or a Telegram re-delivery to return the existing
  issue SO THAT a spike is never filed twice.
- AS a platform operator I WANT callback presses from any other chat or user, and drafts that
  point outside the allowed repos, to be refused SO THAT the bot cannot be used to file issues
  on someone else's behalf or in arbitrary repositories.

## Acceptance criteria (EARS)

Routing and authentication
- WHEN `POST /api/v1/telegram` receives an update with a `callback_query` THE SYSTEM SHALL
  handle it on the callback path and SHALL NOT pass it to `/start` forwarding or text-command
  parsing.
- IF the webhook secret (`TELEGRAM_WEBHOOK_SECRET`) is unset, OR the chat allowlist
  (`TELEGRAM_CHAT_ID` / tenant chat ids) is empty, OR the owner user id
  (`TELEGRAM_OWNER_USER_ID`) is unset THEN THE SYSTEM SHALL refuse every `scout:create`
  callback, create nothing, and log the misconfiguration without chat or user ids.
- IF `callback_query.message.chat.id` is not allowlisted per `Telegram.CommandChatAllowed`
  THEN THE SYSTEM SHALL refuse the press silently, make no GitHub call, and log the refusal
  without chat or user ids.
- IF `callback_query.from.id` is not equal to the configured owner user id THEN THE SYSTEM SHALL
  refuse the press silently, make no GitHub call, and log the refusal without chat or user ids.
- IF `callback_query.data` does not match `scout:create:<N>`, where N is a decimal integer from
  1 to 99 with no leading zero, THEN THE SYSTEM SHALL ignore the callback and create nothing.
- IF `callback_query.message` is missing or inaccessible (no `reply_markup`, or `date == 0`)
  THEN THE SYSTEM SHALL answer `Failed: message unavailable` and create nothing.

Draft parsing and allowlist
- WHEN a `scout:create:N` press passes authentication THE SYSTEM SHALL take the draft only from
  the inline button in `callback_query.message.reply_markup` whose text is exactly
  `Draft spike N` and which carries a `url`.
- IF no such button exists, or more than one does, THEN THE SYSTEM SHALL answer
  `Failed: draft not found` and create nothing.
- IF the draft URL's scheme is not `https`, OR its host is not exactly `github.com`, OR it
  carries userinfo or a port, OR its path is not exactly `/mctlhq/<repo>/issues/new`, OR
  `<repo>` is not in the configured repo allowlist (`SCOUT_SPIKE_REPOS`) THEN THE SYSTEM SHALL
  answer `Failed: draft target not allowed` and create nothing.
- IF the draft title, after trimming, does not start with `spike:`, OR the body has no
  `Source:` line, OR the title or body is longer than the limits in design.md THEN THE SYSTEM
  SHALL answer `Failed: draft rejected` and create nothing.
- WHILE creating an issue from a draft THE SYSTEM SHALL set the labels to exactly
  `["spike:scout"]`, whatever the draft's `labels` parameter says.

- IF the GitHub token cannot read `mctlhq/<repo>` (the repo check answers anything but 200)
  THEN THE SYSTEM SHALL answer `Failed: repo not accessible` and create nothing, because
  a search the token cannot see into would wrongly report no duplicate.

Idempotency
- WHEN a draft is accepted THE SYSTEM SHALL search GitHub for `org:mctlhq label:"spike:scout"`
  issues (any state) before creating anything, and compare each result's normalised `Source:`
  line with the draft's normalised `Source:` line.
- IF a matching issue exists THEN THE SYSTEM SHALL create nothing and answer
  `Already exists: <repo>#<n>`.
- IF the GitHub search fails, times out, or returns `incomplete_results: true` THEN THE SYSTEM
  SHALL create nothing and answer `Failed: could not check for duplicates`.
- WHILE one `scout:create` press for a given normalised source is in flight THE SYSTEM SHALL
  serialise further presses for the same source in this process, and for at least 10 minutes
  after a successful create it SHALL return the created issue from memory without searching.
  This covers the GitHub search index lag on a double tap.

Create and feedback
- WHEN no duplicate is found THE SYSTEM SHALL call `POST /repos/mctlhq/<repo>/issues` once,
  with the parsed title, the parsed body and the label `spike:scout`.
- WHEN the issue is created or found THE SYSTEM SHALL call `answerCallbackQuery` with
  `Created <repo>#<n>` or `Already exists: <repo>#<n>`. It SHALL then call
  `editMessageReplyMarkup` to replace the row holding `Draft spike N` with a single URL button
  `#<n> ->` that links to the issue's `html_url`, and leave every other row unchanged.
- IF the create call fails THEN THE SYSTEM SHALL answer `Failed: <short reason>` and leave the
  keyboard unchanged.
- WHILE handling callbacks THE SYSTEM SHALL use only the Telegram methods `answerCallbackQuery`
  and `editMessageReplyMarkup`, and SHALL NOT call `getUpdates`, `deleteWebhook` or
  `setWebhook` from this path.
- WHEN the callback handling finishes, whatever its outcome, THE SYSTEM SHALL return HTTP 200 to
  Telegram. Only a bad secret returns 401, and only an unreadable body returns 400, as today.

## Out of scope

- The mctl-agents `render.py` change that adds the `Create spike N` button (the second step of
  the rollout, in mctlhq/mctl-agents).
- Any new store, database table or secret beyond the two new configuration values.
- Minting a new GitHub PAT or GitHub App. This proposal uses the existing mctl-agent
  installation token (see design.md, Credentials).
- Narrowing the mctl-agent GitHub token at mint time in mctl-gitops
  (`cwft-rotate-github-token.yaml`). That is worth doing, but it is a separate change.
- Callback actions other than `scout:create`.
- Cross-replica deduplication beyond the GitHub search. The in-memory guard is per process.

## Open questions

- Exact `dedupe.normalise_url` semantics in mctl-agents are not visible from this repo. The
  design ports a stated rule (lowercase scheme and host, drop the fragment, drop a trailing
  slash, drop `utm_*` query parameters, sort the remaining query). The implementer must check
  that rule against mctl-agents' `dedupe.py` and copy its test vectors. If they differ, the
  mctl-agents implementation wins.
- The repo allowlist must equal the scout's SERVICES plus `.github`. That list lives in
  mctl-agents and was not observed here, so it is configured through `SCOUT_SPIKE_REPOS` with
  no built-in default. An empty value disables the feature (fail closed).
- The owner's Telegram user id, and whether the chat that receives the scout digest is in
  mctl-agent's `TELEGRAM_CHAT_ID`/tenant allowlist, could not be observed: the deployed
  mctl-agent values were not found in the gitops checkout or through mctl MCP (see design.md).
  If the digest goes to a chat that is not allowlisted, every press is refused until it is
  added.
- The exact button text emitted by `render.py` is assumed to be `Draft spike N`, as the issue
  states. If render.py adds a prefix or emoji, the matcher must be updated in step with it.
- Replica count of mctl-agent was not observed. With more than one replica the in-memory guard
  does not cover a double tap that lands on two pods within the search-index lag window.
