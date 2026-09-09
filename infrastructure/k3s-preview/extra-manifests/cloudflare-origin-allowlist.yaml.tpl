# Cloudflare-only ingress on the websecure entrypoint (#1119).
#
# Why the control is here and not on the cloud firewall, which is what #1119
# originally asked for. 91.98.10.188 is the Hetzner Cloud LOAD BALANCER for
# svc/traefik, not a node -- only 80 and 443 answer on it; 22 and 6443 do not.
# Hetzner cloud firewalls attach to servers, and hcloud-cloud-controller-manager
# ignores spec.loadBalancerSourceRanges, so there is no firewall object in front
# of that address to write a rule on. There is nothing to close on the nodes
# either: kube-hetzner opens 80/443 there only when using_klipper_lb is true,
# and it is false here (4 nodes, klipper off). Traefik is the first thing on the
# path that can refuse the request, so the control lives in Traefik.
#
# Traefik is also the stronger place for it. A pod dialling a public IP does not
# traverse the cloud firewall -- kube.tf says so, and nodePublicCIDRs in
# platform-gitops/helm-charts/tenant/values.yaml is the compensating control --
# but the load balancer's address is not in that list, because it is not a node.
# Until this landed, any tenant pod could reach the origin with an arbitrary
# Host header and skip the edge from inside the cluster. A cloud-firewall
# allowlist could never have closed that path; this does.
#
# The match is unspoofable. The hcloud LB is annotated uses-proxyprotocol=true
# and the websecure entrypoint trusts PROXY from 10.0.0.0/8, so RemoteAddr is
# the Cloudflare edge address rather than the LB's. ipAllowList with no
# ipStrategy matches on RemoteAddr and NOT on X-Forwarded-For, which a client
# controls. Do not add an ipStrategy here.
#
# v3 spelling: the installed CRD group is traefik.io (traefik v3.7.10). v2's
# traefik.containo.us called this ipWhiteList; that name parses and silently
# allows everything. Same trap is documented in
# platform-gitops/services/labs/mctl-telegram/values.yaml.
#
# Namespace traefik, not kube-system, because that is where the ingress
# controller runs and this object is its configuration -- the sibling
# traefik-helmchartconfig.yaml.tpl is in kube-system only because a
# HelmChartConfig must share a namespace with its HelmChart, which is a
# requirement rather than a convention. Traefik's kubernetescrd provider is
# started with no namespace restriction, so it would find this object either
# way; the placement is about where it belongs, not about whether it works.
#
# The namespace is not an undeclared dependency. kube-hetzner's
# templates/traefik_ingress.yaml.tpl declares `kind: Namespace` alongside the
# HelmChart, and that manifest is applied by `kubectl apply -k
# /var/post_install` (init.tf) -- which then waits for the traefik namespace's
# deployments to become Available and for the load balancer to get an IP.
# The user kustomization that applies THIS file runs later:
# kustomization_user.tf declares `depends_on = [terraform_data.kustomization]`,
# i.e. on that same post-install step. A from-zero rebuild therefore has the
# namespace, and a running Traefik, before this manifest is applied.
#
# Source: https://api.cloudflare.com/client/v4/ips
# Fetched 2026-09-09, etag 38f79d050aa027e3be3865e495dcc9bc.
# A daily check that this list still matches the API ships with the follow-up
# pull request that references the middleware from the entrypoint. Until then
# the list is unguarded. Do not hand-edit: regenerate from the API and keep
# the etag comment in sync.
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: cloudflare-origin
  namespace: traefik
  labels:
    app.kubernetes.io/part-of: mctl-platform
    mctl.me/component: origin-allowlist
spec:
  ipAllowList:
    sourceRange:
      # --- Cloudflare IPv4 ---
      - 173.245.48.0/20
      - 103.21.244.0/22
      - 103.22.200.0/22
      - 103.31.4.0/22
      - 141.101.64.0/18
      - 108.162.192.0/18
      - 190.93.240.0/20
      - 188.114.96.0/20
      - 197.234.240.0/22
      - 198.41.128.0/17
      - 162.158.0.0/15
      - 104.16.0.0/13
      - 104.24.0.0/14
      - 172.64.0.0/13
      - 131.0.72.0/22
      # --- Cloudflare IPv6 ---
      # Unreachable today: the zones publish A records only, so the edge
      # connects to the origin over IPv4. Listed anyway because the load
      # balancer has a public IPv6 (2a01:4f8:c01e:1b67::1) and publishing an
      # AAAA record later must not become a silent outage.
      - 2400:cb00::/32
      - 2606:4700::/32
      - 2803:f800::/32
      - 2405:b500::/32
      - 2405:8100::/32
      - 2a06:98c0::/29
      - 2c0f:f248::/32
