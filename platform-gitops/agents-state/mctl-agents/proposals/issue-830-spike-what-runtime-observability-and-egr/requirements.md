# Spike #830: runtime observability and egress controls that detect an agent escaping its sandbox

## Context

Issue mctlhq/mctl-agents#830 asks which runtime observability and egress controls would detect an
agent escaping its sandbox. The motivating case is an OpenAI evaluation where an agent's package
installation reached the internet. The issue wants two outcomes: an egress policy and a runtime audit
plan. The related spikes split the problem. #807 (PR #810) covers the preventive Kubernetes primitives,
and its gap G1 ("no egress control on agent pods") is being closed by the staged egress proxy
(mctl-gitops#2159). #852 (`docs/spikes/852-sandbox-isolation-delta.md`) marks pod egress and
package-install escape (row N1) as `covered-by-830`, so this spike owns detection. #854
(`docs/spikes/854-agent-observability-gaps.md`) lists the general trace gaps and does not cover egress.

This matters because an mctl-agents step pod holds long-lived credentials in its environment (#807 G2).
It also runs repository code through the model's `Bash` tool (#852 D4), and today that tool is audited
but never denied (`orchestrator/options.py` `_audit_pre_tool_use`). A package install is the natural
way for untrusted code to reach the network, and right now nothing would alert on it. The deliverable
is a docs-only spike report in this repo. It contains a detection matrix, a staged egress and
runtime-audit plan tied to the proxy rollout stages A, B and C, and draft follow-up issues. A test
guards the report's structure, in the same way #852 and #854 are guarded.

## User stories

- AS the platform owner I WANT a list of every path an agent step pod can use to reach the internet,
  with the signal that would reveal each one SO THAT I know which escapes are detectable today and
  which are blind spots.
- AS the platform owner I WANT the egress policy and the runtime audit plan ordered against the egress
  proxy rollout (stages A, B, C) SO THAT detection work lands when it can actually fire, not before.
- AS an on-call operator I WANT each proposed alert to name its producer, the log or metric it reads,
  and how it ties back to an agent run SO THAT an alert can be traced to one workflow.
- AS a reviewer of follow-up work I WANT each follow-up drafted with its owning repo, dependency and
  rollback SO THAT it can be filed and implemented without redoing the spike.

## Acceptance criteria (EARS)

- WHEN the spike is implemented THE SYSTEM SHALL add `docs/spikes/830-runtime-egress-detection.md`
  with exactly one `STATUS:` line whose value is `DRAFT` or one of `ADOPT_PLAN`, `ADOPT_SUBSET`,
  `RESEARCH_ONLY`.
- THE SYSTEM SHALL include an escape-path matrix in the report. Each row has: id, path, layer,
  detecting signal, producer (a file and symbol, or a gitops path), attribution, state (`emitted`, `partial`,
  `missing`, `blind`, or `out-of-scope`), stage that unblocks it, and follow-up id.
- THE SYSTEM SHALL cover at least these paths in the matrix:
  - proxied HTTP(S) from model tools and package managers;
  - a direct connection that bypasses `HTTP(S)_PROXY`;
  - DNS as a side channel;
  - provider-side `WebSearch` (#852 D1);
  - the Argo `init`/`wait` executors;
  - in-process command intent seen by the `Bash` audit hook.
- THE SYSTEM SHALL state, for each detection signal, how an event is attributed to one agent run
  (pod IP, pod name, execution context id or workflow name). Where no attribution exists, it SHALL
  state that explicitly.
- THE SYSTEM SHALL order the plan against the egress proxy stages in `docs/runbooks/mctl-agents-egress.md`
  (mctl-gitops). It SHALL state that a direct-bypass escape cannot be detected at the network layer
  before stage C is enforced.
- WHILE any follow-up proposes a new log line, metric or span attribute THE SYSTEM SHALL restrict it to
  closed vocabularies. It SHALL never carry argv, hostnames chosen by the model, or tool arguments in
  telemetry attributes, consistent with "Redaction rules" in `docs/observability/execution-traces.md`.
- IF a source could not be observed from the investigating run (live proxy log, Loki ruler, CNI drop
  logging, CoreDNS logging) THEN THE SYSTEM SHALL list it as not observed and SHALL NOT report it as
  absent.
- THE SYSTEM SHALL include draft follow-up issue bodies, each with: owning repo, priority, dependency,
  scope and rollback. It SHALL include at least one detector self-test (a canary that attempts a
  forbidden egress and expects both a refusal and an alert).
- WHEN `uv run pytest tests/test_spike_830_report.py` runs THE SYSTEM SHALL check four things: the
  status token, that every matrix row is well formed with a value from the state vocabulary, that the
  #852 N1 path appears in the matrix, and that the report contains no token-shaped strings.
- THE SYSTEM SHALL NOT change runtime behaviour, gitops manifests or agent profiles in this PR.

## Out of scope

- Implementing any control: the Squid allowlist (stage B), the egress NetworkPolicy (stage C), Promtail
  counters, VMRules, the canary, or classifier code in `orchestrator/options.py`. These become
  follow-ups.
- Preventive primitives that #807 already owns (credentials in env G2, namespace split G3, PSA G4,
  kernel sandbox G5, quota G6).
- In-process deny controls for `Bash` and project-settings loading (#852 D2 and D3).
- Installing an eBPF runtime sensor (Tetragon or Falco). It is evaluated as an alternative only.
- Filing the follow-up issues. The report carries draft bodies only.

## Open questions

- The issue does not define "detect". This proposal reads it as: an alert fires within minutes and
  names the run. It does not mean prevention, which #807 G1 already owns.
- Whether Loki's ruler is enabled. The Promtail metrics-stage plus VMRule pattern
  (`bootstrap/templates/observability/loki.yaml`, `vm-rules/vault-audit-alerts.yaml`) is the only
  log-to-alert path seen in gitops, so the plan assumes it.
- Whether kube-router can log NetworkPolicy drops on this cluster, and whether CoreDNS has its `log`
  plugin enabled. Neither was observable. Both decide whether direct bypass and DNS exfiltration are
  `missing` or `blind`.
- Pod-IP attribution of Squid log lines. The options are a pod-IP join (for example kube-state-metrics
  `kube_pod_info`) or a per-run proxy username in `HTTPS_PROXY`. The second needs a Squid auth helper
  that accepts any name. The owner should choose one. The report recommends the username approach and
  records the trade-off.
- Whether stage A2 (mctl-gitops#2163, routing the agent CWFTs through the proxy) is live. The gitops
  checkout shows `HTTPS_PROXY` in 8 of the 9 `cwft-mctl-agents-*` templates (not in
  `cwft-mctl-agents-daily.yaml`), but the PR state and live pod env were not observed.
- The `mctl_get_workflow_logs` tool description says Loki never ingests Argo step pods. The Promtail
  config has a `{namespace="argo-workflows"}` match block whose comments state the shepherd's step-pod
  lines are counted. The two sources disagree, and that decides whether the `AUDIT tool=Bash` lines
  can feed a counter.
