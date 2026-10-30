# Design: issue-830-spike-what-runtime-observability-and-egr

## Current state

### Agent-side (this repo)

- `orchestrator/options.py` `_audit_pre_tool_use` (around line 566) and `_command_audit_hooks`
  (line 614) form the only in-process hook on the model's shell. On every `Bash` call the hook prints
  one line, `AUDIT tool=Bash cmd=<repr> execution_context=<id>`, and returns `{}`, so the call is never
  denied. `_policy_hooks` (line 1071) matches only `mcp__.*`. `_ci_log_guard_hook` is a precedent for
  a regex-based `PreToolUse` deny on specific command shapes (`_CI_LOG_DENY_PATTERNS`).
- `orchestrator/run_implementer.py` `_TYPECHECK_ENV_KEEP` (line 4269) and `_typecheck_env`. The
  orchestrator's own `uv sync` runs build backends from the clone with an allowlisted env. The
  allowlist already forwards `HTTP(S)_PROXY`/`NO_PROXY`, which shows that package installs are
  expected to go through the proxy.
- `orchestrator/tracing.py` `AgentRunObserver` emits `execute_tool <name>` spans with
  `gen_ai.tool.name` and `is_error`. Tool arguments are not recorded. `classify_command` and
  `command_span` cover orchestrator gh/git only. `orchestrator/tracing_sdk.py` `GuardedExporter`,
  `key_allowed` and `redact_attributes` enforce the key allowlist. `k8s.pod.name` is set from
  `HOSTNAME` (`tracing_sdk.py:290`).
- `docs/observability/execution-traces.md` "Redaction rules": argv, tool arguments, stdout and paths
  are never recorded, with no opt-in. Any egress signal has to use closed vocabularies.
- `docs/spikes/852-sandbox-isolation-delta.md` rows N1 and D1-WebFetch assign pod egress detection to
  #830. Row D1-WebSearch notes that provider-side search is invisible to any pod control.
  `tests/test_spike_852_report.py` and `tests/test_tracing_coverage.py` are the pattern for guarding a
  docs-only spike with a structural test.
- `docs/spikes/854-agent-observability-gaps.md` lists trace gaps G1 to G7. None of them covers
  network egress.
- `docs/adr/023-runtime-assurance-probe-harness.md` and `orchestrator/assurance_harness.py`: the
  harness only performs `mcp.tool.call`, so it cannot probe pod egress. A network canary has to live
  elsewhere.

### Platform side (mctl-gitops, read-only)

- `agent-platform/execution-profiles/*/profile.yaml`: every profile declares
  `permissions.network: approved-providers-only`. The schema allows only `none` or that value
  (`agent-platform/schemas/execution-profile.schema.json:87`).
- `docs/runbooks/mctl-agents-egress.md`: the proxy rollout. The runbook says the CNI is flannel plus
  kube-router (from the runbook text, not verified). That CNI matches NetworkPolicy by IP only, so the
  hostname allowlist lives in a Squid forward proxy. The stages are:
  - A1, proxy deployed, allow-all, every host logged (#2161);
  - A2, agent CWFTs route through it (#2163, draft in the runbook);
  - B, `dstdomain` allowlist (not started);
  - C, default-deny egress NetworkPolicy `argo-workflows/config/networkpolicy-agents-egress.yaml`
    (not started).

  The Argo `init`/`wait` executors are explicitly not proxied. The runbook includes a candidate
  allowlist that already names `registry.npmjs.org`, `pypi.org` and `files.pythonhosted.org` as
  "unknown, depends on target repo".
- `infra-components/mctl-platform/mctl-agents-egress-proxy/proxy.yaml`: Squid with
  `access_log stdio:/dev/stdout squid` (native format, client IP only, no user) and `http_access allow
  all` after the link-local and loopback denies.
- `infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`: proxy ingress only from
  `argo-workflows` pods labelled `app.kubernetes.io/name: mctl-agents`. Proxy egress goes to kube-dns
  and to public IPs on 80/443.
- `argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`: `HTTPS_PROXY` appears in implement,
  investigate, reconcile, run and shepherd (5 to 6 occurrences each), in approve (4), and in scout and
  usage-collector (2 each). It does not appear in daily (0). `NO_PROXY` includes `10.0.0.0/8` and the
  service CIDR. Proxy use is only advisory: any process can unset the variables or open a raw socket,
  and until stage C nothing on the network stops it.
- `argo-workflows/config/networkpolicy.yaml`: an ingress-only policy, with no agent egress policy (the
  same finding as #807 G1).
- `bootstrap/templates/observability/loki.yaml`: Promtail has a `{namespace="argo-workflows"}` match
  block whose regex plus metrics stages turn step-pod log lines into counters
  (`lifecycle_shadow_*_total`). `vm-rules/vault-audit-alerts.yaml` shows the counter-to-VMRule
  alerting pattern, including the separate Silent and Absent rules ("could not observe" is not
  "observed quiet"). Each rule has a promtool test in `vm-rules/tests/`.
- No eBPF runtime sensor (Tetragon, Falco) was found under `infra-components/` or `bootstrap/`. A grep
  for those names matched only cert-manager and descheduler files, for unrelated reasons.

Deployed state checked:
- `mctl_get_service_status(admins, mctl-agents-worker)`: Healthy, Synced, image `1.108.0`. This
  confirms the worker is live. It says nothing about step-pod egress.
- gitops paths read: `bootstrap/templates/mctl-platform/mctl-agents-egress-proxy.yaml`,
  `infra-components/mctl-platform/mctl-agents-egress-proxy/{proxy,networkpolicy}.yaml`,
  `docs/runbooks/mctl-agents-egress.md`, `argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`
  (`HTTPS_PROXY` counts), `argo-workflows/config/`, `bootstrap/templates/observability/loki.yaml`,
  `infra-components/observability/vm-rules/`, `tenants/admins/values.yaml`,
  `agents-state/mctl-agents/proposals/issue-807-*/{design.md,.status.yaml}` (PR #810 open, head
  `7b1c9267f5cf80d738e3b2f3134415740402d764`).
- Not observed: the live Squid access log in Loki (no read-only tool reaches the `mctl-agents-egress`
  namespace), the state of PR #2163 and the live pod env, whether the Loki ruler is enabled,
  kube-router drop logging, the CoreDNS `log` plugin, and Argo executor egress. Each of these is in
  Open questions. None is treated as absent.

## Proposed solution

Ship one docs-only spike report, `docs/spikes/830-runtime-egress-detection.md`, and one guard test,
`tests/test_spike_830_report.py`. The report makes no runtime change. It answers the question in four
sections.

### 1. Source and limits

The source article is cited. Where the article body was not retrieved, the taxonomy rests on the
public description of the OpenAI evaluation (package installation reaching the internet) and on repo
and gitops evidence. Section 1 states that live cluster state was not observed.

### 2. Escape-path matrix

The matrix has columns `id | path | layer | signal | producer | attribution | state | unblocked_by |
follow_up`. The state vocabulary is `emitted | partial | missing | blind | out-of-scope`.

| id | path | signal and producer | state today | unblocked by |
|---|---|---|---|---|
| X1 | Proxied HTTP(S) from model tools, package managers (pip, npm, uv, go) and curl that honour `HTTPS_PROXY` | Squid access log on stdout, sent to Loki (`proxy.yaml`). Attribution is the client pod IP only. | partial: logged, no alert, no run attribution | A2 live; F2 attribution; B for denials |
| X2 | Direct connection that bypasses the proxy (`env -u HTTPS_PROXY`, `--proxy ''`, raw socket, a tool that ignores the env) | None at the network layer before stage C. After C: refused connections, plus kube-router drop logging if available (not observed). | blind until C | C, then F4 |
| X3 | DNS side channel (kube-dns stays allowed in stage C) | CoreDNS query log, if the `log` plugin is enabled (not observed) | blind / not observed | F6 |
| X4 | Provider-side `WebSearch` (#852 D1) | `execute_tool WebSearch` span count only (`tracing.py` `AgentRunObserver`). The destination is never visible. | partial | #852 follow-up 1 (remove or mediate) |
| X5 | Argo `init`/`wait` executors, direct to R2 and the kube API | Not agent-controlled. Excluded from stage C per the runbook. | out-of-scope | runbook task 2 |
| X6 | In-process intent: the model runs an install, a fetch or a proxy-unsetting command | `AUDIT tool=Bash` line from `_audit_pre_tool_use`. It is free text, so there is no counter and no alert. | partial | F3 |
| X7 | Repository code at build or test time (postinstall scripts, setup.py) opening sockets | Same as X1 or X2 depending on whether the code honours the proxy. There is no process-level signal. | blind for process identity | eBPF sensor (deferred, Alternative 2) |

### 3. Egress policy and runtime audit plan, ordered by proxy stage

- Stage A (now). Run F1: Promtail counters on the Squid log in the `mctl-agents-egress` namespace,
  following the vault-audit pattern. The counters are `agent_egress_requests_total` and
  `agent_egress_log_lines_total`. Two VMRules go with them: `AgentEgressProxyLogSilent` and
  `AgentEgressProxyLogAbsent`, because detection that silently stops is worse than none. Also run F2,
  run attribution. The recommended way is a per-run proxy username,
  `HTTPS_PROXY=http://<workflow-name>@agent-egress-proxy...:3128`, with Squid configured with a helper
  that accepts any user and a `logformat` that includes `%un`. The fallback is a pod-IP join. Run F3 in
  mctl-agents: a closed classifier on the `Bash` audit hook that adds `class=` to the AUDIT line. The
  vocabulary is `package-install`, `network-fetch`, `proxy-env-change` and `none`. The classifier
  copies no argv, only the class token. Promtail counts one counter per class (the
  `lifecycle_shadow_*` precedent), and `proxy-env-change` alerts at once.
- Stage B (allowlist). Run F4: a Promtail counter on `TCP_DENIED/403` lines, `agent_egress_denied_total`,
  and the alert `AgentEgressDenied` (any increase, routed to Telegram). The hostname stays in Loki and
  is never used as a metric label. The plan decides package registries explicitly. Implementer and
  test runs legitimately need `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org` and
  `proxy.golang.org`. Allowing them keeps exfiltration possible through package uploads and through
  dependency-confusion fetches. Denying them breaks implementer test runs. The report recommends
  allowing these registries for implementer CWFTs only. The longer-term target is a pull-through
  registry mirror, at which point the public registries leave the allowlist.
- Stage C (enforce). The egress NetworkPolicy turns X2 from blind into refused. Run F5: a scheduled
  canary CronWorkflow in `argo-workflows`, labelled `app.kubernetes.io/name: mctl-agents`. It makes
  one direct connection with the proxy unset and one proxied request to a host outside the allowlist.
  It passes only if both are refused and `agent_egress_denied_total` moved. This self-tests the
  detector, the same idea as the Silent and Absent split. F6 covers DNS (the CoreDNS log plugin, or a
  restricted resolver) and is P3.

### 4. Decision and follow-ups

Draft issue bodies F1 to F6, each with owning repo, priority, dependency, scope and rollback. F1, F2,
F4 and F5 are in mctl-gitops. F3 is in mctl-agents. F6 is in mctl-gitops. The recommended token is
`ADOPT_PLAN`. The report merges as `STATUS: DRAFT` until the owner records a token, matching #852.

### Guard test

`tests/test_spike_830_report.py`, modelled on `tests/test_spike_852_report.py`, checks:
- there is one `STATUS:` line with an allowed token;
- every matrix row has 9 cells, a non-empty producer, and a state in the vocabulary;
- ids X1 to X7 are present;
- the report mentions `#852` and `N1`;
- every follow-up heading `### F<n>` names a `Repo:`;
- the report contains no token-shaped strings.

## Alternatives

1. **Detection only through OpenTelemetry spans (extend #854).** This would add an
   `mctl.sandbox.egress_intent` event on `execute_tool Bash`. It was dropped as the primary signal for
   two reasons. Spans come from the same process the model controls, and the network-layer signal
   (Squid, NetworkPolicy) is what holds when the process misbehaves. Also, #854 G5 shows several
   runners are untraced. The F3 class token can still be mirrored onto the span later, once
   mctl-docs reserves the name.
2. **eBPF runtime sensor (Tetragon or Falco) on the nodes.** It would give process-level attribution
   for X7 and catch raw sockets without depending on the proxy. It was deferred: it is not installed,
   it adds a privileged DaemonSet with node-wide resource cost on a small k3s cluster, and stage C
   plus the proxy log covers the network outcome. The report keeps it as the escalation path if X7
   attribution is ever required.
3. **Deny package-manager commands in the `Bash` hook (extend `_CI_LOG_DENY_PATTERNS`).** This was
   rejected as a control. A deny-list on command text is bypassable (as #852 D2 already notes) and
   would break legitimate implementer test runs. Classifying for audit (F3) keeps the visibility
   without pretending to enforce.

## Platform impact

- This PR adds one Markdown file and one pytest module. It has no migrations, no runtime change and
  no gitops change, so backward compatibility is not affected.
- Resource impact of the follow-ups is small. The Promtail regex stages run on two namespaces. The
  canary is one short pod per schedule.
- Risk: the report's claims about live state could go stale (the proxy stages are moving).
  Mitigation: the report pins the gitops evidence paths and the #810 head SHA, and marks each
  unobserved source as not observed.
- Risk: F2's per-run proxy username leaks the workflow name into the Squid log. That is acceptable,
  because the name is not a secret and Loki access is admin-only. It must never be a credential.
- Risk: the registry allowlist decision in stage B lets package-upload exfiltration through. This is
  recorded as an accepted residual risk, with the mirror as the long-term fix. The owner decides.
