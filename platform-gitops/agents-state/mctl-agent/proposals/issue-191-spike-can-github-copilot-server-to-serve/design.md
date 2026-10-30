# Design: issue-191-spike-can-github-copilot-server-to-serve

## Current state
Credentials and outbound AI/GitHub calls in `mctl-agent`, as read in the clone:

| Credential | Loaded in | Consumer | Destination | Type (per code) | Copilot? |
|---|---|---|---|---|---|
| `GITHUB_TOKEN` + `GITHUB_TOKEN_FILE` | `internal/config/config.go` `Load` (`GitHubToken`, `GitHubTokenFile`) | `fixer.NewGitHubFixer` (`internal/fixer/github.go`) via `tokenSource` + `authTransport` (`internal/fixer/token.go`). The same `GitHubFixer` is reused by `scoutspike.NewService` (`cmd/agent/main.go:88`) | `api.github.com`, `uploads.github.com` only (`defaultGitHubHosts`) | GitHub App installation token, re-minted every 30 min into Vault (comment on `tokenSource`) | No |
| `ANTHROPIC_API_KEY` | `config.Load` (`AnthropicAPIKey`) | `LLMDiagnosisSkill` (`internal/skill/builtin/llm_diagnosis.go`) | `api.anthropic.com/v1/messages` | Provider API key | No |
| `MCTL_API_TOKEN` (falls back to `GITHUB_TOKEN`) | `config.Load` lines ~232-254 | `mctlclient.NewClient` (`cmd/agent/main.go:80`) | mctl-api (in-cluster) | Static service token. If it is unset, the frozen GitHub App token is used (warning comment in code) | No |
| Telegram, webhook and AlertManager secrets | `config.Load` | `internal/api`, `internal/notify` | Telegram / inbound | Static secrets | No |
| CI: mctl-agents App token | `.github/workflows/release-please.yml` | release-please | GitHub | App installation token | No |

A repo-wide search for `copilot` (case-insensitive) finds no match in Go code, config or
workflows. The repository has no Copilot client, endpoint or token.

Deployed state checked:
- `mctl_list_services` (all teams): `mctl-agent` is not a catalogue/tenant service. It is
  not listed. Only `admins/mctl-agents-worker*` (a different repo) and others appear.
- `$MCTL_GITOPS_ROOT/services/*` and `tenants/*`: there is no `mctl-agent` service
  directory. A grep for `ghcr.io/mctlhq/mctl-agent` found no deployment manifest in this
  checkout. `infra-components/data/cnpg/shared/databases.yaml` declares a `mctl-agent`
  database and owner, which confirms the service exists in-cluster.
- A grep for `copilot` across `$MCTL_GITOPS_ROOT` matched only
  `platform-skills/catalog/review-watch/SKILL.md`, which says the Copilot reviewer "is
  not watched". That suggests Copilot is at most a PR-review bot (an org-level GitHub
  App), not a token-driven integration.
- Not observed: `mctl-agent`'s pod env, its Vault keys and the job that mints the GitHub
  App token. The App-token claim rests on code comments only. See Open questions in
  requirements.md.

## Proposed solution
This is a documentation spike with one small guard:

1. **`docs/spikes/copilot-s2s-auth.md`**: holds the inventory table above, refreshed by
   the implementer against HEAD. It also covers:
   - A summary of the feature from the changelog: scope, required App permission, which
     Copilot APIs it covers. Each claim is marked verified or unverified.
   - The decision: **no-go / not applicable for mctl-agent.** There are no Copilot calls,
     and the GitHub credential is already App-based. Adopting Copilot would mean adding a
     second LLM provider next to `LLMDiagnosisSkill`, which the issue does not ask for.
   - Residual risk: the `MCTL_API_TOKEN` to `GITHUB_TOKEN` fallback. The document links
     the existing comment in `config.Load`.
   - Follow-ups: repos and surfaces where Copilot may actually be used (org Copilot
     reviewer, IDE seats, other mctlhq repos). Each one is a candidate for its own spike.
   - A trigger for revisiting the decision: any future Copilot integration must use the
     App path, by reusing `tokenSource` with a separate host allowlist and never a PAT.
2. **Guard test `internal/fixer/copilot_guard_test.go`**: walks the module's non-test
   `.go` files from the repository root and fails if it finds a Copilot API host string
   (`api.githubcopilot.com`, `copilot-proxy.githubusercontent.com`). The failure message
   names the spike document. It is table-driven over the host list, follows the repo's
   convention, and has no runtime effect.
3. **Link from README.md**: add one line next to the `GITHUB_TOKEN` row in the env table,
   pointing to the spike document.

The spike stays inside `mctl-agent`. It changes no runtime code path, so nothing about
token rotation or `authTransport` host scoping moves.

## Alternatives
- **Implement Copilot App auth now** (a new client that exchanges an installation token
  for Copilot access): dropped. Nothing in `mctl-agent` calls Copilot, and the LLM
  provider is Anthropic. This would add a feature, not migrate one.
- **Org-wide inventory in this repo**: dropped. Other repos' credentials can't be grounded
  from this clone, and listing them here would mean guessing. The document lists them as
  follow-ups for mctlhq/.github or the repos that own them.
- **Document-only spike with no guard test**: considered. The guard is cheap and turns
  the "no Copilot here" conclusion into a checked invariant, so it is kept. The
  implementer may drop it if reviewers prefer a pure document.

## Platform impact
- No migrations, no config, env or Helm changes, and no resource impact.
- Backward compatible. Only a document, a test and a README line are added.
- Risk: the guard test could false-positive on a comment that mentions a Copilot host.
  Mitigation: scan only non-test files and keep the host list to exact API hostnames.
  The spike document itself is Markdown and is not scanned.
- Risk: the go/no-go rests on an unverified changelog and unobserved deployed state.
  Mitigation: the document marks each claim verified or unverified.
