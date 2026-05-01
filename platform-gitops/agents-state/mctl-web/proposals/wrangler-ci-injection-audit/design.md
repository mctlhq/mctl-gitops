# Design: wrangler-ci-injection-audit

## Current state
Per `context/architecture.md`, mctl-web is the only platform service with its deployment pipeline (`deploy.yml`) living inside its own repository rather than in mctl-gitops. The pipeline invokes wrangler — currently at version 4.87.0 — to deploy the Cloudflare Worker. The deploy workflow uses the GitHub Actions runner context, and the `--commit-hash` argument is populated from that context.

CVE-2026-0933 showed that wrangler < 4.59.1 executed `--commit-hash` in a shell without sanitization. The current wrangler version is patched, but the pipeline's input-trust model has never been formally reviewed. GitHub Actions offers two distinct SHA variables for pull-request events: `github.sha` (the merge commit, set by GitHub itself and not influenceable by the PR author) and `github.event.pull_request.head.sha` (the tip of the head branch, set by the PR author and therefore untrusted for fork PRs). If `deploy.yml` uses the latter — or any expression that can be overridden by a fork contributor — it is a potential injection vector even on a patched wrangler, because the shell interpolation risk shifts to the caller rather than the library.

Additionally, GitHub Actions workflow permissions for `pull_request` events from forks are restricted by default (read-only, no secrets), but this configuration must be verified to be explicitly enforced in the workflow file.

## Proposed solution
The audit follows a structured checklist approach rather than a code change, and produces a hardened `deploy.yml` as its output artefact.

**Step 1 — Input source mapping.** Read `deploy.yml` in full and identify every place `--commit-hash` (or any variable feeding it) is set. Classify each source as: (a) GitHub-controlled (trusted), (b) repository-owner-controlled (trusted), or (c) PR-author-controllable (untrusted for fork PRs).

**Step 2 — Permission scope verification.** Confirm that the workflow's `permissions:` block limits fork-triggered runs to `contents: read` (or more restrictive) and that secrets are not exposed to `pull_request` events. If this is not explicitly declared, add the block.

**Step 3 — SHA format validation (defense-in-depth).** Add a validation step before the wrangler invocation that asserts the commit-hash value matches `^[0-9a-f]{40}$` (or `^[0-9a-f]{64}$` for SHA-256). This makes the pipeline safe even if a future wrangler regression reintroduces shell interpolation.

```yaml
# Example guard step to add in deploy.yml
- name: Validate commit hash format
  run: |
    if ! [[ "${{ github.sha }}" =~ ^[0-9a-f]{40}$ ]]; then
      echo "ERROR: commit hash does not match expected SHA-1 format" >&2
      exit 1
    fi
```

**Step 4 — Inline documentation.** Add a comment block in `deploy.yml` near the wrangler invocation that cites CVE-2026-0933, explains why `github.sha` is used instead of `github.event.pull_request.head.sha`, and records the audit date.

**Step 5 — Findings report.** Record the audit outcome (clean or issues found + mitigated) in `context/decisions/0003-wrangler-ci-injection-audit.md` so the finding is traceable.

The approach prioritizes zero functional disruption: if the audit finds the pipeline already uses `github.sha` with correct permissions, the only changes are the validation step and the inline comment. If issues are found, the mitigation is scoped to `deploy.yml` alone.

## Alternatives
1. **Rely solely on wrangler being patched (4.87.0) and take no audit action.** The patched wrangler version eliminates the library-level shell injection, but does not address whether the pipeline's input sourcing is safe against future regressions or other injection patterns. Rejected: the CVE's disclosure surface warrants a documented audit regardless of current patch status.

2. **Migrate deploy.yml to mctl-gitops (centralize the exception).** This would bring the pipeline under the standard security review cycle but requires significant coordination across teams and is outside the scope of a security audit. Rejected for this proposal; may be worth a separate ADR.

3. **Replace `--commit-hash` with no argument (omit it entirely).** Wrangler can deploy without `--commit-hash`; the argument is informational metadata for Cloudflare's deployment dashboard. Dropping it removes the injection surface entirely but loses audit-trail value in the Cloudflare dashboard. Rejected as too broad a change for a targeted audit; kept as a fallback mitigation if the audit finds no safe value source.

## Platform impact
- **Migrations:** No runtime migration. `deploy.yml` changes are CI-only and do not affect the deployed Worker artifact or Nuxt build.
- **Backward compatibility:** Adding a SHA format validation step is additive and will fail fast on malformed input; it does not break any well-formed invocation.
- **Resource impact:** No change to runtime resources. The `labs` tenant is unaffected — this is a CI pipeline change only.
- **Risks and mitigations:** The primary risk is that the validation step uses a regex that is too strict (e.g., does not accommodate SHA-256 hashes if Cloudflare migrates to them). Mitigation: make the regex configurable or accept both 40- and 64-character hex strings from the start. Secondary risk: the audit reveals that secrets are currently exposed to fork PRs — mitigation is to add the `permissions:` block immediately and treat this as a P0 finding requiring same-day resolution.
