# Design: wrangler-interactive-prompt-ci-guard

## Current state
`cloudflare-worker/wrangler.toml` configures the Cloudflare Worker (see
`context/architecture.md` — Cloudflare Worker section). The Worker is deployed
by the `deploy.yml` GitHub Actions workflow, which is the only deploy pipeline
for this service that lives outside mctl-gitops. wrangler is invoked directly in
that workflow without the `CI=true` environment variable or `--no-interactive`
flag. If `name` or `compatibility_date` are absent from `wrangler.toml`,
wrangler 4.88.0+ will block indefinitely waiting for user input, causing the
GitHub Actions job to hang until the runner timeout (typically 6 hours) kills it.
There is currently no pre-merge validation that checks `wrangler.toml` for
required fields.

## Proposed solution

### Layer 1 — Explicit required fields in `wrangler.toml`
Audit `cloudflare-worker/wrangler.toml` and confirm that `name` and
`compatibility_date` are set as top-level keys. If either is absent, add it.
This removes the immediate trigger for interactive prompts and is sufficient to
prevent hangs with wrangler 4.88.0.

Example minimum-viable configuration:
```toml
name = "mctl-web-worker"
compatibility_date = "2026-05-05"
```

### Layer 2 — Non-interactive flag in `deploy.yml`
Add `CI=true` as an environment variable on the wrangler deploy step (or pass
`--no-interactive` as a CLI flag). This is the canonical way to tell wrangler it
is running in automation; any future missing-field scenario will produce an
immediate non-zero exit and a clear error message instead of a hang.

```yaml
- name: Deploy Worker
  env:
    CI: "true"
    # existing secrets...
  run: npx wrangler deploy
```

`CI=true` is preferred over `--no-interactive` because GitHub Actions already
sets this variable by default; making it explicit in the step documents the
intent and is forward-compatible with future wrangler non-interactive modes.

### Layer 3 — Pre-merge `wrangler.toml` lint step
Add a lightweight validation step earlier in `deploy.yml` (or in a separate
`ci.yml` triggered on pull requests) that uses `grep` or a TOML parser to assert
both `name` and `compatibility_date` are present. This acts as a permanent
guardrail against accidental regression.

```yaml
- name: Validate wrangler.toml
  run: |
    grep -E '^name\s*=' cloudflare-worker/wrangler.toml || \
      (echo "ERROR: wrangler.toml missing 'name'" && exit 1)
    grep -E '^compatibility_date\s*=' cloudflare-worker/wrangler.toml || \
      (echo "ERROR: wrangler.toml missing 'compatibility_date'" && exit 1)
```

## Alternatives

### A — Rely solely on `CI=true` without auditing `wrangler.toml`
Setting `CI=true` would convert hangs into fast failures, but the deploy would
still fail on every run if the fields are missing. This is strictly worse than
also fixing the root cause in `wrangler.toml`. Dropped in favour of the two-layer
approach.

### B — Pin wrangler to a version prior to 4.88.0
Locking wrangler at 4.87.x avoids the prompt behaviour now, but defers the
problem and blocks future upgrades. It also leaves the `wrangler.toml` gap
unfixed, meaning the problem re-emerges on any future upgrade. Dropped because
it trades a short-term fix for long-term technical debt.

### C — Use a TOML-aware schema validation tool (e.g., `taplo`)
A dedicated TOML linter could enforce a schema against `wrangler.toml`. This is
more robust but adds a new toolchain dependency and is disproportionate for
validating two keys. Dropped in favour of the simple `grep`-based check for now;
can be revisited if `wrangler.toml` complexity grows.

## Platform impact

### Migrations
No data migrations. The changes are limited to two configuration files
(`wrangler.toml`, `deploy.yml`) and optionally a CI workflow file.

### Backward compatibility
Adding `CI=true` to the deploy step is fully backward-compatible. Explicit
`name` and `compatibility_date` fields in `wrangler.toml` are valid for all
wrangler versions that have been used on this project.

### Resource impact (especially for `labs`)
Zero resource impact. The Cloudflare Worker runs on Cloudflare infrastructure,
not on Kubernetes. No memory, CPU, or pod changes are involved. The `labs`
tenant is unaffected.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| `compatibility_date` set to a date far in the past activates deprecated behaviour flags | Low | Set the date to the current date during the audit; document in a comment |
| `CI=true` suppresses a prompt that would otherwise surface a genuine configuration error | Low | The flag makes wrangler exit non-zero immediately — errors are still visible, just not interactively |
| Lint step produces false negatives (e.g., key inside a `[env.*]` block only) | Low | Scope the grep to the top-level section; add a comment in the workflow explaining the check |
