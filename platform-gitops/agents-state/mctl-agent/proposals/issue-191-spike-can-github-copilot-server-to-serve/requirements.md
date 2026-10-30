# Spike: Copilot server-to-server (GitHub App) authentication for mctl-agent: inventory and go/no-go

## Context
Issue #191 (scout digest 2026-10-28) asks whether GitHub Copilot's new server-to-server
authentication, which lets a GitHub App call Copilot without a user token, would let
mctl's Copilot usage move off personal tokens. It asks for two outcomes: an inventory of
user tokens used for Copilot calls, and a go/no-go decision on App-based auth.

For `mctl-agent` specifically, the code shows no Copilot usage at all:
- The only LLM is Anthropic's Messages API (`internal/skill/builtin/llm_diagnosis.go`,
  `anthropicMessagesURL`, keyed by `ANTHROPIC_API_KEY`).
- The GitHub credential (`GITHUB_TOKEN` / `GITHUB_TOKEN_FILE`, `internal/config/config.go`)
  is already a GitHub App installation token that rotates every 30 minutes
  (`internal/fixer/token.go`). It is only ever sent to `api.github.com` and
  `uploads.github.com`.
- Repository CI (`.github/workflows/*.yml`) has no Copilot step. release-please already
  mints a token from the mctl-agents App.

The spike is therefore a documented finding, not a migration. It records the inventory
with evidence, gives a go/no-go for this repo, and names the remaining fallback where a
user-style token could still reach a non-GitHub service (the `MCTL_API_TOKEN` fallback
to `GITHUB_TOKEN` in `config.Load`).

## User stories
- AS a platform operator I WANT a written inventory of every credential `mctl-agent`
  uses to reach GitHub or an LLM SO THAT I know whether any personal or user token still
  powers Copilot or other AI calls.
- AS a platform operator I WANT a clear go/no-go on Copilot App-based auth for
  `mctl-agent` SO THAT the scout item can be closed or handed to the repos where it
  actually applies.
- AS a maintainer I WANT a regression guard SO THAT a future change cannot silently add
  a Copilot endpoint or a personal-token code path without the spike's conclusion being
  revisited.

## Acceptance criteria (EARS)
- WHEN the spike is complete THE SYSTEM SHALL include `docs/spikes/copilot-s2s-auth.md`
  with a credential inventory table. Each row gives the env var or file, the consumer
  symbol and file, the destination host, the token type (App installation, API key,
  static service token, personal) and whether it is used for Copilot.
- WHEN the spike is complete THE document SHALL state a go/no-go decision for
  `mctl-agent`. Given the current code, that decision is "no-go / not applicable: no
  Copilot calls exist; the GitHub credential is already an App installation token".
- WHEN the document lists the `MCTL_API_TOKEN` to `GITHUB_TOKEN` fallback in
  `internal/config/config.go` THE document SHALL record it as the only path where a
  GitHub-issued token reaches a non-GitHub host, and link the existing in-code warning.
- IF any Go source file outside tests contains a Copilot API host
  (`api.githubcopilot.com` or `copilot-proxy.githubusercontent.com`) THEN the guard test
  SHALL fail and point the reader to the spike document.
- WHILE `internal/fixer.authTransport` is in use THE SYSTEM SHALL keep sending the GitHub
  token only to the hosts in `defaultGitHubHosts`. Existing behaviour does not change.
- IF deployed-state facts (Vault key names, the token-minting job, the pod spec) could not
  be observed during the spike THEN the document SHALL list them as unverified, not as
  absent.

## Out of scope
- Adding any Copilot integration to `mctl-agent`.
- Changing how the GitHub App installation token is minted, stored in Vault or rotated.
- Auditing Copilot usage in other mctlhq repos (mctl-agents, mctl-telegram, mctl-api,
  developer laptops/IDEs). The document lists them as follow-up candidates only.
- Removing the `MCTL_API_TOKEN` fallback. That is a separate behaviour change.

## Open questions
- The issue says "mctl's Copilot usage" without naming where it happens. In
  `mctl-agent` there is none. If Copilot is used elsewhere (IDE seats, the Copilot review
  bot, other repos), the real inventory belongs in those repos or in mctlhq/.github.
  This proposal concludes for `mctl-agent` only.
- The changelog entry (github.blog, 2026-10-27) was not fetched or verified in this run.
  The spike must confirm that the feature exists, which Copilot APIs it covers (chat
  completions vs. review vs. agent) and which App permission it requires before any
  "go" is given anywhere.
- `mctl-agent`'s deployment manifest (env, Vault keys, token-minting CronWorkflow) was
  not found in the mctl-gitops checkout available to this run. The claim that the
  deployed `GITHUB_TOKEN` is an App installation token rests on code comments in
  `internal/fixer/token.go`, not on observed deployed state.
