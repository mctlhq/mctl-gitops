# Tasks: npm-supply-chain-audit

- [ ] 1. Run a manual audit of `package.json` and `package-lock.json`: confirm absence of forbidden packages (`baileys`, `discord.js-user`), resolved URLs for `@whiskeysockets/baileys` and `discord.js`, run `npm audit --audit-level=high` — DoD: audit results are documented; if issues are found — P0 fix tasks are created; if everything is clean — confirmed in writing
- [ ] 2. Compile and capture the monitoring list: forbidden package names + monitored packages with expected registry origins (depends on 1) — DoD: the file `scripts/npm-supply-chain-config.json` (or equivalent inline in the script) with the up-to-date list is created and committed to the repository
- [ ] 3. Write the CI script `scripts/check-npm-supply-chain.sh` (depends on 2) — DoD: the script checks forbidden package names in `package-lock.json`; checks resolved URLs of monitored packages against the official registry; returns exit 1 with an informative message on a violation; returns exit 0 on a clean result
- [ ] 4. Integrate the script into the CI pipeline with a trigger on changes to `package.json` or `package-lock.json` (depends on 3) — DoD: the CI step is added to the pipeline config; the step is mandatory (cannot be skipped without an explicit override); tested on a mock PR with a forbidden package — the step fails; tested on a clean state — the step passes
- [ ] 5. Add `npm audit --audit-level=high` as a separate mandatory CI step (depends on 4) — DoD: the step is added, fails on a high/critical advisory; the result is artifacted for tracking
- [ ] 6. Document the process: what to do on detection of a poisoned package, how to update the monitoring list (depends on 4) — DoD: a runbook is added to the repository; it includes credential rotation instructions on a confirmed compromise

## Tests
- [ ] T1. In a test branch add `"baileys": "1.0.0"` to `package.json` (without installing) and verify that the CI script detects the name and fails with exit code 1 and a forbidden-package message
- [ ] T2. Build a mock `package-lock.json` with the resolved URL `https://malicious.example.com/baileys-1.0.0.tgz` for `@whiskeysockets/baileys` and verify the script fails noting the wrong URL
- [ ] T3. Run the script against the current `package-lock.json` — expected: exit 0, all resolved URLs match `https://registry.npmjs.org/`
- [ ] T4. Run `npm audit --audit-level=high` on the current `package-lock.json` — expected: no advisories of severity high or above for `@whiskeysockets/baileys` and `discord.js`
- [ ] T5. Verify that the CI step does not run for PRs that do not touch `package.json`/`package-lock.json` (optimisation) — expected: the step is skipped with the corresponding label

## Rollback
The CI script lives only in CI — it does not affect runtime or deploys. Rollback in the sense of "go back to how it was" means removing the CI step from the pipeline config:
1. Revert the commit that added the CI step to the pipeline config
2. Steps 1–2 (audit and monitoring list) can stay — they do not affect runtime

If the audit (task 1) found a poisoned package in the current `package-lock.json`:
1. Immediately replace the package with the official one, rebuild `package-lock.json` via `npm install`
2. Build a new Docker image and deploy to all tenants in the order labs → admins → ovk
3. Treat WhatsApp auth tokens (for Baileys) and Discord tokens as compromised: rotate via the corresponding platform dashboards
4. Notify the security team and record the incident
