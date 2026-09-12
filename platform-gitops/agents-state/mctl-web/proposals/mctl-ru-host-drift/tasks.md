# Tasks: mctl-ru-host-drift

- [ ] 1. Inspect the deployed Cloudflare Worker route configuration (`wrangler.toml`
      and/or live deployment bindings) for `mctl.ai/api/*`, `mctl.ru/*`, `mctl.me/*` and
      their wildcard variants — DoD: documented list of actual route-to-host bindings
      as currently deployed, independent of `mctl_get_service_config`.
- [ ] 2. Perform a live HTTP check against `https://mctl.ru/` and a couple of
      sub-paths (e.g. `/api/github/callback`) and record the response — DoD: recorded
      status codes and `Location` headers (if any) showing whether `mctl.ru` redirects
      to `mctl.ai` or serves content directly.
- [ ] 3. Trace what data source/field populates `mctl_get_service_config`'s reported
      "host" value for `mctl-web`/`admins` — DoD: documented explanation of whether that
      field is derived from live routing or a static/config-time label, and whether it
      is known to be stale.
- [ ] 4. Cross-reference DNS records for `mctl.ru` and `mctl.ai` — DoD: documented DNS
      target for each domain, confirming which currently points at the Worker/Pages
      deployment.
- [ ] 5. Synthesize findings from tasks 1-4 into a root-cause conclusion: "stale
      config-tool label" vs. "genuine routing divergence" (depends on 1, 2, 3, 4) — DoD:
      conclusion documented in this proposal (or a linked follow-up note) with
      supporting evidence cited.
- [ ] 6a. IF root cause is "stale config-tool label": file/track a correction against
      the config-tool's data source and close this proposal with no application/
      infrastructure change (depends on 5) — DoD: correction filed or noted as
      out-of-repo-scope, proposal marked resolved.
- [ ] 6b. IF root cause is "genuine routing divergence": draft a fix plan covering
      Worker route correction, OAuth allow-list audit, and CORS policy audit, staged to
      avoid locking out legitimate users during cutover (depends on 5) — DoD: fix plan
      documented and reviewed before any config change is merged.

## Tests
- [ ] T1. Verify (via live HTTP check) that `mctl.ru/*` returns the documented
      redirect behavior (3xx to `mctl.ai`) — passes if Stage 1 confirms "stale label";
      informs the Stage 2 fix plan if it does not.
- [ ] T2. If Stage 2 is triggered: after the fix, re-run the live HTTP check against
      `mctl.ru/*` and confirm it only redirects and never serves application content
      directly.
- [ ] T3. If Stage 2 is triggered: verify GitHub OAuth login/callback flow completes
      successfully end-to-end against `mctl.ai` after any allow-list change, with no
      regression for existing users.

## Rollback
Stage 1 (investigation) has no rollback concern — it is read-only. If Stage 2 (a
conditional fix) is executed, rollback is a revert of the Worker route/OAuth
allow-list/CORS config change via `wrangler` redeploy of the prior configuration;
because any allow-list change should be staged (both hosts allowed temporarily during
cutover, per the design), reverting is a low-risk, fast operation with no data
migration involved.
