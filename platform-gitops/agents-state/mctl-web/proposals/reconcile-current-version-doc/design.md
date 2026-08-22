# Design: reconcile-current-version-doc

## Current state
`context/current-version.md` states:

```
Version: 4.6.2
Tenant: admins
Last update of this file: 2026-04-25
```

with the instruction "When updating the service — update this file and add an ADR in
`decisions/`." Meanwhile, `mctl_get_service_status` and `mctl_get_service_config` for
admins/mctl-web both currently report `imageTag=7.3.0`, `host=mctl.me`, `port=80`,
`componentType=base-service`, `hasDatabase=false`, with ArgoCD `health=Healthy`,
`syncStatus=Synced`. The gap between "4.6.2" in the doc and "7.3.0" live suggests
either: (a) the doc was simply never updated across one or more deploys, or (b) "4.6.2"
and "7.3.0" refer to different versioning schemes (e.g., app/Nuxt version vs. an
internal build/release tag) that were never reconciled. `context/architecture.md`
separately states the pinned Nuxt version is 4.3.1, which is closer to but still
distinct from "4.6.2" — suggesting the current-version.md file may already have been
tracking something other than the raw Nuxt version.

## Proposed solution
1. **Verify what "7.3.0" actually is.** Using mctl MCP tooling (`mctl_get_service_status`
   / `mctl_get_service_config` against tenant `admins`), confirm the exact field
   semantics of `imageTag` and cross-reference it against the repo's own release/tag
   history (e.g., git tags or CI build metadata) to determine whether "7.3.0" is an
   application release version, a container image tag independent of app version, or
   something else.
2. **Correct the record.** Update `context/current-version.md` with the verified value,
   a clear label of what versioning scheme it represents, and the verification date.
   This edit itself is executed by whoever owns the deploy/update process (out of
   scope for spec-writer, since `context/` is read-only to this agent).
3. **Prevent recurrence with a lightweight process.** Add explicit guidance (in this
   proposal's tasks, and ultimately reflected in the file's own header instruction,
   which already says "update this file" on every service update) that
   `context/current-version.md` is updated as a mandatory last step of every deploy to
   `admins`, not as an occasional/best-effort task. Optionally recommend that the
   analyst/researcher agents perform a periodic sanity check (e.g., once a week) that
   compares the recorded version against a live `mctl_get_service_status` call, and
   flags a discrepancy in the inbox if found, rather than silently trusting the file.

## Alternatives
- **Automate the sync entirely via CI (auto-write current-version.md on every deploy)**:
  more robust long-term, but out of scope here — it requires deploy-pipeline changes
  (`deploy.yml` in this repo) that go beyond a documentation/process proposal and
  should be scoped separately if desired.
- **Do nothing, treat this as a one-off staleness**: rejected — the inbox rationale
  notes this file is the baseline every future researcher/analyst pass depends on;
  leaving it uncorrected risks compounding bad decisions in unrelated future
  proposals.
- **Delete current-version.md and rely solely on live mctl status calls**: rejected —
  a static, human-readable snapshot with a timestamp is still useful for quick context
  and for agents/humans without live MCP access; the fix is to keep it accurate, not
  to remove it.

## Platform impact
- **Migrations:** None. This is a documentation correction; no application, database,
  or infrastructure change.
- **Backward compatibility:** No compatibility concerns — no code or API changes.
- **Resource impact (labs):** None. This proposal does not touch the `labs` tenant or
  any running workload; it is scoped entirely to `admins` tenant record-keeping.
- **Risks and mitigations:**
  - Risk: the "verify what 7.3.0 is" step turns up an unclear or undocumented
    versioning scheme. Mitigation: document whatever is found, even if imperfect —
    an explicitly-labeled uncertainty is still better than a silently stale number.
  - Risk: the process fix (update-on-every-deploy) is not followed because it depends
    on human/agent discipline rather than automation. Mitigation: call out the CI
    automation alternative explicitly as a natural follow-up proposal if the manual
    process proves unreliable in practice.
