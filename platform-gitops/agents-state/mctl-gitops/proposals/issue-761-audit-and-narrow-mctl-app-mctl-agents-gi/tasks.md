# Tasks: issue-761-audit-and-narrow-mctl-app-mctl-agents-gi

- [ ] 1. Write `docs/runbooks/github-app-scope-audit.md` containing: the
      two apps' current state (app_id, installation id,
      `repository_selection`, permissions) transcribed from the issue's
      2026-08-08 `gh api orgs/mctlhq/installations` snapshot; the full
      in-repo consumer list for `platform/github-app` (mctl-app) and
      `platform/github-app-agents` (mctl-agents) with file citations, as
      established in design.md; the recommended narrowed repo list per
      app (12-repo `agents-state/` roster for `mctl-agents`; deploy-wired
      repos + `mctl-gitops` for `mctl-app`, marked provisional); and the
      "NOT YET VERIFIED" section with the exact `gh api` / `gh secret
      list` / grep commands needed to complete the cross-repo sweep —
      DoD: file exists, every claim in it cites a real path in this repo
      or is explicitly marked as unverifiable from this clone.
- [ ] 2. In `cwft-rotate-github-token.yaml`, rename the first `TARGETS`
      entry's `"label"` from `"mctl-agent"` to `"mctl-app"` and update the
      header `annotations.workflows.argoproj.io/description` target list
      line to say `mctl-app (App id 2902192)` instead of `mctl-agent (App
      id 2902192)`. Do not touch `creds_path`, `dest_path`, `dest_key`,
      `es_namespace`, or `es_name` (depends on 1, so the runbook and the
      code agree on the naming) — DoD: `git diff` on this file shows only
      the label string and the description comment changed; `dest_path`
      stays `platform/mctl-agent/tokens` (renaming the Vault path itself
      is out of scope — it would require migrating the
      `admins-mctl-agent-base-service` ExternalSecret in lockstep, which
      this proposal does not do) and `es_name` stays
      `admins-mctl-agent-base-service`.
- [ ] 3. Add a short policy note to `docs/runbooks/github-app-scope-audit.md`
      (part of task 1's file, written as its own subsection) stating the
      per-team Vault PAT pattern from `.github/workflows/build-image.yaml`
      (Tier 1, tried before the App-token Tier 2 fallback) is the required
      shape for any NEW single-repo automation consumer, instead of adding
      a new caller to either shared app — DoD: subsection exists and
      references `build-image.yaml` by path.
- [ ] 4. Open a tracking checklist (either a new GitHub issue linked from
      the runbook, or a `## Manual follow-up` section in the runbook
      itself — implementer's choice, runbook section is simpler and keeps
      it in one place) listing the concrete manual steps for the org owner:
      (a) run the cross-repo sweep commands from task 1 and update the
      "NOT YET VERIFIED" section with real findings; (b) narrow
      `mctl-agents`'s installation to the confirmed repo list via GitHub's
      App settings UI; (c) smoke-test the agents pipeline (a
      `mctl_trigger_single_service` or single-proposal
      `mctl_trigger_implementer` run) against a repo still on the list and
      confirm PR authoring still works; (d) narrow `mctl-app`'s
      installation the same way, after separately confirming
      Backstage/ArgoCD SSO do not need org-wide visibility (the open
      question in requirements.md); (e) smoke-test a
      `mctl_deploy_service` call and a Backstage/ArgoCD login — DoD:
      checklist committed, each item is independently actionable by a
      human without needing to re-read this whole proposal.
- [ ] 5. Cross-link the new runbook from `CLAUDE.md`'s "Key Paths" or
      "Common Operations" section (one line, e.g. under a new "Security /
      Access Audits" bullet) so the next person auditing app scope finds
      it without re-deriving this work — DoD: `CLAUDE.md` has one new line
      pointing at `docs/runbooks/github-app-scope-audit.md`.

## Tests

- [ ] T1. `helm lint` is not applicable (no chart changes); instead, after
      task 2, diff-review that `cwft-rotate-github-token.yaml` still
      parses as valid YAML (`python3 -c "import yaml,sys;
      yaml.safe_load(open('platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml'))"`)
      and that the embedded Python `TARGETS` list literal is still valid
      Python (`python3 -c "import ast; ast.parse(open(...).read())"` is
      unnecessary since it's embedded in a YAML block scalar — visually
      confirm the trailing comma/quote structure around the renamed label
      is intact).
- [ ] T2. After ArgoCD syncs the CronWorkflow change (~3 min per this
      repo's `CLAUDE.md` convention), let the next scheduled
      `rotate-github-app-tokens` tick run and confirm via
      `mctl_get_workflow_status` / `mctl_get_workflow_logs` that both
      `[mctl-app]` (renamed) and `[mctl-agents]` labels appear in the
      success log lines, and that `admins-mctl-agent-base-service` and
      `mctl-agents-secrets` ExternalSecrets both still force-synced
      (unchanged Vault paths mean this should be a no-op diff from
      today's behavior, just relabeled).
- [ ] T3. Once the org owner narrows `mctl-agents` (manual follow-up task
      4b), run `mctl_trigger_single_service` for one repo still on the
      narrowed list and confirm the resulting proposal/PR flow completes
      normally — this is the real regression signal that narrowing didn't
      break the pipeline.
- [ ] T4. Once `mctl-app` is narrowed (manual follow-up task 4d), verify a
      Backstage login and an ArgoCD SSO login both still succeed, and run
      one `mctl_deploy_service action=deploy` call end to end.

## Rollback

- Tasks 1, 3, 5 (documentation only): revert the commit(s). No runtime
  effect to unwind.
- Task 2 (rotation label rename): revert the commit; the CronWorkflow
  picks up the reverted template on the next ArgoCD sync (~3 min), and
  since no Vault path or secret name changed, there is no data to migrate
  back — the next rotation tick simply logs `[mctl-agent]` again.
- The manual GitHub App narrowing (task 4b/4d, executed by a human outside
  this proposal's automation) is reversible directly in GitHub's App
  settings UI: switch `repository_selection` back to "All repositories."
  If a consumer breaks after narrowing and the fix isn't an immediate
  "add the missing repo to the list," the fastest mitigation is that
  UI revert, not a gitops change — nothing in this repo needs to change
  to undo the GitHub-side scope.
