# Design: baileys-lockfile-audit

## Current state

Per `context/architecture.md`, the mctl-openclaw workspace is a Node.js + TypeScript project that uses `@whiskeysockets/baileys` (a reverse-engineered WhatsApp Web client) to implement the WhatsApp channel. The package is declared as a dependency in the workspace and its resolved URL and sha512 integrity hash are recorded in `package-lock.json`. All three tenants (`labs`, `admins`, `ovk`) build from the same source tree.

WhatsApp auth tokens and channel sessions are stored in per-tenant S3 buckets per ADR-0002. These are the highest-value credentials in the platform because they allow full WhatsApp session impersonation. The `restore-state` readiness probe depends on successfully restoring this state from S3 at pod startup.

The malicious npm package `lotusbail` (disclosed approximately December 2025, ~56,000 downloads) is a Baileys fork that wraps the legitimate package and exfiltrates auth tokens, message content, contacts, and media to an external socket at runtime. It is designed to be a drop-in substitute for `@whiskeysockets/baileys` and would be indistinguishable in normal operation until exfiltration is detected out-of-band.

The related proposal `baileys-registry-lockdown` adds preventive controls (`.npmrc` scope pin, `npm ci` enforcement). This proposal addresses the pre-condition: confirming the current lockfile state is clean before those controls are applied and before any other rollout proceeds.

## Proposed solution

The audit is a **read-only inspection task** with a defined escalation path. It requires no runtime code changes, no infrastructure changes, and no Kubernetes manifest changes. It can be completed by a single operator in under one hour.

### Step 1: Lockfile inspection

For each of the three tenant build environments, inspect `package-lock.json` (or `npm-shrinkwrap.json` if present) and extract every entry whose name contains `baileys`:

```bash
# Run from the workspace root
grep -r '"baileys\|lotusbail' package-lock.json
# Also check nested dependencies:
node -e "
  const lock = require('./package-lock.json');
  const pkgs = lock.packages || {};
  Object.entries(pkgs)
    .filter(([k]) => /baileys|lotusbail/i.test(k))
    .forEach(([k, v]) => console.log(k, v.resolved, v.integrity));
"
```

For each matching entry, record:
- Package name
- Declared version
- `resolved` URL
- `integrity` sha512 hash

### Step 2: Hash verification against registry

For each entry found in step 1, fetch the official npm registry metadata and compare:

```bash
VERSION=$(node -e "const l=require('./package-lock.json'); \
  console.log(l.packages['node_modules/@whiskeysockets/baileys'].version)")
curl -s "https://registry.npmjs.org/@whiskeysockets/baileys/$VERSION" \
  | node -e "
      const d=[];
      process.stdin.on('data',c=>d.push(c));
      process.stdin.on('end',()=>{
        const meta=JSON.parse(Buffer.concat(d));
        const dist=meta.dist;
        console.log('tarball:', dist.tarball);
        console.log('integrity:', dist.integrity || dist.shasum);
      });"
```

The `integrity` field in `package-lock.json` must match the `integrity` (sha512) or derived `shasum` (sha1, used in older registry entries) published by the official registry for the exact version declared.

### Step 3: Escalation path

**Clean result:** All entries reference `@whiskeysockets/baileys`, all `resolved` URLs start with `https://registry.npmjs.org/@whiskeysockets/baileys/`, and all integrity hashes match the official registry. Produce the audit record (see step 4) and allow other rollouts to proceed.

**Finding — name mismatch (`lotusbail` or other non-official name found):**
- Immediately raise a P0 security incident.
- Halt all active or planned rollouts across all three tenants.
- Do not merge any open gitops PRs.
- Quarantine the build: disable CI image builds until the dependency is removed and the lockfile is regenerated from a clean environment using only `https://registry.npmjs.org/`.
- Rotate all WhatsApp auth tokens stored in S3 for all tenants (assume exfiltration may have already occurred).
- Engage the security response process.

**Finding — URL mismatch or integrity hash mismatch:**
- Raise a security incident (severity to be determined by investigation; start at P1).
- Halt rollouts for the affected tenant.
- Investigate the origin of the non-standard resolution before proceeding.

### Step 4: Audit record

Produce a brief written record (can be a comment on the task ticket or a file in the appropriate location) containing:
- Date and operator who performed the audit
- Tenant(s) audited
- Package name, version, `resolved` URL, and `integrity` hash for each Baileys-related entry
- Pass/fail result per tenant
- Any findings and their resolution status

This design is intentionally minimal: the audit is a verification exercise, not a remediation effort. The remediation controls (scope pin, `npm ci`) live in `baileys-registry-lockdown`. This separation ensures the audit can be completed quickly and independently of any other work.

## Alternatives

**A. Automate the audit via a continuous CI lint step.**
This is the right long-term posture and is partially covered by `baileys-registry-lockdown` task 3. However, a one-time manual audit is needed now to establish the baseline before CI automation is in place. The manual audit is faster to complete (no CI pipeline changes required) and is appropriate as a first step. Automation follows in `baileys-registry-lockdown`.

**B. Rebuild all images from scratch in an isolated environment and compare digests.**
This provides the strongest guarantee (no trust in the existing lockfile at all) but takes significantly longer and requires a clean build environment to be provisioned. For an audit whose primary goal is ruling out `lotusbail`, lockfile inspection plus registry hash verification is sufficient and proportionate. A full rebuild can be triggered as part of the escalation path if a hash mismatch is found.

**C. Use `npm audit` as the audit mechanism.**
`npm audit` checks for known vulnerabilities in the advisory database, not for typosquat substitution. It would not detect `lotusbail` unless `lotusbail` has been added to the npm advisory database. Lockfile-level inspection of resolved URLs and integrity hashes is the correct tool for this specific threat. `npm audit` is complementary, not a substitute.

## Platform impact

### Migrations

None. This proposal involves only inspection and documentation. No files are modified.

### Backward compatibility

Not applicable. No code or configuration is changed.

### Resource impact (especially for `labs`)

None. This audit adds no runtime dependencies and changes no deployed code. Risk for `labs`: NONE.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `lotusbail` or a hash mismatch is found | Escalation path defined above; P0 incident, token rotation, rollout halt. |
| Audit is performed against a stale local copy of the lockfile rather than the version built into the Docker images | Verify the lockfile used in the audit is identical (byte-for-byte) to the one embedded in the currently running Docker image; cross-check using `docker cp` or image layer inspection if needed. |
| Auditor misses a nested dependency that re-introduces `lotusbail` transitively | Step 1 uses a recursive scan of all `packages` entries in the lockfile, not just top-level dependencies; transitive entries are included. |
| Finding triggers a rollout halt that delays the `upgrade-to-2026-5-3` security rollout | Acceptable trade-off: a compromised Baileys dependency is a more immediate threat than the CVEs being patched; the halt is deliberate and bounded. |
