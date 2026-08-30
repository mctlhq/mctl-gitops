# Pin GitHub SSH host keys in gitops reader (drop accept-new)

## Context
`internal/gitops/reader.go` clones and refreshes the `mctl-gitops` mono-repo
over SSH when an SSH deploy key is configured (`GitOpsSSHKeyPath` /
`GITOPS_SSH_KEY_PATH`). The `refresh()` method builds the SSH command as:

```go
sshCmd := fmt.Sprintf("ssh -i %s -o StrictHostKeyChecking=accept-new", r.sshKeyPath)
```

`accept-new` implements trust-on-first-use (TOFU): the first time the
control plane connects to `github.com` over SSH, it silently accepts and
caches whatever host key the server presents, with no way to verify it
against a known-good value beforehand. If an attacker can intercept that
first connection (a MITM on the pod's egress path, a DNS/routing attack, or
a compromised network step between the control plane and GitHub), they can
present their own host key, get it trusted, and thereafter read or tamper
with all gitops mono-repo content the control plane pulls — tenant
definitions, service manifests, skill catalogs, OpenClaw identity/skill
overrides. Because this data drives cluster-wide reconciliation (ArgoCD)
and authorization decisions (`GetTenantsForUser`), a poisoned known_hosts
entry is a high-value target. This is flagged as P1 in the 2026-08 platform
audit.

The fix is to ship a pinned `known_hosts` file containing GitHub's
published SSH host keys (from `https://api.github.com/meta`), force
`StrictHostKeyChecking=yes`, and point `UserKnownHostsFile` at the pinned
file instead of the default `~/.ssh/known_hosts`. The known_hosts path must
stay overridable so unit tests can point it at a throwaway file (e.g. one
containing a deliberately wrong key) without touching the real pinned data.

## User stories
- AS a platform operator I WANT the gitops reader to verify GitHub's SSH
  host key against a pinned, out-of-band list SO THAT a network-level
  attacker cannot silently poison trust on first clone and intercept
  gitops mono-repo traffic.
- AS a contributor to mctl-api I WANT the known_hosts path to be
  configurable SO THAT I can write a unit test that proves a mismatched
  host key fails closed, without needing real network access to GitHub or
  mutating a shared trust store.
- AS an on-call engineer I WANT a clear, actionable error when the pinned
  host key stops matching what GitHub presents SO THAT I can tell a genuine
  key rotation apart from an active attack instead of the clone silently
  "just working" either way.

## Acceptance criteria (EARS)
- WHEN the gitops `Reader` clones or fetches over SSH (`sshKeyPath != ""`)
  THE SYSTEM SHALL invoke `ssh` with `-o StrictHostKeyChecking=yes` and
  `-o UserKnownHostsFile=<pinned-path>` instead of
  `-o StrictHostKeyChecking=accept-new`.
- WHEN no `knownHostsPath` is explicitly configured THE SYSTEM SHALL use a
  known_hosts file populated with GitHub's currently published SSH host
  keys (RSA, ECDSA, ED25519, per `https://api.github.com/meta`), shipped
  with the binary/image so no runtime fetch from `api.github.com` is
  required at clone time.
- WHEN a `knownHostsPath` is explicitly configured (e.g. via the new
  `GITOPS_SSH_KNOWN_HOSTS_PATH` env var, or the `Reader` field used
  directly in tests) THE SYSTEM SHALL use that file verbatim instead of the
  shipped default.
- IF the SSH server presents a host key that does not match any entry in
  the configured known_hosts file THEN THE SYSTEM SHALL fail the clone/
  fetch with a non-nil error (surfaced through the existing
  `fmt.Errorf("git clone failed: %w\n%s", ...)` / `git fetch failed`
  wrapping) and SHALL NOT write any repository data to `localPath`.
- WHILE SSH auth is not configured (`sshKeyPath == ""`, HTTPS/token or
  anonymous clone) THE SYSTEM SHALL behave exactly as it does today — this
  change is scoped to the SSH code path only.
- WHEN `NewReader` is called without the new parameter (existing call
  sites, if any remain after this change lands) THE SYSTEM SHALL fall back
  to the shipped default known_hosts file so behavior does not silently
  regress to no host-key checking.

## Out of scope
- Rotating or managing the SSH deploy key itself (`GitOpsSSHKeyPath`) —
  unchanged.
- HTTPS/token-based gitops auth path — unchanged, no host-key concept
  applies there.
- Automatically re-fetching `https://api.github.com/meta` at runtime to
  keep the pinned keys fresh; the file is a build-time/deploy-time
  artifact, refreshed via a manual or scheduled update process (see Open
  questions).
- Host-key pinning for any other SSH remote besides `github.com` (the
  gitops repo is GitHub-hosted; there is no evidence in the code of other
  SSH remotes for this reader).

## Open questions
- How should the pinned known_hosts file be kept current if GitHub ever
  rotates its host keys? Two reasonable options: (a) commit the file as a
  static asset and treat updates as a normal code change reviewed like any
  other security-sensitive diff, or (b) add a periodic CI check that diffs
  the committed file against `https://api.github.com/meta` and opens an
  issue on drift. This proposal assumes (a) — static, manually reviewed —
  since it is the minimal change that satisfies the issue's acceptance
  criteria; (b) is a natural follow-up, not blocking.
- Should `GITOPS_SSH_KNOWN_HOSTS_PATH` be documented/wired into the Helm
  chart (`helm/values.yaml`, `helm/templates/deployment.yaml`) as a
  first-class override, or is the shipped-in-image default sufficient for
  production and the env var exists purely for tests/local dev? This
  proposal assumes the latter (env var for override/tests; production uses
  the shipped default) and does not touch the Helm chart, since the
  acceptance criteria only ask for "configurable for tests." Flagging so a
  reviewer can decide if a chart change belongs in this proposal or a
  follow-up.
- The issue does not specify what should happen if the shipped known_hosts
  file is missing or unreadable at startup. This proposal treats that as a
  hard startup/config error for the SSH path (fail closed, consistent with
  "IF...fails closed" in the acceptance criteria) rather than silently
  falling back to `accept-new`.
