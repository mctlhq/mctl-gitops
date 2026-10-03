# Tasks: issue-1416-chore-cloudflare-iac-import-the-tg-seerr

- [ ] 1. Collect the live objects for the three hand-made `type = "mcp"` member
      applications (`tg`, `seerrsense`, `api`) with an
      `Access: Apps and Policies -> Read` token:
      `GET /accounts/6a09f637d20e1f66a8e9d45ebe778058/access/apps?type=mcp`
      and `GET /accounts/.../access/policies`. Record, per application: its id,
      `name`, `domain`, `destinations`, `session_duration`, `allowed_idps`,
      `auto_redirect_to_identity`, `app_launcher_visible`, the three cookie
      flags, `cors_headers`, whether `oauth_configuration` is set, and the id +
      shape of every policy it references. Also record whether
      `5f0102c7-fd88-499c-9b15-9167633d6c63` appears in
      `GET /access/policies`. — DoD: a table of the three application ids and
      every distinct policy id, each marked `reusable` or `app-scoped`. If the
      token is not available to the implementer, the PR body states this as the
      blocking input and names exactly these two API calls; nothing below is
      guessed.
- [ ] 2. Create `infrastructure/cloudflare/account/portal-mcp-apps-adopted.tf`
      with a `locals` block holding the three application ids (and, if reusable,
      the policy ids), commented with the read date and with why literal UUIDs
      are used here rather than a data source (cite `projects-mcp.tf:20-29`).
      (depends on 1) — DoD: every live id in the change appears in exactly one
      place; `tofu fmt -check` clean.
- [ ] 3. In that file add, per application, an `import` block
      (`id = "accounts/${var.account_id}/${local.adopted_app_ids.<name>}"`) above
      a `cloudflare_zero_trust_access_application` resource named
      `portal_member_tg` / `portal_member_seerrsense` / `portal_member_api`,
      with a header comment saying these were created by the dashboard on
      2026-09-10 and are adopted under mctlhq/mctl-gitops#1416, refs #1092.
      (depends on 2) — DoD: three `import` blocks, three resources, resource
      names continuing the `portal_member_<server>` scheme of
      `portal-mcp-apps.tf`.
- [ ] 4. Produce each resource body by the documented procedure, not by hand:
      `tofu plan -generate-config-out=generated.tf` with only the `import` blocks
      present, reduce the generated bodies (drop the explicit `null`s), then
      re-plan — `docs/runbooks/cloudflare-operations.md` step 2 and
      `infrastructure/cloudflare/zones/mctl-me/README.md` "How the configuration
      got here". Record live values, never the siblings' `8760h`, and leave
      `oauth_configuration` unset unless the live object has it.
      (depends on 3) — DoD: re-plan for `account` shows the three applications as
      `will be imported` with no attribute diff.
- [ ] 5. For every policy the read in task 1 marked `reusable`, create
      `infrastructure/cloudflare/account/portal-access-policies.tf` with one
      `cloudflare_zero_trust_access_policy` resource per distinct policy object,
      each with an `import` block
      (`id = "accounts/${var.account_id}/<policy id>"`), bodies generated and
      reduced the same way. Reference each from every application that uses it
      via `policies = [{ id = cloudflare_zero_trust_access_policy.<name>.id,
      precedence = N }]`. (depends on 1, 4) — DoD: the number of policy resources
      equals the number of distinct live policy objects — no object declared
      twice, no object left undeclared; `decision`, `include`, `exclude` and
      `require` byte-identical to the live read.
- [ ] 6. For every policy marked `app-scoped`, describe it inline in its
      application's `policies` list at live values, with a comment stating it has
      no standalone resource because it is not a reusable object and is tracked
      by the application that owns it. (depends on 1, 4) — DoD: no
      `cloudflare_zero_trust_access_policy` resource exists for an app-scoped
      policy, and the plan shows `0 to add`.
- [ ] 7. If task 1 showed `5f0102c7-fd88-499c-9b15-9167633d6c63` is reusable,
      declare it once in `portal-access-policies.tf` and replace the literal id
      at `infrastructure/cloudflare/account/portal-app.tf:64-69` with a reference
      to that resource, keeping the surrounding comment's reasoning and adding
      that the policy is now imported. If it is app-scoped, leave the literal id
      and extend the comment to say why it has no resource of its own.
      (depends on 1, 5) — DoD: the plan for
      `cloudflare_zero_trust_access_application.mcp_portal` reads no change at
      all; if it reads a change, the literal id is restored and the policy is
      deferred to its own issue.
- [ ] 8. Rewrite the header comment at
      `infrastructure/cloudflare/account/portal-mcp-apps.tf:34-36` so it no longer
      says the three siblings stay out of state: say they are adopted in
      `portal-mcp-apps-adopted.tf` under #1416, and cross-reference the policy
      file if one exists. (depends on 3) — DoD: `grep -n "stay out of state"
      infrastructure/cloudflare/account/` returns nothing.
- [ ] 9. Update `infrastructure/cloudflare/account/README.md`: the "Holds one
      application" opening paragraph and the "Imports arrive with" list, so the
      root's own documentation states what it now holds (six portal member
      applications, the portal application, the imported policies) and that
      #1092's Access half landed here. (depends on 3, 5) — DoD: no sentence in
      that README contradicts the `.tf` files in the same directory.
- [ ] 10. Open the PR with a body that states: the three application ids and
      every policy id with the date they were read; whether each policy was
      reusable or app-scoped and therefore which branch of the design was taken;
      any live value that differs from the managed siblings (especially
      `session_duration`) and that it is deliberately recorded, not harmonized;
      that the import apply is a separate owner-dispatched
      `cloudflare-apply.yml` run on `infrastructure/cloudflare/account`; and
      that `cloudflare-drift.yml` will read `DRIFT` for that root between merge
      and that apply. Refs mctlhq/mctl-gitops#1092, closes #1416.
      (depends on 4, 5, 6, 7, 8, 9) — DoD: PR open, `cloudflare-plan` green for
      `account` with the import-only table, no reviewer left to reconstruct where
      a UUID came from.

## Tests

- [ ] T1. `tofu fmt -check` and `tofu validate` in
      `infrastructure/cloudflare/account` — clean. (`tofu init` needs only the
      provider; `validate` needs no credentials.)
- [ ] T2. The PR's `cloudflare-plan` check for
      `infrastructure/cloudflare/account` reads
      `N to import, 0 to add, 0 to change, 0 to destroy`, with `N` = 3
      applications + the number of reusable policy resources declared. The
      workflow's summary table (`import | create | update | destroy`) is the
      artefact to quote in the PR.
- [ ] T3. Every `import` block in the change resolves: the plan lists each
      target as `will be imported` and no target reports "Cannot import
      non-existent remote object" or a 404/1010 from the provider.
- [ ] T4. Exactly one resource exists per live object: grep the change for each
      policy UUID and each application UUID and confirm each appears once in a
      `locals` block (or once in an `import` block) and nowhere else as a literal.
- [ ] T5. No behaviour drift smuggled in: diff the `include` / `exclude` /
      `require` / `decision` of every policy in the change against the task-1
      read, address by address. Any difference is a bug in this PR, not an
      improvement.
- [ ] T6. The three already-managed member applications
      (`portal_member_projects`, `portal_member_alice`, `portal_member_coolify`),
      `projects_mcp` and `mcp_portal` show **no** change lines in the plan — the
      adoption must not disturb resources already in state.
- [ ] T7. Other roots unaffected: `cloudflare-plan` for
      `infrastructure/cloudflare/portal` and the three zone roots still reads
      `No changes` (they share no state with this change, so any movement there
      means something unintended was edited).
- [ ] T8. Post-merge, owner-side: after the environment-approved import-only
      apply on `infrastructure/cloudflare/account`, the run reports
      `N imported, 0 added, 0 changed, 0 destroyed`, and the next
      `cloudflare-drift.yml` run reads `No changes.` for that root — the issue's
      second acceptance box.

## Rollback

Before the import apply, rollback is `git revert` of the merge commit: the
change is description-only, nothing in Cloudflare was touched, and reverting
returns `account` to a root whose plan reads `No changes.` The three applications
go back to being live and unmanaged — the state this issue exists to end, but a
safe one.

After the import apply, the objects are in state and `git revert` alone is the
wrong move: removing the resources from configuration while they are in state
plans a **destroy** of three live Access applications and their policies, which
would take `tg`, `seerrsense` and `api` out of `mcp.mctl.ai` for everyone. The
correct rollback is to drop them from state instead of from Cloudflare — remove
the resource and `import` blocks in a PR together with `removed { from = ...
lifecycle { destroy = false } }` blocks (OpenTofu `removed`, the declarative form
of `state rm`), so the plan reads `0 to destroy`. `cloudflare-apply.yml` refuses a
plan with a destroy unless it is dispatched with `allow_destroy`, which is the
backstop if this is ever attempted carelessly; the `destroy` column in the plan
summary is what a reviewer must check before approving any rollback of this
change.

If instead the import apply reveals an unwanted mutation (a field recorded wrong
that the apply then pushed to Cloudflare), the fix is forward: correct the value
in the `.tf` file to the intended one and dispatch another approved apply, per
`docs/runbooks/cloudflare-operations.md` path B. The pre-change live values
recorded in task 1 are what that correction is measured against, which is why
task 1 writes them down before anything is touched.
