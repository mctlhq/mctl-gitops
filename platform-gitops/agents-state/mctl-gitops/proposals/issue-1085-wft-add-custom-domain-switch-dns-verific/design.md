# Design: issue-1085-wft-add-custom-domain-switch-dns-verific

## Current state

### The template

`platform-gitops/argo-workflows/cluster-templates/wft-add-custom-domain.yaml`
is a `ClusterWorkflowTemplate` whose entire body is one `script` step
(`do-add-domain`, line 31) running `alpine:3.19` with
`apk add --no-cache curl git openssh-client bind-tools yq` (line 84). It reads
platform configuration through `envFrom: configMapRef: mctl-platform-config`
(lines 43-45) and injects its three workflow parameters as `PARAM_TEAM`,
`PARAM_SERVICE`, `PARAM_DOMAIN` env vars rather than interpolating
`{{inputs.parameters.*}}` into the shell body — deliberate shell-injection
hardening, documented at lines 47-52.

Ten numbered sections follow:

1. Domain/team/service validation (lines 92-123), including `reject_multiline`
   and the anchored regexes.
2. Platform-domain rejection (lines 124-150) — the guard the issue explicitly
   marks off-limits.
3. **DNS verification (lines 153-166)** — the defect:
   ```sh
   CNAME_TARGET=$(dig +short CNAME "${DOMAIN}" | sed 's/\.$//' | head -1)
   if [ -z "$CNAME_TARGET" ]; then ... exit 1; fi
   if [ "$CNAME_TARGET" != "$AUTO_DOMAIN" ]; then ... exit 1; fi
   ```
   where `AUTO_DOMAIN="${TEAM}-${SERVICE}.${PLATFORM_DOMAIN}"` (line 89).
4. SSH setup with pinned GitHub host keys (lines 168-192).
5. Shallow clone of the gitops repo (lines 194-198).
6. Service existence check on
   `platform-gitops/services/${TEAM}/${SERVICE}/values.yaml` (lines 200-205).
7. `ALREADY_PRESENT` detection with `grep -qFx` (lines 207-221) — deliberately
   *not* a full no-op, so a rerun after "push succeeded, callback failed" still
   reconciles the record (comment at lines 208-211).
8. `ingress.hosts` / `ingress.tls` edits and the single
   `custom-domain-cert.yaml` Certificate (lines 225-281).
9. Commit and a five-attempt push loop that hard-fails rather than reporting
   success without the ingress commit (lines 283-311).
10. **Backstage callback (lines 315-353)** — `GET
    ${BACKSTAGE_URL}/api/custom-domains/domains?team=&service=`, `yq -p=json`
    to select the row whose `.domain` matches, then `POST .../{id}/activate`,
    with an already-`active` escape hatch.

The Backstage credential is `BACKSTAGE_TOKEN` (lines 59-81), mounted
`optional: true` with a long comment explaining that the secret does not exist
in tenant namespaces on purpose.

### The surrounding wiring

- `platform-gitops/argo-workflows/config/mctl-platform-config.yaml` holds
  exactly four keys: `GITOPS_ORG`, `GITOPS_REPO`, `PLATFORM_DOMAIN`,
  `PLATFORM_DOMAIN_ALT`, `CONTAINER_REGISTRY`. **There is no `MCTL_API_URL`.**
- `platform-gitops/argo-workflows/secrets/` contains five ExternalSecrets;
  `mctl-api-argo-webhook.yaml` is the closest precedent — `ClusterSecretStore
  vault-backend`, `refreshInterval: 1h`, `creationPolicy: Owner`, a single
  `remoteRef` under `platform/mctl-api/...`. **No secret in this namespace
  carries an mctl-api bearer token today.**
- The in-cluster mctl-api address is used exactly once in the repo:
  `http://mctl-api.mctl-api.svc.cluster.local:8080` in
  `cluster-templates/cwft-global-workflow-completion-hook.yaml` line 98.
- The service-principal credential mctl-api validates is
  `MCTL_AGENT_SERVICE_TOKEN`, sourced from Vault `platform/mctl-agent/tokens`
  property `mctl-api-token`
  (`bootstrap/templates/mctl-platform/mctl-api-secrets.yaml` lines 39-42).
- `config/networkpolicy.yaml` in `argo-workflows` declares `policyTypes:
  [Ingress]` only, so pod egress out of the namespace is unrestricted from this
  side. On the receiving side,
  `bootstrap/templates/mctl-platform/mctl-api-netpol.yaml` lines 32-35 already
  admit `namespaceSelector: kubernetes.io/metadata.name: argo-workflows` with
  the comment "Workflows call back into mctl-api to report operation status" —
  the network path this change depends on is open in both directions today.
- The house pattern for a workflow calling an internal API with a bearer token
  is `cwft-mctl-agents-run.yaml` lines 800-805 and 897-901: an `optional: true`
  `secretKeyRef` plus `-H "Authorization: Bearer ${TOKEN}"`. None of the
  existing API curls use `--retry`; `--retry` appears only on binary downloads
  (`wft-rollback-service.yaml` line 59, `tpl-git-commit.yaml` lines 288/491).
- `wft-remove-custom-domain.yaml` (lines 56-67) mounts the same
  `backstage-workflow-token` and still calls Backstage. It is untouched here.

### The already-approved spec

`platform-gitops/agents-state/mctl-api/proposals/issue-262-custom-domains-post-api-v1-domains-alway/`
(`.status.yaml`: `merged`, PR `mctl-api#264`, merge commit `e81215b`) defines
this work as tasks 10 and 11 of that proposal (`tasks.md` lines 68-81), with the
contract in `design.md` sections 3-5: `POST /api/v1/domains/verify` body
`{team, service, domain}`, response `{verified, method, reason, expected_record,
expected_value}` returned with `200` even on a negative verdict, and `PATCH
/api/v1/domains/{id}` accepting `{status, error}` restricted to
`user.IsService()`.

## Proposed solution

Three files change; one new file is added. Nothing outside
`platform-gitops/argo-workflows/` is touched.

### 1. `config/mctl-platform-config.yaml` — add `MCTL_API_URL`

```yaml
  # In-cluster base URL for mctl-api. wft-add-custom-domain calls
  # /api/v1/domains/verify and /api/v1/domains/{id} through this.
  MCTL_API_URL: "http://mctl-api.mctl-api.svc.cluster.local:8080"
```

Additive to a ConfigMap the template already consumes via `envFrom`, so no new
mount and no change to the pod spec's config wiring. Twenty-one templates read
this ConfigMap; adding a key changes no existing value and no other template's
behaviour. The ConfigMap carries emberstack reflector annotations (lines 9-12,
`reflection-auto-enabled: "true"` with an empty namespace list), which is how it
already reaches tenant namespaces, so the key propagates the same way
`PLATFORM_DOMAIN` does.

The FQDN form is used to match
`cwft-global-workflow-completion-hook.yaml` line 98, the only other in-cluster
mctl-api call from a workflow. `bootstrap/templates/mctl-platform/mctl-agent.yaml`
line 34 uses the short form `http://mctl-api.mctl-api.svc:8080` for the same
service; either resolves, and the longer one is preferred here only for
consistency inside `argo-workflows/`.

### 2. New `secrets/mctl-api-service-token.yaml`

An ExternalSecret in `argo-workflows`, modelled line-for-line on
`mctl-api-argo-webhook.yaml`:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: mctl-api-service-token
  namespace: argo-workflows
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-backend
  target:
    name: mctl-api-service-token
    creationPolicy: Owner
  data:
    - secretKey: MCTL_API_TOKEN
      remoteRef:
        key: platform/mctl-agent/tokens
        property: mctl-api-token
        # ESO's own CRD defaults, spelled out on purpose — omitting them
        # wedges the Application under ServerSideApply +
        # RespectIgnoreDifferences (#789, argo-cd#17694). Every ExternalSecret
        # in this namespace carries the same three lines.
        conversionStrategy: Default
        decodingStrategy: None
        metadataPolicy: None
```

No Application change is needed: `bootstrap/templates/core-infra/argo-workflows-config.yaml`
syncs `path: platform-gitops/argo-workflows` with `directory.recurse: true`, so
a new file under `secrets/` is picked up automatically.

Same Vault path mctl-api reads as `MCTL_AGENT_SERVICE_TOKEN`, so the workflow
authenticates as the `mctl-agent` service principal — the only principal
`PATCH /api/v1/domains/{id}` admits. It lives in `argo-workflows`, never
replicated into a tenant namespace, for the same reason
`backstage-workflow-token` never was (comment at
`wft-add-custom-domain.yaml` lines 68-81): a tenant service account can read
secrets in its own namespace and would inherit a platform-tier credential.

### 3. `wft-add-custom-domain.yaml` — the substance

**Credential swap.** The `BACKSTAGE_TOKEN` env block (lines 59-81) is replaced
by:

```yaml
          - name: MCTL_API_TOKEN
            valueFrom:
              secretKeyRef:
                name: mctl-api-service-token
                key: MCTL_API_TOKEN
                optional: true
```

`optional: true` is retained deliberately. A required `secretKeyRef` for a
secret absent from the namespace produces `CreateContainerConfigError` — the
pod never starts, no logs, no message naming the cause. Instead the script
opens with an explicit preflight:

```sh
if [ -z "${MCTL_API_TOKEN}" ]; then
  echo "❌ mctl-api service token not mounted (secret mctl-api-service-token)." >&2
  echo "   This template must be submitted into the argo-workflows namespace." >&2
  exit 1
fi
```

Fail-closed, with a diagnosis. This matters because the template's own comment
and the mctl-api design disagree about which namespace this runs in today.

**Section 2 rewrite.** `dig` is replaced by:

```sh
VERIFY_BODY=$(TEAM="$TEAM" SERVICE="$SERVICE" yq -n -o=json \
  '{"team": strenv(TEAM), "service": strenv(SERVICE), "domain": strenv(DOMAIN)}')
HTTP_CODE=$(curl -s -o /tmp/verify.json -w '%{http_code}' \
  --max-time 30 --retry 3 --retry-connrefused \
  -X POST "${MCTL_API_URL}/api/v1/domains/verify" \
  -H "Authorization: Bearer ${MCTL_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-binary "$VERIFY_BODY")
```

Notes on why each part is what it is:

- The body is built by `yq -n -o=json` from `strenv()`, not by string-pasting
  shell variables into a JSON literal. All three values are already regex-
  validated at lines 105-123, so this is defence in depth, but it is the same
  posture the rest of the template took when it moved every `yq` argument
  through `strenv`.
- `-w '%{http_code}'` instead of `-sSf`: the whole point of this endpoint is
  that a negative verdict arrives as `200` with a body worth printing. `-f`
  would discard bodies on error statuses, which is exactly the information the
  operator needs. Non-2xx is still a hard failure, but with the status and the
  raw body echoed.
- `--retry 3 --retry-connrefused --max-time 30` because this step now depends
  on another service being up, where before it depended only on a resolver.

Then the verdict:

```sh
VERIFIED=$(yq -p=json -r '.verified // false' /tmp/verify.json)
if [ "$VERIFIED" != "true" ]; then
  echo "❌ DNS verification failed for ${DOMAIN}"
  echo "   reason:         $(yq -p=json -r '.reason // "(none)"' /tmp/verify.json)"
  echo "   expected record: $(yq -p=json -r '.expected_record // "(none)"' /tmp/verify.json)"
  echo "   expected value:  $(yq -p=json -r '.expected_value // "(none)"' /tmp/verify.json)"
  echo "   (a CNAME to ${AUTO_DOMAIN} is also accepted when the name is not proxied)"
  exit 1
fi
echo "✅ DNS verified (method: $(yq -p=json -r '.method // "unknown"' /tmp/verify.json))"
```

A `yq` parse failure on `/tmp/verify.json` propagates under `set -e` with yq's
own stderr rather than collapsing into a bogus "not verified" — the same
reasoning already written at lines 330-333 for the Backstage lookup.

`AUTO_DOMAIN` stays: it is still the CNAME target quoted in operator messages
and in the commit body (lines 286-288), even though the workflow no longer
computes the verdict from it. `bind-tools` drops out of the `apk add` line,
since `dig` was its only consumer.

**Section 10 rewrite.** The Backstage list-and-activate block becomes an
mctl-api list-and-PATCH block with the same control flow:

```sh
DOMAIN_DATA=$(curl -sSf --max-time 30 --retry 3 --retry-connrefused \
  -H "Authorization: Bearer ${MCTL_API_TOKEN}" \
  "${MCTL_API_URL}/api/v1/domains?team=${TEAM}&service=${SERVICE}")
DOMAIN_ID=$(echo "$DOMAIN_DATA" | yq -p=json -r '.domains[] | select(.domain == strenv(DOMAIN)) | .id' -)
[ "$DOMAIN_ID" = "null" ] && DOMAIN_ID=""
if [ -z "$DOMAIN_ID" ]; then
  echo "❌ ${DOMAIN} is not registered in the mctl-api domains registry" >&2
  exit 1
fi
curl -sSf --max-time 30 -X PATCH \
  -H "Authorization: Bearer ${MCTL_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-binary '{"status":"active"}' \
  "${MCTL_API_URL}/api/v1/domains/${DOMAIN_ID}"
```

The `.domains[] | select(.domain == ...) | .id` shape and the
`"null"`-to-empty normalisation are lifted verbatim from lines 333-334; the
`{"domains":[...]}` envelope is preserved by mctl-api#264 per that proposal's
"Backward compatibility" note. The already-`active` escape hatch at lines
337-347 is no longer needed: `SetStatus` to the value a row already holds is
idempotent, so a rerun after a transient failure simply succeeds. This block
still sits *after* the `fi # ALREADY_PRESENT` at line 313, so the reconcile
path keeps working.

**Exit handler for the failure callback.** `active` is written inline; `failed`
cannot be, because the interesting failures are the ones that abort the script.
A second template is added and referenced from `spec.onExit`:

```yaml
spec:
  entrypoint: add-domain-pipeline
  onExit: report-failure
```

`report-failure` is a small `alpine:3.19` script with the same `envFrom`, the
same `MCTL_API_TOKEN` mount, and `WORKFLOW_STATUS: "{{workflow.status}}"` /
`WORKFLOW_FAILURES: "{{workflow.failures}}"`. It returns immediately when
`WORKFLOW_STATUS` is `Succeeded`; otherwise it resolves the id the same way and
PATCHes `{"status":"failed","error":"<phase>: <failures>"}`.

The handler is wrapped so that **every** path exits `0`:

```sh
set -u   # deliberately NOT set -e
...
} || true
exit 0
```

A workflow that failed validation at line 106 has no registry row, an mctl-api
outage during an unrelated failure must not be reported as the failure, and an
exit handler that itself fails only replaces a precise error message with a
vaguer one. The handler's job is best-effort reporting, not enforcement.

**Description block.** The `workflows.argoproj.io/description` annotation
(lines 6-12) is updated: step 2 becomes "DNS verify via mctl-api TXT challenge
(CNAME fallback)" and step 5 becomes "Callback to mctl-api to mark the domain
active".

### 4. Skill documentation

Three copies of the platform skill describe `mctl_verify_domain` as "Check
CNAME config" and instruct the user to create a CNAME:
`platform-gitops/mcp/mctl-platform/SKILL.md` lines 100-111,
`platform-gitops/platform-skills/catalog/mctl-platform/references/tools.md`
lines 42-59, and `.github/skills/mctl-platform/SKILL.md`. Once verification is
TXT-first, that instruction is wrong for exactly the proxied case this change
exists to fix. The wording is updated to name the TXT challenge with the CNAME
kept as a fast path. The platform-domain paragraph in the same sections is left
verbatim — it was settled in `mctl-gitops#1080`.

### 5. JSON handling: `yq` over `jq`

The repo has two conventions. The mctl-agents templates install `jq` and build
request bodies with `jq -nc --arg` (`cwft-mctl-agents-run.yaml` line 826, with
a comment stating jq is mandatory so quotes and newlines cannot break the
body). Both custom-domain templates install `yq` and parse with
`yq -p=json ... strenv(...)`. This change stays with `yq`: it is already in the
`apk add` line for the git edits, `yq -n -o=json` with `strenv()` gives the same
injection-safe encoding jq is used for elsewhere, and adding a second JSON tool
to this image for two calls is not worth the divergence.

### 6. What is deliberately *not* changed

- Lines 124-150, the platform-domain rejection. Untouched, per the issue.
- `secrets/backstage-workflow-token.yaml`. The issue says "the old
  `backstage-workflow-token` mount can be dropped" — the *mount*, in this one
  template. The ExternalSecret must stay: `wft-remove-custom-domain.yaml` lines
  62-67 still consume it, and deleting the secret would break domain removal.
- `wft-remove-custom-domain.yaml` itself.

## Alternatives

**A. Keep `dig` and add a TXT lookup in the shell
(`dig +short TXT _mctl-challenge.$DOMAIN`).** The smallest possible diff and no
new credential. Rejected: the workflow would have to learn the per-row
verification token, which only mctl-api's registry holds, so it needs an
authenticated API call regardless — at which point the DNS logic is duplicated
in shell and in Go, with two places to keep in step and only one of them
covered by tests (`internal/domains/verify_test.go`). It also leaves the
workflow unable to write the `active`/`failed` status back, so half the issue's
ask goes unaddressed.

**B. Split verification into its own Argo DAG step with a proper
`retryStrategy`, rather than a `curl --retry` inside the existing script.**
Architecturally cleaner and gives Argo-native backoff. Rejected for now: the
template is one monolithic script by design — sections 3-9 share the cloned
repo, the SSH identity and shell state, and splitting only step 2 out means
passing `AUTO_DOMAIN` and the verdict across an artifact boundary for no
behavioural gain. `curl --retry 3 --retry-connrefused` covers the transient
case that matters. Worth revisiting if the template is ever decomposed.

**C. Have mctl-api perform the whole verify-and-activate transition itself,
with the workflow only reporting the git push result.** Fewer round trips and
one owner for the state machine. Rejected: it inverts the existing control flow
(mctl-api submits the workflow, then would have to poll it), and `mctl-api#264`
already shipped the opposite contract — an explicit `PATCH` from the service
principal. Changing that now means another mctl-api PR, which is exactly the
cross-repo stall this issue exists to close.

**D. Mint a dedicated Vault token for the workflow tier rather than reusing
`platform/mctl-agent/tokens`.** Better blast-radius isolation. Rejected as
out-of-band: it requires a Vault write plus an mctl-api change to accept a
second service token, and mctl-api validates exactly one static service token
today. Recorded as an open question instead.

## Platform impact

**Migrations.** None. No CRD, no schema, no data. The registry table was
created by `mctl-api#264`.

**Backward compatibility.** The workflow's three input parameters
(`team_name`, `service_name`, `domain`) and its `ClusterWorkflowTemplate` name
`add-custom-domain` are unchanged, so mctl-api's
`internal/operations/registry.go` entry and every existing caller
(`mctl_add_custom_domain`, the Backstage scaffolder, the CLI) keep working with
no coordinated release. Argo snapshots templates at submit time, so in-flight
runs finish on the old definition; per `CLAUDE.md`, allow ~3 minutes for ArgoCD
to sync before triggering a run against the new one.

**Ordering.** `mctl-api#264` is already merged and deployed, so the API side is
present before this lands. The ConfigMap key and the ExternalSecret must be
synced before the first run of the new template — they are in the same commit,
and the token preflight turns a partially-synced state into a clear message
rather than a confusing 401.

**Resource impact.** Negligible: two to three short HTTP calls to an
in-cluster service replace one DNS query. Dropping `bind-tools` marginally
shrinks the `apk add` step.

**Risks and mitigations.**

- *mctl-api unavailable makes domain-add impossible, where `dig` only needed a
  resolver.* This is a real new dependency. Mitigated by `--retry 3
  --retry-connrefused --max-time 30` and by the failure being loud and
  correctly attributed (HTTP status and body echoed). Accepted: mctl-api is
  already the submitter of this very workflow, so it is on the critical path
  regardless.
- *A platform-tier bearer token now lives in the workflow pod's environment.*
  Same exposure class as the `BACKSTAGE_TOKEN` it replaces, and the existing
  `PARAM_*` env-var indirection (lines 47-52) already prevents a crafted
  `team`/`service`/`domain` from reaching the shell as code. The secret exists
  only in `argo-workflows`, never in a tenant namespace.
- *Token scope is wider than Backstage's was.* `MCTL_AGENT_SERVICE_TOKEN`
  authenticates as `mctl-agent` across all of mctl-api, whereas
  `backstage-workflow-token` was scoped to one plugin. Mitigated by namespace
  isolation and by alternative D being recorded for follow-up; not mitigated
  within this change.
- *The workflow is submitted into a tenant namespace after all.* Then the
  secret is absent, `MCTL_API_TOKEN` is empty, and the preflight fails the run
  on line one with a message naming the namespace — instead of an opaque
  `CreateContainerConfigError` or a 401 five steps later.
- *The exit handler swallows errors.* By design; it must never convert a
  precise failure into "exit handler failed". The cost is that a `failed`
  status can be silently missed, leaving a row `pending`. That is strictly
  better than today, where no status is ever written on failure at all.
- *`spec.onExit` interacts with the cluster-wide completion hook.*
  `cwft-global-workflow-completion-hook.yaml` is a controller-level hook, not a
  `spec.onExit`, so adding one here does not displace it.
- *Rollout order with `wft-remove-custom-domain.yaml`.* The two templates
  diverge after this change: add uses mctl-api, remove still uses Backstage.
  This is intended and bounded; the in-template comments should say so, since
  the current ones assert the two are kept "in step".
