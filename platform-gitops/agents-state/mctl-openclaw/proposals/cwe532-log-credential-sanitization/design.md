# Design: cwe532-log-credential-sanitization

## Current state

All three tenants (admins, labs, ovk) run openclaw 2026.3.14 on Kubernetes managed by ArgoCD (see
`context/architecture.md`). Application pods write HTTP request logs to stdout/stderr. A DaemonSet
log agent (Fluentd or Vector, depending on the cluster's log-shipper configuration) collects those
streams from each node and forwards them to the log-aggregation backend (Loki, CloudWatch,
Datadog, or similar). No scrubbing or redaction transform is applied at any point in this pipeline
today.

As a result, log lines of the form:

```
GET /api/webhook?token=xoxb-live-slack-token-value HTTP/1.1 200
Authorization: Bearer eyJhbGci...live-jwt...
GET /oauth/callback?code=4/P7q7W HTTP/1.1 302
```

flow from pod stdout through the DaemonSet agent into the backend without modification. Anyone
granted log-read access to the backend — including all operators, any CI/CD pipeline with log
tailing, and any third-party log observability service — can retrieve production secrets.

The permanent fix (application-level sanitization) ships in openclaw 2026.5.2 and must soak
through the mandatory labs → admins → ovk promotion cycle before reaching production (ovk). That
cycle takes several days. This proposal covers the interim period.

## Proposed solution

Insert a **scrubbing transform** into the DaemonSet log-shipper configuration. The transform
operates on the raw log line string before it is forwarded to the backend. No changes are made to
openclaw application code, Kubernetes Deployments, or ArgoCD Application manifests.

### Regex rules (three patterns, applied in sequence)

| Pattern | Replacement |
|---|---|
| `\?password=[^&\s"']+` | `?password=REDACTED` |
| `\?token=[^&\s"']+` | `?token=REDACTED` |
| `(?i)Authorization:\s*[^\r\n"']+` | `Authorization: REDACTED` |

All three rules are applied to every log line collected from pods in the `admins`, `labs`, and
`ovk` namespaces. Multiple occurrences per line are all replaced (global flag). The remaining
content of the line — method, path structure, status code, timestamps, trace IDs — is untouched.

### Fluentd implementation (primary)

If the cluster log-shipper is Fluentd, add a `<filter>` stanza in the Fluentd ConfigMap that
applies to `kubernetes.var.log.containers.*_admins_*`, `*_labs_*`, and `*_ovk_*` sources:

```ruby
<filter kubernetes.var.log.containers.**>
  @type record_transformer
  enable_ruby true
  <record>
    log ${
      record["log"]
        .gsub(/\?password=[^&\s"']+/, '?password=REDACTED')
        .gsub(/\?token=[^&\s"']+/,    '?token=REDACTED')
        .gsub(/(?i)Authorization:\s*[^\r\n"']+/, 'Authorization: REDACTED')
    }
  </record>
</filter>
```

The filter is scoped to the three tenant namespaces via Fluentd routing tags so that it does not
affect unrelated workloads on the same cluster.

### Vector implementation (alternative primary)

If the cluster log-shipper is Vector, add a `remap` transform in the Vector pipeline:

```toml
[transforms.openclaw_scrub]
type   = "remap"
inputs = ["kubernetes_logs"]
source = '''
  if match(string!(.kubernetes.namespace_name), r'^(admins|labs|ovk)$') {
    .message = replace(.message, r'\?password=[^&\s"'"'"']+',    "?password=REDACTED")
    .message = replace(.message, r'\?token=[^&\s"'"'"']+',       "?token=REDACTED")
    .message = replace(.message, r'(?i)Authorization:\s*[^\r\n"'"'"']+', "Authorization: REDACTED")
  }
'''
```

### NetworkPolicy (secondary mitigation)

If the log-aggregation backend is reachable by any pod in the cluster today (no NetworkPolicy),
apply a NetworkPolicy on the backend namespace that only permits ingress from:
- The DaemonSet log-agent ServiceAccount.
- Designated observability tooling namespaces (e.g., `monitoring`).

This narrows the blast radius if log data has already been forwarded: a compromised workload pod
cannot directly query the backend to harvest historical secrets.

### Retirement path

Once openclaw 2026.5.2 is confirmed healthy on all three tenants, the log-shipper scrubbing
transform can be removed by reverting the ConfigMap change and reloading the DaemonSet. The
NetworkPolicy may be retained as defense-in-depth with no operational cost.

## Alternatives

### Option A: Application-level patch (monkey-patch logging middleware)

Fork the openclaw HTTP logger in the extensions layer and inject a redaction step before the log
call. This keeps the fix inside the application boundary.

Dropped because: it requires code changes deployed via ArgoCD, which means the labs → admins → ovk
soak cycle applies — exactly the delay this proposal is designed to avoid. It also risks breaking
the restore-state probe if the rollout is flawed.

### Option B: Disable HTTP request logging entirely

Set the openclaw log level to suppress HTTP access logs until 2026.5.2 is deployed.

Dropped because: HTTP access logs are the primary operational signal for diagnosing channel
failures, webhook delivery problems, and skill routing errors. Disabling them blinds the operations
team during the highest-risk period (when the upgrade is being evaluated). Loss of observability is
a worse trade-off than the delay from option A.

### Option C: Rotate all exposed credentials now and accept ongoing exposure until upgrade

Treat the existing exposure as an incident, rotate secrets, and accept that the leak continues
until 2026.5.2 lands, without any infra-layer mitigation.

Dropped because: rotation without scrubbing means newly issued credentials begin leaking
immediately. This is not a one-time fix — it must be repeated after every rotation until the root
cause is addressed. Proactive scrubbing at the shipper layer stops the forward accumulation of
secrets in the backend regardless of rotation cadence.

## Platform impact

### Migrations

No schema migrations. The change is limited to the Fluentd or Vector DaemonSet ConfigMap.
The DaemonSet pods reload configuration without restarting openclaw application pods.

### Backward compatibility

The scrubbing transform only modifies the `log` / `message` field in forwarded log events. All
other fields (pod name, namespace, container, timestamp, trace IDs) are preserved unchanged.
Log-query dashboards that reference fields other than the raw message are unaffected. Any existing
alert rule that searches for a literal `?token=` or `Authorization:` in the raw message will no
longer fire on redacted lines — this is intentional and expected.

### Resource impact (labs)

The transform adds three `gsub` / `replace` calls per log line in the DaemonSet agent process, not
in the openclaw pod. The DaemonSet agent runs in its own pod on the node and does not share memory
limits with the `labs` tenant's openclaw pod. Regex scrubbing at the log-shipper level adds
negligible CPU overhead (sub-millisecond per line) and zero additional memory to the `labs`
openclaw container. This proposal is not flagged as risky for `labs`.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Regex incorrectly redacts part of a benign URL fragment that resembles `?token=` | Low | Pattern anchors on `?` and stops at `&`, whitespace, quotes — benign path tokens without these delimiters are unaffected. Review in labs first. |
| DaemonSet ConfigMap reload interrupts log forwarding briefly | Low | Fluentd and Vector support hot-reload; buffered events are flushed before reload. |
| Scrubbing transform is forgotten and left in place after the upgrade | Low | The `tasks.md` retirement task is explicitly linked to the `upgrade-to-2026-5-2` proposal completion gate. |
| Historical logs in backend already contain plaintext credentials | Certain | Out of scope for this proposal; a separate incident-response workstream must assess and purge if required by data-handling policy. |
