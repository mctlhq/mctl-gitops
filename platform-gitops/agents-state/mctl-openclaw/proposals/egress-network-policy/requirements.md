# Egress NetworkPolicy to restrict outbound traffic from openclaw pods

## Context

CVE-2026-41297 (SSRF in marketplace plugin download) allows redirecting openclaw HTTP requests
to arbitrary internal or external hosts. While that specific CVE is closed by upgrading to
2026.4.25 (see proposal `upgrade-to-2026-4-25`), the architectural gap itself — the absence
of an egress NetworkPolicy on the openclaw namespaces — remains and stays exposed to any
future SSRF in openclaw core or its plugins.

Today the openclaw pods in namespaces `ovk`, `labs`, `admins` have no outbound traffic
restrictions: a pod can reach any IP inside the cluster and outside. This violates the
least-privilege principle for network access and creates an irreducible lateral-movement
risk on any future SSRF or RCE in openclaw. A Kubernetes NetworkPolicy with an explicit
egress whitelist removes this attack class regardless of the openclaw version.

## User stories

- AS a platform security engineer I WANT egress from openclaw pods restricted to required
  endpoints SO THAT an SSRF vulnerability in any openclaw version cannot reach internal
  cluster services or unintended external hosts
- AS a platform operator I WANT NetworkPolicy applied via gitops (ArgoCD) without changes
  to openclaw code SO THAT the change can be rolled back via a manifest without a new image deploy
- AS a labs tenant operator I WANT NetworkPolicy not to increase pod RAM consumption SO THAT
  the labs tenant does not approach OOM

## Acceptance criteria (EARS)

- WHEN an openclaw pod in any tenant (`ovk`, `labs`, `admins`) attempts to reach an IP not in
  the egress whitelist THE SYSTEM SHALL reject the connection at iptables level (connection
  timeout or connection refused without packet passing)
- WHEN an openclaw pod issues a request to the allowed S3 endpoint THE SYSTEM SHALL pass
  traffic without delay
- WHEN an openclaw pod issues a request to the allowed upstream marketplace endpoint THE SYSTEM
  SHALL pass traffic without delay
- WHEN an openclaw pod issues requests to channel API endpoints (Telegram, Discord, Slack,
  WhatsApp and other channels from the architecture list) THE SYSTEM SHALL pass traffic
- WHILE NetworkPolicy is applied THE SYSTEM SHALL not block traffic to DNS (UDP/TCP 53
  in the kube-dns namespace)
- WHILE NetworkPolicy is applied THE SYSTEM SHALL not block egress traffic to the mctl-api
  endpoint (`api.mctl.ai/mcp`) for MCP integration
- IF an openclaw pod attempts to initiate a connection to any address in the RFC-1918 ranges
  (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) that is not an explicitly allowed cluster
  service THEN THE SYSTEM SHALL block the connection
- WHEN the allowed endpoints set changes (a new channel or S3 region) THE SYSTEM SHALL apply
  the updated NetworkPolicy via ArgoCD sync without restarting pods

## Out of scope

- Changes to openclaw source code or its configuration
- Ingress NetworkPolicy (managing inbound traffic — separate task)
- Changing resource limits or requests on openclaw pods
- Inter-tenant network isolation (namespace isolation) — already provided by the architecture
  of three independent namespaces per ADR 0001
- Introducing a service mesh (Istio, Linkerd) — heavier solution, separate decision
