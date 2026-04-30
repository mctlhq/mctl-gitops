# Tasks: upgrade-to-2026-4-8

- [ ] 1. Evaluate memory footprint of 2026.4.8 vs 2026.3.14 — DoD: Build the 2026.4.8 image locally; measure pod RSS under representative load; document the delta in a short note. If increase > 50 MB, open a platform approval ticket and block all subsequent tasks until resolved.

- [ ] 2. Review upstream 2026.3.14 → 2026.4.8 changelog for breaking changes and migrations (depends on 1) — DoD: Upstream changelog reviewed; any database or S3 schema migrations identified and noted; no unaddressed breaking changes remain; findings recorded in the ADR draft.

- [ ] 3. Bump `openclaw` to `2026.4.8` in `package.json` and regenerate `package-lock.json` (depends on 2) — DoD: `package.json` shows `"openclaw": "2026.4.8"`; `npm install` completes without errors; no unexpected transitive dependency upgrades introduced.

- [ ] 4. Build and push Docker image tagged `2026.4.8` (depends on 3) — DoD: Image built successfully; pushed to the mctl registry; image digest recorded; no high/critical CVE findings from image scan (other than those already fixed by this upgrade).

- [ ] 5. Roll out to `labs` with canary pause/resume (depends on 4) — DoD: s3-sync canary suspended before apply; ArgoCD applies `labs` helm release with `image.tag: 2026.4.8`; restore-state probe passes within existing timeout; canary resumed and passing; all channels on `labs` reporting healthy.

- [ ] 6. Observe `labs` for one day (depends on 5) — DoD: No alerts fired on `labs`; s3-sync canary passing all cycles; no channel reconnect errors in logs; memory within established bounds.

- [ ] 7. Roll out to `admins` with canary pause/resume (depends on 6) — DoD: Same procedure as task 5 applied to `admins`; restore-state probe passes; canary resumed and passing; all channels healthy on `admins`.

- [ ] 8. Observe `admins` for one day (depends on 7) — DoD: No alerts fired on `admins`; canary passing; no channel errors.

- [ ] 9. Roll out to `ovk` with canary pause/resume (depends on 8) — DoD: Same procedure as task 5 applied to `ovk`; restore-state probe passes; canary resumed and passing; all channels healthy on `ovk`; no customer-visible downtime.

- [ ] 10. Update version record and write ADR (depends on 9) — DoD: `context/current-version.md` updated to `2026.4.8` for all tenants; new ADR file created in `context/decisions/` referencing the four CVEs, the rollout outcome, and the memory-footprint findings from task 1.

## Tests

- [ ] T1. Verify CVE-2026-42422 not reproducible on `labs` post-upgrade: attempt to mint a token for an unapproved role via `device.token.rotate` and confirm the request is rejected with a permission error.
- [ ] T2. Verify CVE-2026-42426 not reproducible on `labs` post-upgrade: attempt to call `node.pair.approve` with only `operator.write` scope and confirm the request is rejected.
- [ ] T3. Verify CVE-2026-42428 not reproducible on `labs` post-upgrade: attempt to install a plugin archive with a tampered checksum and confirm the installation is rejected.
- [ ] T4. Verify CVE-2026-42429 not reproducible on `labs` post-upgrade: confirm that a gateway plugin HTTP auth request with `operator.read` scope does not receive `operator.write` runtime permissions.
- [ ] T5. Confirm restore-state probe passes on all three tenants after rollout (check ArgoCD sync status = Healthy for each namespace).
- [ ] T6. Confirm s3-sync canary passes at least three consecutive cycles on each tenant after the post-rollout resume.
- [ ] T7. Smoke-test WhatsApp (Baileys), Slack, and Telegram channels on `ovk` after rollout to confirm no channel connectivity regression.

## Rollback
If any rollout step fails (probe does not pass, canary fires, channel connectivity lost):

1. ArgoCD: revert the failing tenant's helm release `image.tag` back to `2026.3.14` (the previous known-good tag is pinned in mctl-gitops git history).
2. ArgoCD applies the rollback; wait for the restore-state probe to pass on the reverted pod.
3. Resume the s3-sync canary.
4. Verify all channels healthy on the reverted tenant.
5. Do NOT roll back tenants that have already been confirmed healthy unless they are also showing failures.
6. Open a post-mortem issue, record the failure mode, and revisit the upgrade plan before retrying.

The 2026.3.14 image remains available in the mctl registry throughout the rollout window and must not be pruned until all three tenants are confirmed stable on 2026.4.8.
