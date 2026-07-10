---
name: mctl-demo-walkthrough
description: Record the mctl-telegram ChatGPT demo walkthrough on the reviewer/test Telegram account and auto-deploy the video to tg.mctl.ai/demo. Use when (re)recording the App Directory demo, refreshing the /demo clip, or when asked to "record the demo" / "redo the walkthrough video" for mctl-telegram.
---

# mctl-telegram demo walkthrough + auto-deploy

Produce the public demo video at https://tg.mctl.ai/demo by driving **ChatGPT
Developer Mode** through the mctl-telegram MCP tools on the **reviewer/demo
Telegram account**, recording it with `gif_creator`, converting to mp4, and
shipping it through the normal PR → release → gitops flow.

## HARD SAFETY RULES (read first)
- **Only** the test/reviewer account **`8745115872` (@mctlhq)**. NEVER the
  operator **`210408407` (@MashkovD)**. ([[reference_mctl_telegram_account_ids]])
- **Verify the surface is the reviewer account before recording:** ask ChatGPT to
  send any message; the tool result MUST contain
  `dry_reason: "reviewer/demo account — sending is preview-only; no message is
  delivered"`. If it sends for real, STOP — you are on the wrong account.
- Sends are auto-dry-run on the reviewer account (0.36.0 reviewer-forced-dry-run,
  [[project_mctl_telegram_demo_reviewer_rollout]]) — so clicking "Send Message" in
  the confirm panel is safe and delivers nothing.
- **ChatGPT Developer Mode AUTO-EXECUTES tools — there is NO reliable deny-able
  panel for `disconnect`.** Confirmed 2026-05-25: prompting "Disconnect my Telegram
  account" ran `disconnect_telegram_account` immediately ("Disconnected your
  Telegram account") with no Deny button. So you CANNOT demonstrate disconnect by
  "deny" — if you issue the prompt, it WILL disconnect for real.
- **Disconnect bricks reviewer re-login until restored.** `disconnect` sets
  `revoked_at` on the account row; `CheckSessionValid` only looks at rows
  `revoked_at IS NULL`, so once the last row is revoked, demo_login (and all RPCs)
  fail with no-active-session. It does NOT wipe `session_encrypted` and does NOT
  log out Telegram-side, so it is recoverable. **Preferred: do NOT issue a
  disconnect prompt at all** — narrate it / show the `/demo` page's disconnect
  copy instead. If it does fire, RESTORE immediately (see Recovery).
- `pin` actually pins (benign + reversible on the demo account). `delete`/`revoke`
  are destructive like disconnect — never prompt them.
- Never put real operator chats / phone numbers / private content on screen.

## Preconditions
- Chrome extension connected; a `chatgpt.com` tab logged in, the **MCTL Telegram**
  connector added, **Developer Mode** ON.
- Connector authenticated as the reviewer account (the dry_reason check above).
- `ffmpeg` available locally (`/opt/homebrew/bin/ffmpeg`).

## Recording sequence
1. Load chrome tools via ToolSearch (`mcp__claude-in-chrome__*`): `tabs_context_mcp`,
   `computer`, `browser_batch`, `gif_creator`, `navigate`, `get_page_text`, `find`.
   Confirm/select the chatgpt.com tab.
2. Open a **New chat** (clean recording). Confirm "Developer mode" banner.
3. `gif_creator start_recording`, then screenshot (first frame).
4. Issue prompts ONE at a time via `browser_batch` (click composer → type → Return →
   `wait` ~8-10s → screenshot). Use English prompts. Cover all eight items:
   1. **Connect** — "Show my connected Telegram accounts" → `list_telegram_identities`
      (demonstrates the connected account / how connection is established). Do NOT
      do a destructive re-auth.
   2. **Search** — "List my recent Telegram chats" → `list_dialogs`. Dismiss any
      "Is this conversation helpful?" popup.
   3. **Summarize** — "Show the recent messages in my <chat> and summarize them" →
      `get_messages` + summary.
   4. **Draft** — "Draft a reply to <chat> saying '...'. Don't send it yet." → draft
      (prepare), shown with an Edit affordance, not sent.
   5. **Send with confirmation** — "Now send it" → confirm panel "Send Telegram
      message to ...?" → click **Send Message** → result is `sent:false` /
      `mode:"draft"` / preview-only (the highlight).
   6. **Pin** — "Pin <the message> in <chat>" → confirm panel → **Send Message**
      (actually pins on the demo account; benign).
   7. **Audit** — "Show my recent audit log" → `get_my_audit_log` (shows the
      draft/sent/list entries — transparency).
   8. **Disconnect** — do NOT prompt "Disconnect my Telegram account" (it
      auto-executes — see safety rules). Either skip it, or capture the `/demo`
      page's "Disconnect or revoke access" copy as the closing frame. If you DO
      run it (or it fires accidentally), the video is still fine — but you MUST
      run Recovery below before finishing.

## Recovery — if the reviewer account got disconnected
Symptom: ChatGPT says "Disconnected your Telegram account"; subsequent reads fail
with no-active-session. The session bytes survive in the revoked row. Restore with
`KUBECONFIG=...k3s-preview/kubeconfig.yaml`, pod `shared-pg-1` in ns `platform-db`,
db `labs-mctl-telegram` (reviewer = `users.telegram_login_id=8745115872`,
`user_id=6462`):
1. Find the newest revoked row that has the session + a real telegram_user_id:
   `SELECT id FROM telegram_accounts WHERE user_id=6462 AND telegram_user_id=8745115872 ORDER BY connected_at DESC LIMIT 1;`
2. Un-revoke it and refresh TTLs so `CheckSessionValid` accepts it:
   `UPDATE telegram_accounts SET revoked_at=NULL, last_used_at=now(), expires_at=now()+interval '24 hours', connected_at=now() WHERE id=<id>;`
3. Verify: ask ChatGPT "List my recent Telegram chats" — it should return chats
   (the pool re-loads the row and reconnects). Keep `send_enabled=false`.
5. `gif_creator stop_recording` (screenshot the final state first), then `export`
   with `download:true`, `showWatermark:false`, `quality:8`,
   `filename:mctl-telegram-demo-walkthrough.gif`. Note: max ~50 frames; keep the run
   tight so frames cover the key panels.

## Auto-deploy (hand off to a background general-purpose agent)
Give the agent a self-contained prompt to:
- Convert the GIF → mp4: `ffmpeg -y -i <gif> -movflags +faststart -pix_fmt yuv420p
  -vf "scale=1280:-2:flags=lanczos" -c:v libx264 -crf 28 internal/web/walkthrough.mp4`
  (target < ~3MB). Replace `internal/web/walkthrough.mp4` in **mctl-telegram**
  (`/Users/dmitriimashkov/PycharmProjects/mctlhq/mctl-telegram`); the route
  `/demo/walkthrough.mp4` + `//go:embed` already exist (0.37.0).
- `go build ./... && go vet ./... && go test ./internal/web/...`; open a PR
  (conventional commit, NO `Co-Authored-By`), post EXACTLY `@claude review`.
- After merge: cut a release. **If the only change is the embedded `.mp4`** it may
  land as `chore`/`docs` and NOT bump — force `Release-As: x.y.z`
  ([[feedback_release_please_docs_no_bump]]). Release PRs merge with `--admin`.
- Bump the gitops cache-buster: edit `DEMO_VIDEO_URL` in
  `mctl-gitops/platform-gitops/services/labs/mctl-telegram/values.yaml` to
  `...walkthrough.mp4?v=N` (increment N) — **hand-edit only**, never
  `mctl_deploy_service` ([[feedback_mctl_env_colon_strip]]). Why the cache-buster:
  Cloudflare caches `.mp4` 404s/old copies; a fresh `?v=N` key dodges stale edge
  cache ([[feedback_cloudflare_caches_404_static_paths]]).
- Verify the new image live by polling **in-pod** (`kubectl exec ... wget
  localhost:8080/demo/walkthrough.mp4`) or the deployed tag — NOT the public CF URL.
  Then confirm `tg.mctl.ai/demo` plays the new clip.

## Done = `tg.mctl.ai/demo` plays the refreshed walkthrough and the `?v=N` asset
returns 200 through Cloudflare.
