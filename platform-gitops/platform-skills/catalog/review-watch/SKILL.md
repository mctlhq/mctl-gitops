---
name: review-watch
description: 'Monitor a GitHub PR in the background for a review-bot response. Watches claude[bot] (claude-review.yml), chatgpt-codex-connector[bot] (@codex review), and — on repos that have it wired up — the agy reviewer, which posts as github-actions[bot] with an `<!-- agy-review -->` marker. Launches a detached shell process that polls until a bot posts a review (line-anchored comments or top-level review body), a top-level issue comment (clean/"no findings"), or reacts with a thumbs-up, then writes a result file you can read at any time. Use whenever the user has just posted "@codex review" or "@claude review" on a PR — or asks you to "watch / monitor / wait for / babysit the review" on a specific PR — and they want hands-off notification instead of manual `gh api` polling. Also use when they queue several PRs at once: launch one watcher per PR, in parallel.'
---

# review-watch — background PR-review monitor (detached shell)

The user has set this up so they don't have to manually re-run `gh api` to check whether a review bot has finished reviewing — claude[bot], chatgpt-codex-connector[bot], and (on repos where it's wired up) the agy pilot reviewer.

## When to invoke

Trigger phrases (Russian or English): "посмотри ответ claude", "монитор claude", "следи за claude", "watch claude on PR X", "wait for claude review", "/review-watch <PR>".

Also invoke this **proactively** (without being asked) whenever you have just posted `@claude review` on a PR via `gh pr comment` and the user seems to be waiting for the response. Posting `@claude review` and then idling is exactly the thing this skill exists to automate.

## Implementation — detached shell, NOT subagent

Use the script at `/tmp/review-watch.sh` (lazily ensure it exists; see "Bootstrap" below). Launch one **detached background shell** per PR via `nohup ... &` + `disown`. The shell process survives across Claude Code sessions and writes a result file when codex responds or after a timeout.

Do NOT spawn an `Agent` for this. Sub-agent runtime has a strong bias toward the `Monitor` tool, which does not block the agent's completion — agents thinking they're "watching" Monitor exit in seconds without ever waiting. Two empirical attempts at agent-based watchers (with explicit "do not use Monitor" instructions) both failed in 26–39 seconds. The detached shell pattern below is what actually works.

## Bootstrap — write `/tmp/review-watch.sh` if missing or stale

Before launching watchers, check that the script is in place AND current:
`grep -qF 'QUOTA_RE=' /tmp/review-watch.sh` — if the file is missing or the
grep fails, (re)write it via Bash heredoc (the entire script body).

**The predicate must be something no older version can satisfy**, and it moves
with every change to the script body. Two regressions taught this:

- Before 2026-08-28 the predicate was the *name* `AGY_MARKER`, which stale
  scripts also defined — with the wrong value `<!-- agy-review-pilot -->`. A
  name-only grep declared them current, so the host kept running a watcher
  that silently missed every agy response until someone deleted the file by
  hand. Fixed by matching the marker's value instead.
- On 2026-08-30 the predicate was still the AGY_MARKER value, so it happily
  accepted a script with no quota handling at all — see below. It is now
  `QUOTA_RE=`, which only the current body defines.

```bash
#!/bin/bash
# Detached PR-review watcher with macOS notification on completion.
# Watches BOTH review bots — claude[bot] (claude-review.yml GH Action) and
# chatgpt-codex-connector[bot] (@codex review) — so it works whichever
# reviewer the repo / trigger uses.
# Args: <repo>           e.g. mctlhq/mctl-openclaw
#       <pr>             e.g. 5
#       <result-file>    e.g. /tmp/review-watch-mctl-openclaw-5.result
#       <log-file>       e.g. /tmp/review-watch-mctl-openclaw-5.log
#       [baseline-ts]    optional explicit baseline, e.g. 2026-07-12T08:04:47Z —
#                        pass the fix-up push time to ignore everything older
set -u
REPO="$1"; PR="$2"; RESULT="$3"; LOG="$4"; BASE_TS="${5:-}"
exec >"$LOG" 2>&1
echo "[$(date -u +%FT%TZ)] watcher start repo=$REPO pr=$PR pid=$$"

# jq predicate matching either review bot. Expanded inside the double-quoted
# --jq strings below; its inner double-quotes survive because shell variable
# expansion happens after quote parsing. Add more bots here if needed.
BOTFILTER='select(.user.login == "claude[bot]" or .user.login == "chatgpt-codex-connector[bot]")'

# agy (Antigravity reviewer) posts via
# `gh pr comment` using the workflow's GITHUB_TOKEN, so its login is the
# generic "github-actions[bot]" — shared with every other Actions-posted
# comment in the repo (release-please, other workflows, etc). Login alone
# is not enough to identify it; every agy comment carries a hidden
# `<!-- agy-review -->` marker, which is the only reliable filter.
#
# The marker MUST match what mctlhq/.github/.github/workflows/agy-review.yml
# actually echoes (`<!-- agy-review -->`; grep "Publish review comment" there).
# It said `<!-- agy-review-pilot -->` until 2026-08-28 and therefore never
# matched anything: every watcher reported agy_comments=0 while agy was
# posting normally. On mctl-agent#105 that hid two real P2 findings, which
# were only caught by checking `gh api .../issues/<N>/comments` by hand.
AGY_MARKER='<!-- agy-review -->'

# A quota/rate-limit notice is NOT a review. It has burned this watcher twice,
# from opposite directions, so it is handled explicitly rather than left to the
# generic comment counters:
#
#  - claude-review.yml posts its own exhaustion warning ("the Claude reviewer
#    hit the shared usage limit...") as github-actions[bot], its workflow
#    identity. That login is NOT in BOTFILTER, so the notice was invisible and
#    the watcher polled out the full 30 min reporting "in progress" while the
#    real (non-blocking) answer had already landed — mctl-api#115, 2026-07-30.
#  - Codex posts "You have reached your Codex usage limits for code reviews"
#    under its OWN login, which IS in BOTFILTER. That counts as a top-level
#    issue comment, trips the hit gate, and — having no line-anchored findings
#    — is then classified CLEAN. On mctl-agents#243 the watcher exited 14
#    seconds after PR open reporting a clean review, while claude and agy had
#    not started. The in-progress guard cannot help: quota text carries no
#    "- [ ]" checkbox and no "Claude Code is working" marker.
QUOTA_RE='hit (your|the shared) (usage )?limit|usage limit|rate.?limit|overloaded|insufficient.*quota|credit balance|reached your Codex usage limits'

notify() {
  local title="$1" body="$2" sound="${3:-Glass}"
  # osascript is macOS-only; skip it elsewhere (e.g. in-cluster Linux) so the
  # log stays clean. The result file is the source of truth either way.
  [ "$(uname)" = "Darwin" ] || return 0
  osascript -e "display notification \"$body\" with title \"$title\" sound name \"$sound\"" >/dev/null 2>&1 || true
}

# Trigger baseline: prefer the latest @claude/@codex review comment if one
# exists. But across every mctlhq repo, claude-review.yml's base trigger is
# `pull_request: [opened, reopened, synchronize, ready_for_review]` — i.e. the
# FIRST review always auto-fires on PR open, and re-reviews after a fix-up
# push auto-fire too (synchronize is already in that trigger list). Only 7/16
# repos (mctl-gitops, mctl-api, mctl-portal, mctl-web, mctl-agents, mctl-docs,
# mctl-telegram) additionally wire up `issue_comment` as a manual rerun path;
# the other 9 (incl. mctl-claude-remote, mctl-openclaw, mctl-design, ...) have
# no comment listener at all, so a posted "@claude review" there is a no-op.
# A missing trigger comment is therefore the COMMON case, not an error — fall
# back to "now" and rely on the caller launching the watcher right after the
# open/push event it wants to observe.
#
# CAVEAT: the latest trigger comment can be OLDER than the event you care
# about (e.g. a day-old "@claude review" on a PR that just got a fix-up push
# via the auto-fire path). Auto-detect would then match the bot's PREVIOUS
# review and false-hit instantly. When an explicit baseline-ts (arg 5) is
# given it wins unconditionally; the reaction check is skipped in that mode
# (no trigger-comment ID to watch), which is fine — reviews/comments cover it.
if [ -n "$BASE_TS" ]; then
  TS="$BASE_TS"
  ID=""
  echo "[$(date -u +%FT%TZ)] using explicit baseline from arg"
else
  TS=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq '[.[] | select(.body | test("@(claude|codex) review"; "i"))] | last | .created_at')
  ID=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq '[.[] | select(.body | test("@(claude|codex) review"; "i"))] | last | .id')
  if [ -z "$TS" ] || [ "$TS" = "null" ]; then
    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    ID=""
    echo "[$(date -u +%FT%TZ)] no trigger comment found; using launch time as baseline (auto-fire repo)"
  fi
fi
echo "[$(date -u +%FT%TZ)] baseline trigger_ts=$TS trigger_id=${ID:-<none>}"
for i in $(seq 1 10); do
  R=$(gh api --paginate "repos/$REPO/pulls/$PR/reviews" --jq "[.[] | $BOTFILTER | select(.submitted_at > \"$TS\")] | length" 2>/dev/null || echo 0)
  C=$(gh api --paginate "repos/$REPO/pulls/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\")] | length" 2>/dev/null || echo 0)
  # Top-level issue comments — codex posts "no findings" results here
  # ("Codex Review: Didn't find any major issues. Swish!") instead of as
  # a PR review when there is nothing line-anchored to flag. Without this
  # check the watcher times out at 30 min while codex has already
  # responded clean within minutes (regression observed on
  # mctlhq/mctl-gitops#91, 2026-05-01).
  I=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\")] | length" 2>/dev/null || echo 0)
  # agy pilot reviewer — see AGY_MARKER note above. Independent of BOTFILTER
  # since its login collides with unrelated github-actions[bot] comments.
  A=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | select(.user.login == \"github-actions[bot]\") | select(.body | contains(\"$AGY_MARKER\")) | select(.created_at > \"$TS\")] | length" 2>/dev/null || echo 0)
  # Real issue comments = $I minus quota notices. This is the number the hit
  # gate and the CLEAN heuristic use; $I is kept only for the log line, so a
  # reader can see the difference at a glance.
  IREAL=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\") | select((.body | test(\"$QUOTA_RE\"; \"i\")) | not)] | length" 2>/dev/null || echo 0)
  # Quota notices from ANY login — deliberately unfiltered, because the two
  # known emitters are a BOTFILTER bot (codex) and a non-BOTFILTER one
  # (github-actions[bot], i.e. claude-review.yml itself).
  Q=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | select(.created_at > \"$TS\") | select(.body | test(\"$QUOTA_RE\"; \"i\"))] | length" 2>/dev/null || echo 0)
  E=""
  [ -n "$ID" ] && E=$(gh api --paginate "repos/$REPO/issues/comments/$ID/reactions" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\") | .content] | last" 2>/dev/null || echo "")
  echo "[$(date -u +%FT%TZ)] tick $i: reviews=$R comments=$C issue_comments=$I (real=$IREAL) agy_comments=$A quota_notices=$Q reaction=$E"
  # Fetch the latest bot issue-comment body up front so the hit gate can tell
  # claude-review.yml's in-progress checklist from a real verdict. The checklist
  # has UNCHECKED boxes ("- [ ]"); a finished verdict has only "- [x]", and codex
  # posts no checklist at all. An issue-comment-only signal that is still a
  # checklist is NOT a response yet -> keep polling (regression: false "clean"
  # on the progress comment, mctlhq/mctl-gitops#267, 2026-05-22).
  # claude[bot]'s FIRST progress comment ("Claude Code is working…") has no
  # checkboxes at all, so match its marker text too (regression: false hit
  # on mctlhq/mctl-gitops#583, 2026-07-12).
  ICBODY=$(gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\") | select((.body | test(\"$QUOTA_RE\"; \"i\")) | not) | .body] | last // \"\"" 2>/dev/null || echo "")
  IC_INPROGRESS=0
  if [ "${IREAL:-0}" -gt 0 ] && [ "${R:-0}" -eq 0 ] && [ "${C:-0}" -eq 0 ]; then
    if printf '%s' "$ICBODY" | grep -qF -- '- [ ]' || printf '%s' "$ICBODY" | grep -qF -- 'Claude Code is working'; then
      IC_INPROGRESS=1
      echo "[$(date -u +%FT%TZ)] issue-comment is an in-progress checklist; still polling"
    fi
  fi
  if [ "${R:-0}" -gt 0 ] || [ "${C:-0}" -gt 0 ] || { [ "${IREAL:-0}" -gt 0 ] && [ "$IC_INPROGRESS" -eq 0 ]; } || [ "${A:-0}" -gt 0 ] || [ "$E" = '"+1"' ] || [ "$E" = "+1" ]; then
    echo "[$(date -u +%FT%TZ)] hit; fetching details"
    {
      echo "status=responded"
      echo "trigger_ts=$TS"
      echo "found_at=$(date -u +%FT%TZ)"
      echo "review_count=$R"
      echo "comment_count=$C"
      echo "issue_comment_count=$IREAL"
      echo "quota_notice_count=$Q"
      echo "agy_comment_count=$A"
      echo "reaction=$E"
      echo "---comments---"
      gh api --paginate "repos/$REPO/pulls/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\") | {user: .user.login, path, line, original_line, body}]"
      echo "---reviews---"
      gh api --paginate "repos/$REPO/pulls/$PR/reviews" --jq "[.[] | $BOTFILTER | select(.submitted_at > \"$TS\") | {user: .user.login, state, body, submitted_at}]"
      echo "---issue_comments---"
      gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | $BOTFILTER | select(.created_at > \"$TS\") | select((.body | test(\"$QUOTA_RE\"; \"i\")) | not) | {user: .user.login, created_at, body}]"
      echo "---quota_notices---"
      gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | select(.created_at > \"$TS\") | select(.body | test(\"$QUOTA_RE\"; \"i\")) | {user: .user.login, created_at, body}]"
      echo "---agy_comments---"
      gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | select(.user.login == \"github-actions[bot]\") | select(.body | contains(\"$AGY_MARKER\")) | select(.created_at > \"$TS\") | {user: .user.login, created_at, body}]"
    } > "$RESULT"
    # "Clean" detection paths (bot signals):
    # 1. 👍 reaction on the trigger with no line-anchored reviews/comments
    # 2. Top-level issue comment with no line-anchored findings
    #    (a bot posts a top-level "no issues" comment when clean)
    CLEAN="0"
    if { [ "$E" = '"+1"' ] || [ "$E" = "+1" ]; } && [ "${R:-0}" -eq 0 ] && [ "${C:-0}" -eq 0 ]; then
      CLEAN="1"
    fi
    if [ "${IREAL:-0}" -gt 0 ] && [ "${R:-0}" -eq 0 ] && [ "${C:-0}" -eq 0 ]; then
      CLEAN="1"
    fi
    if [ "$CLEAN" = "1" ] && [ "${A:-0}" -eq 0 ]; then
      notify "review-watch [$REPO#$PR]" "clean review (no findings)" "Glass"
    else
      TOTAL=$(( ${R:-0} + ${C:-0} + ${IREAL:-0} + ${A:-0} ))
      notify "review-watch [$REPO#$PR]" "$TOTAL response(s) — read $RESULT" "Glass"
    fi
    exit 0
  fi
  [ "$i" -lt 10 ] && sleep 180
done
# A quota notice with no real signal after the full window is a DIFFERENT
# outcome from silence: some bot was asked and answered "not now". Reported as
# its own status so the reader does not mistake it for either a clean review or
# a dead trigger.
#
# Note it does NOT short-circuit the polling loop. An earlier design exited on
# the first quota tick; on mctl-agents#244 that would have quit at second ~15
# and missed codex's real review — two P2 findings — posted 5 minutes AFTER its
# own quota notice, plus claude and agy, which had not started. Waiting out the
# window costs 30 min of background polling and nothing else.
if [ "${Q:-0}" -gt 0 ]; then
  {
    echo "status=quota_exhausted"
    echo "trigger_ts=$TS"
    echo "quota_notice_count=$Q"
    echo "---quota_notices---"
    gh api --paginate "repos/$REPO/issues/$PR/comments" --jq "[.[] | select(.created_at > \"$TS\") | select(.body | test(\"$QUOTA_RE\"; \"i\")) | {user: .user.login, created_at, body}]"
  } > "$RESULT"
  echo "[$(date -u +%FT%TZ)] quota_exhausted"
  notify "review-watch [$REPO#$PR]" "reviewer hit a usage limit — NOT reviewed" "Basso"
  exit 0
fi
echo "status=timeout" > "$RESULT"
echo "trigger_ts=$TS" >> "$RESULT"
echo "[$(date -u +%FT%TZ)] timeout"
notify "review-watch [$REPO#$PR]" "timeout after ~30 min, no review response" "Basso"
```

> **Known caveat — claude[bot] progress checklist.** When `claude-review.yml`
> is also active, claude[bot] posts a *progress checklist* as a top-level
> issue comment seconds after the trigger, then edits it as it works. The hit
> gate guards against this: an issue-comment-only signal whose body still has an
> unchecked `- [ ]` box is treated as in-progress and the watcher keeps polling
> (a finished verdict has only `- [x]`, and codex posts no checklist). This
> matters for automated readers (e.g. pr-steward) that parse the result file
> rather than eyeballing it — without the guard every tick would misread the
> checklist as a clean review.

Save with `chmod +x /tmp/review-watch.sh`.

### macOS notification permission

`notify` calls `osascript -e 'display notification ...'` — best-effort, fails silently if unavailable. On first use, macOS may prompt for notification permission for the parent terminal/process. If the user reports "I don't see notifications", point them to `System Settings → Notifications` and look for the host app (Terminal, iTerm2, Script Editor depending on which process invoked osascript). The result file still gets written either way; OS notification is the convenience layer, not the source of truth.

## Launch a watcher

For each PR (`<owner>/<repo>` and `<N>`), in a single Bash call:

```bash
nohup /tmp/review-watch.sh <owner>/<repo> <N> \
  /tmp/review-watch-<repo-stem>-<N>.result \
  /tmp/review-watch-<repo-stem>-<N>.log \
  [baseline-ts] \
  >/dev/null 2>&1 &
PID=$!
disown $PID 2>/dev/null
echo "watcher pid=$PID"
```

`<repo-stem>` = repo name without owner (e.g. `mctl-openclaw`). Multiple PRs ⇒ launch each in its own `nohup ... &` invocation, all in parallel from a single Bash call.

**When to pass `baseline-ts`:** whenever the review you're waiting for was triggered by a PUSH (PR open or fix-up push on an auto-fire repo), pass that push's timestamp explicitly — e.g. `git log -1 --format=%cI` converted to UTC, or `date -u +%Y-%m-%dT%H:%M:%SZ` right after pushing. Without it, auto-detect anchors on the latest `@claude review` comment, which may be days old and would false-hit on the bot's previous review. Omit the arg only when you have JUST posted a fresh `@claude review` comment (auto-detect then finds exactly it, and the 👍-reaction path stays active).

## Reading results

When the user later asks "did codex respond yet?" or similar, just `Read` the `.result` file:

- If the file does not exist yet → watcher still polling. `Read /tmp/review-watch-<stem>-<N>.log` for current tick number to estimate.
- If file contents start with `status=responded` → parse and report findings (Format A).
- If `status=quota_exhausted` → Format E. A reviewer was triggered and answered
  "not now"; the diff was never read.
- If `status=timeout` → Format C.

`quota_notice_count` can also be non-zero on a `status=responded` result: one
bot was rate-limited while another reviewed normally. Say which, rather than
reporting the PR as fully reviewed.

## Output formats (when reporting to the user)

  Format A — findings:

    [claude] <repo>#<N>: K findings (X P1, Y P2, Z P3)
    https://github.com/<repo>/pull/<N>
    - Pn {file}:{line} — {one-line summary}
    ...

  Format B — clean (no findings, signaled by either 👍 reaction or a top-level issue comment from claude[bot] with no line-anchored comments/reviews):

    [claude] <repo>#<N>: clean review (no findings)
    https://github.com/<repo>/pull/<N>

  Format C — timeout (~30 min, claude[bot] never responded):

    [claude] <repo>#<N>: no claude review response after ~30 min
    Trigger: <trigger_ts>
    Re-post @claude review or check repo settings.

Severity parsing: claude[bot] prefixes each finding's body with a markdown badge `![P2 Badge](...)` — extract the `P0` / `P1` / `P2` / `P3` token. agy writes plain `**Severity:** P1` / `- **Severity:** P1` lines instead — extract the token the same way. If absent, mark as `P?`.

One-line summary per finding: take the first **bold heading** (between `**`) from the comment body and trim to ~80 chars. Do NOT include the explanatory paragraph or full body — the user clicks into the PR for full context.

  Format D — agy pilot findings (non-blocking, informational only — never treat as a merge gate):

    [agy] <repo>#<N>: K findings (X P1, Y P2, Z P3)
    https://github.com/<repo>/pull/<N>
    - Pn {file}:{line} — {one-line summary}
    ...
    (pilot, non-blocking — does not affect merge gate)

  If agy's comment body is exactly "No significant issues found.":

    [agy] <repo>#<N>: no significant issues found (pilot, non-blocking)

  Format E — quota exhausted (a reviewer was triggered but hit a usage limit and
  never read the diff):

    [<bot>] <repo>#<N>: hit a usage limit — the diff was NOT reviewed
    https://github.com/<repo>/pull/<N>
    Trigger: <trigger_ts>

  Never report this as clean. It is not a verdict, and it does not satisfy a
  merge gate. Re-trigger later, or — if another reviewer covered the current
  head — surface the trade-off to the user instead of deciding alone (the
  merge-gate rule in global CLAUDE.md still nominally wants claude[bot]).

## Multiple PRs

Single Bash call launching multiple `nohup` background processes is fine — each `&` detaches, each runs independently with its own result/log path.

## Argument parsing

Accepted forms from the user:
- `mctlhq/mctl-openclaw#5`
- `https://github.com/mctlhq/mctl-openclaw/pull/5`
- `5` (only if the user has just opened exactly one PR in conversation context — pick the most recent)

If args are ambiguous, ask which PRs in one short AskUserQuestion before launching.

## Operational notes

- The detached shell uses `nohup` + `disown` + stdout/stderr redirection — it survives Claude Code session boundaries. A future session can read the result file and report.
- Codex usually responds within 1–5 minutes of `@claude review`. The 180s tick cadence catches it within the next tick. Sometimes codex takes 5–15 min when busy.
- Result-file path convention: `/tmp/review-watch-<repo-stem>-<N>.result` — keep this stable so future sessions can find it without args.
- If `gh api` returns 403/404, the watcher writes a status-error result and exits. No retries — auth/permission issues won't fix themselves.
- The first `@claude review` issue comment is the trigger baseline. If the user re-triggers (posts `@claude review` again after a fix-up), launch a new watcher — the script's baseline-detection `last` filter picks up the latest trigger automatically. For push-triggered re-reviews (no fresh comment), always pass the explicit `baseline-ts` arg instead.

## What this skill is NOT for

- One-shot "check codex now" — for that, just call `gh api` directly. This skill is for the wait-and-notify case.
- Reviews from bots other than `claude[bot]` / `chatgpt-codex-connector[bot]` / agy (marker-matched, see `AGY_MARKER`) — add the login (and a body marker, if the bot shares a generic login like `github-actions[bot]`) to the script. For an entirely different review surface, write a sibling skill.
- Long-term watching across multiple `@claude review` retries — re-launch after each new trigger.
- Treating agy findings as a merge blocker — the pilot is explicitly non-blocking (see [[project_agy_reviewer_pilot]] memory); only claude[bot] / codex P1-P2 gate a merge.

## Anti-patterns (do not regress)

1. **`Agent` + `Monitor` tool**: sub-agent runtime treats Monitor as fire-and-forget and exits in seconds without waiting. Always use detached shell instead.
2. **Synchronous Bash in foreground**: blocks the user's session for up to 30 min, defeats the "background" goal. Always `nohup ... &` + `disown`.
3. **Polling without baseline timestamp**: if you check `pulls/<N>/reviews` without filtering by `> $TRIGGER_TS`, you'll match codex's previous (pre-fixup) review and falsely report "responded" immediately. Always filter by the latest `@claude review` issue-comment timestamp.
4. **Counting a quota notice as a review**: see `QUOTA_RE`. Codex's notice comes from its own login and otherwise sails straight through the hit gate and out the CLEAN branch. A quota notice is an answer about capacity, not about the diff.
5. **Exiting on the first quota tick**: a bot that just reported a usage limit can still review minutes later — observed on mctl-agents#244, where codex posted the notice and then delivered two real P2s five minutes on. Keep polling; classify at the end.
6. **Trusting the result file as the complete account of a PR's reviews**: the watcher exits at its first hit, so anything a second bot posts afterwards never appears in any result file. Before merging, always sweep `gh api repos/<owner>/<repo>/pulls/<N>/comments` and `.../issues/<N>/comments` unfiltered, full history.
