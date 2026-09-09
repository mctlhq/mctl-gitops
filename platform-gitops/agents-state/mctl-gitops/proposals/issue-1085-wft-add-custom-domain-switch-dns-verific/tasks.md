# Tasks: issue-1085-wft-add-custom-domain-switch-dns-verific

All work is in `mctlhq/mctl-gitops`. This is tasks 10-11 of the merged
`issue-262-custom-domains-post-api-v1-domains-alway` proposal; the mctl-api half
(`mctl-api#264`, merge commit `e81215b`) is already shipped, so there is no
cross-repo dependency to wait on.

- [ ] 1. Add `MCTL_API_URL: "http://mctl-api.mctl-api.svc.cluster.local:8080"`
      to `platform-gitops/argo-workflows/config/mctl-platform-config.yaml`,
      with a comment naming the two endpoints
      (`/api/v1/domains/verify`, `/api/v1/domains/{id}`) that consume it.
      — DoD: `yamllint` clean; the five existing keys are byte-for-byte
      unchanged; `kubeconform` passes in `.github/workflows/validate-manifests.yml`.

- [ ] 2. Add `platform-gitops/argo-workflows/secrets/mctl-api-service-token.yaml`
      — an `external-secrets.io/v1beta1` ExternalSecret named
      `mctl-api-service-token` in namespace `argo-workflows`, modelled on
      `secrets/mctl-api-argo-webhook.yaml`: `ClusterSecretStore vault-backend`,
      `refreshInterval: 1h`, `creationPolicy: Owner`, one entry
      `secretKey: MCTL_API_TOKEN` ← `key: platform/mctl-agent/tokens`,
      `property: mctl-api-token`, and the three explicit ESO defaults
      (`conversionStrategy: Default`, `decodingStrategy: None`,
      `metadataPolicy: None`). Header comment must state that this is the same
      Vault value mctl-api validates as `MCTL_AGENT_SERVICE_TOKEN`
      (`bootstrap/templates/mctl-platform/mctl-api-secrets.yaml` lines 39-42),
      that it must never be replicated into a tenant namespace, and the
      rotation ordering.
      — DoD: `kubeconform` passes against the ExternalSecret CRD schema; the
      three ESO default lines are present (their absence is the #789 /
      argo-cd#17694 sync wedge); no Application manifest change is needed
      because `bootstrap/templates/core-infra/argo-workflows-config.yaml`
      recurses this directory.

- [ ] 3. In `wft-add-custom-domain.yaml`, swap the credential (depends on 2):
      delete the `BACKSTAGE_TOKEN` env block (lines 59-81) and add
      `MCTL_API_TOKEN` from `secretKeyRef: {name: mctl-api-service-token, key:
      MCTL_API_TOKEN, optional: true}`, carrying a comment that explains why
      `optional: true` plus a script preflight is used instead of a required
      ref. Add the preflight as the first statement after `set -e`: exit 1 with
      a message naming `mctl-api-service-token` and the `argo-workflows`
      namespace when `MCTL_API_TOKEN` is empty. Drop `BACKSTAGE_URL` (line 90).
      — DoD: no occurrence of `BACKSTAGE` remains in this file;
      `secrets/backstage-workflow-token.yaml` is NOT deleted (still consumed by
      `wft-remove-custom-domain.yaml` lines 62-67).

- [ ] 4. Replace section 2 of the script (lines 153-166) with the verify call
      (depends on 1, 3): build the body with
      `yq -n -o=json '{"team": strenv(TEAM), "service": strenv(SERVICE),
      "domain": strenv(DOMAIN)}'`; `curl -s -o /tmp/verify.json -w '%{http_code}'
      --max-time 30 --retry 3 --retry-connrefused -X POST
      "${MCTL_API_URL}/api/v1/domains/verify"` with the bearer and
      `Content-Type: application/json`; fail on a non-2xx status echoing the
      code and the raw body; then fail when
      `yq -p=json -r '.verified // false'` is not `true`, printing `.reason`,
      `.expected_record`, `.expected_value` and a line noting a CNAME to
      `${AUTO_DOMAIN}` is also accepted. On success echo the `.method`.
      Remove `bind-tools` from the `apk add` line (line 84) — `dig` was its only
      consumer. Keep `AUTO_DOMAIN` (line 89); it is still used in operator
      messages and the commit body.
      — DoD: `grep -c dig` on the file returns 0; a negative verdict exits
      non-zero and the log names the exact TXT record to create; the platform-
      domain rejection block (lines 124-150) is untouched in the diff.

- [ ] 5. Replace section 10, the Backstage callback (lines 315-353), with the
      mctl-api status PATCH (depends on 3, 4): `GET
      "${MCTL_API_URL}/api/v1/domains?team=${TEAM}&service=${SERVICE}"` with
      `-sSf --max-time 30 --retry 3 --retry-connrefused`, resolve the id with
      `yq -p=json -r '.domains[] | select(.domain == strenv(DOMAIN)) | .id'`,
      normalise `"null"` to empty and hard-fail when empty, then
      `curl -sSf -X PATCH ... --data-binary '{"status":"active"}'
      "${MCTL_API_URL}/api/v1/domains/${DOMAIN_ID}"`. Drop the already-`active`
      escape hatch (lines 337-347) — `SetStatus` to the current value is
      idempotent. The block must remain after `fi  # ALREADY_PRESENT` (line
      313) so the reconcile-on-rerun path still reports status.
      — DoD: a rerun over an already-added domain skips the git edit and still
      PATCHes `active`; the `.domains[] | select(...)` shape and the `"null"`
      normalisation match the removed lines 333-334.

- [ ] 6. Add the failure callback (depends on 5): set `spec.onExit:
      report-failure` and add a `report-failure` script template using
      `alpine:3.19`, the same `envFrom: configMapRef: mctl-platform-config`,
      the same `MCTL_API_TOKEN` `secretKeyRef`, and env `PARAM_TEAM`,
      `PARAM_SERVICE`, `PARAM_DOMAIN`, `WORKFLOW_STATUS: "{{workflow.status}}"`,
      `WORKFLOW_FAILURES: "{{workflow.failures}}"`. Return immediately when
      `WORKFLOW_STATUS` is `Succeeded`; otherwise resolve the id as in task 5
      and PATCH `{"status":"failed","error":"<status>: <failures>"}`. The
      handler must NOT use `set -e` and must `exit 0` on every path, including
      a missing token, a missing row, and an mctl-api outage.
      — DoD: forcing a failure in the validation step still surfaces the
      original error as the workflow's failure message, not an exit-handler
      error; the exit handler's own step reports Succeeded even when it could
      not reach mctl-api.

- [ ] 7. Update the `workflows.argoproj.io/description` annotation (lines 6-12)
      (depends on 4, 5): step 2 becomes DNS verification via mctl-api's TXT
      challenge with a CNAME fallback, step 5 becomes the mctl-api `active`
      callback. Also correct the stale in-file comments that assert the add and
      remove templates are kept "in step" (lines 110-115) and the
      tenant-namespace bridge narrative, noting that add now talks to mctl-api
      while remove still talks to Backstage.
      — DoD: no sentence in the file describes behaviour the script no longer
      has.

- [ ] 8. Update the skill copy that still tells users to create a CNAME
      (depends on 4): `platform-gitops/mcp/mctl-platform/SKILL.md` lines
      100-111, `platform-gitops/platform-skills/catalog/mctl-platform/references/tools.md`
      lines 42-59, and `.github/skills/mctl-platform/SKILL.md` — describe the
      TXT challenge at `_mctl-challenge.<domain>` as primary with the CNAME
      fast path retained. Leave the platform-domain paragraph verbatim.
      — DoD: the three copies stay identical to each other; no change to the
      tool names or the platform-domain wording.

## Tests

- [ ] T1. `yamllint .` and the full `.github/workflows/validate-manifests.yml`
      job (helm lint + kubeconform over the changed manifests) pass locally on
      the branch.
- [ ] T2. Shell syntax check of both script bodies: extract them and run
      `sh -n` (and `shellcheck -s sh` if available) — the added `yq`/`curl`
      pipelines and the new `if`/`fi` nesting must not break the existing
      `if [ "$ALREADY_PRESENT" != "true" ]; then ... fi` span across lines
      223-313.
- [ ] T3. Preflight test: submit the workflow into a namespace where
      `mctl-api-service-token` is absent. The run must fail on the first step
      with the message naming the secret and the `argo-workflows` namespace —
      not `CreateContainerConfigError`, and not a 401 several steps later.
- [ ] T4. Happy path against a real Cloudflare-proxied hostname: register the
      domain via `mctl_add_custom_domain`, create the returned TXT record, run
      the workflow. Expect `verified: true` with `method` reporting the TXT
      challenge, the ingress commit on `main`, and
      `GET /api/v1/domains?team=&service=` showing the row as `active`. This is
      the exact case `dig +short CNAME` fails today.
- [ ] T5. Negative-verdict path: run against a domain with no TXT record.
      Expect a non-zero exit, the log naming `_mctl-challenge.<domain>` and
      `mctl-domain-verification=<token>`, no commit on `main`, and the registry
      row moved to `failed` by the exit handler.
- [ ] T6. CNAME fast-path regression: an unproxied hostname with a plain CNAME
      to `{team}-{service}.mctl.ai` and no TXT record still verifies, so
      existing correct setups are not broken.
- [ ] T7. Reconcile-on-rerun: run the workflow twice for the same domain. The
      second run logs the `ALREADY_PRESENT` branch, makes no commit, and still
      PATCHes `active` (a no-op on an already-active row, not an error).
- [ ] T8. Exit-handler isolation: force a failure in the domain-format
      validation (a domain that has no registry row at all). The exit handler
      must exit 0 and the workflow's reported failure must remain the
      validation error.
- [ ] T9. Non-2xx handling: point `MCTL_API_URL` at an endpoint returning 500.
      The step must fail with the status code and body echoed, and must not be
      reported as "DNS not verified".
- [ ] T10. `wft-remove-custom-domain.yaml` regression: remove a custom domain
      after this lands. It must still work, proving the
      `backstage-workflow-token` ExternalSecret was not removed.

## Rollback

Single-commit revert. The change touches four files
(`config/mctl-platform-config.yaml`, the new
`secrets/mctl-api-service-token.yaml`, `cluster-templates/wft-add-custom-domain.yaml`,
and the three skill copies), all under paths ArgoCD reconciles automatically, so
`git revert <sha>` on `main` restores the `dig +short CNAME` step, the
`BACKSTAGE_TOKEN` mount and the Backstage activate callback within one sync.

Two things make the revert safe and independent of mctl-api:

- No mctl-api rollback is required. `POST /api/v1/domains/verify` and
  `PATCH /api/v1/domains/{id}` simply stop being called; rows already moved to
  `active` keep that status, and no schema or data changes are made by this
  repo.
- Reverting leaves the reverted-to `dig` path broken for Cloudflare-proxied
  domains — that is the pre-existing defect, not a new one. Custom domains for
  unproxied hostnames continue to work on either side of the revert.

Two follow-ups after a revert: rows left `pending` by an in-flight run can be
moved with a direct `PATCH /api/v1/domains/{id}` using the service token, and
the orphaned `mctl-api-service-token` ExternalSecret is harmless if left in
place (it grants nothing that is not already in `argo-workflows`) but should be
deleted with the same revert for tidiness.

Partial rollback: if only the exit handler misbehaves, drop `spec.onExit` and
the `report-failure` template while keeping tasks 1-5. Verification and the
`active` callback are independent of it.
