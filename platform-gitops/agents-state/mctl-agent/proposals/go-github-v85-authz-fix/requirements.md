# Upgrade google/go-github to v85 (Authorization header leak prevention)

## Context
mctl-agent uses `google/go-github` **v68** to create fix-PRs in the `mctlhq/mctl-gitops`
repository. The client authenticates via a GitHub App installation token rotated every
30 minutes.

In version v85.0.0 (2026-04-20), **cross-host redirect rejection** was added: on an HTTP
redirect to a host different from the original, the client now refuses to forward the
`Authorization` header to a third-party server. In v68 this protection is absent — if the
GitHub API (or any configured endpoint) returns a redirect to an external host, the
installation token is passed to the third party. The installation token grants write
access to `mctl-gitops`, which means a potential supply-chain compromise.

Gap: v68 → v85 = 17 major versions; there are breaking changes that require code adaptation.

## User stories

- AS a security engineer I WANT mctl-agent's GitHub client to reject cross-host redirects
  SO THAT the GitHub App installation token cannot be leaked to an untrusted host.
- AS a platform engineer I WANT mctl-agent to use the latest stable go-github client
  SO THAT future security patches are applied with minimal lag.

## Acceptance criteria (EARS)

- WHEN the GitHub API returns an HTTP redirect to a hostname different from the original,
  THE SYSTEM SHALL reject the redirect, NOT forward the Authorization header, and return
  an error to the caller.
- WHEN mctl-agent creates a PR, THE SYSTEM SHALL use `google/go-github` v85 or later.
- IF a cross-host redirect is rejected, THE SYSTEM SHALL log the event at WARN level
  including the original and redirect URLs (without the token value).
- WHILE mctl-agent operates normally, THE SYSTEM SHALL maintain full PR-creation
  functionality unchanged (no regression in existing routed-alert handling).

## Out of scope

- Changes to PR-creation logic or alert handling.
- Rotation or storage of GitHub App secrets (covered by cwft-rotate-github-token).
- Upgrade of other dependencies (go, chi, sqlite) — separate proposals.
- Adding new GitHub API calls (beyond the current PR-creation functionality).
