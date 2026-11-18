# NGINX exposure inventory after the 2026-11-18 nginx.org advisories

Snapshot taken 2026-11-18 / 2026-11-19 (UTC), read-only, on the preview cluster.
Source data: [`nginx-2026-11-18-inventory.csv`](nginx-2026-11-18-inventory.csv)
(184 containers, 103 distinct images). Pod names are reduced to workload names.

Verdict: no reachable exploitation path was found for any of the ten advisories;
every NGINX in the cluster is on a version inside a vulnerable range and needs
updating once a fixed image is built. This is not an emergency, it is version debt.

## Scope and method

- Image inventory from `kubectl get pods -A` (containers, init containers, digests).
- One running container per distinct image: `command -v nginx`, standard binary
  paths, then a filesystem search for `nginx`, `libnginx*`, `ngx_*.so`, `openresty`.
- Where nginx was found: `nginx -v`, `nginx -V`, and the effective configuration
  from `nginx -T`, filtered for `listen`, `http2`, `http3`, `quic`, `resolver`,
  `mail`, `stream`, `alias`, `try_files`, `proxy_protocol`, `load_module`, `ssl*`.
  The full `nginx -T` output was not stored (it can contain secrets).
- No restart, reload, rollout, or file change was made on any workload.

## NGINX found (6 images)

| Namespace / workload | Running digest | nginx | Effective config | Status |
|---|---|---|---|---|
| admins / mctl-web | `mctl-web@sha256:fb27ddef...` | 1.31.7 | `listen 8080;` | VERIFIED |
| admins / mctl-docs | `mctl-docs@sha256:467984a7...` | 1.31.7 | `listen 8080;`, `try_files` | VERIFIED |
| admins / mctl-design | `mctl-design@sha256:f0e6fe55...` | 1.31.7 | `listen 8080;`, `try_files` | VERIFIED |
| labs / portfolio | `portfolio@sha256:4187b682...` | 1.31.7 | `listen 8080;`, `try_files` | VERIFIED |
| labs / genai-leader | `genai-leader@sha256:1270389f...` | 1.27.5 | `listen 8080;`, `listen [::]:8080;` | VERIFIED |
| redloop / redloop-synthetic-staging | `chainguard-nginx@sha256:d1007c59...` | 1.31.8 | `listen 8080;`; mail and stream built as dynamic modules, no `load_module` | VERIFIED |

`nginxinc/nginx-unprivileged:1.31-alpine` is not "1.31.8": the pinned digest
`b5047b9b...` is nginx 1.31.7 on Alpine 3.24.2. Tags do not prove versions;
`nginx -v` does.

The `genai-leader` image has no source repository in the organization (the GHCR
package is private and not linked to one). Its history shows the upstream
`nginx:1.27.5-alpine` layers on Alpine 3.21.3. How it is built is UNVERIFIED.

## The ten advisories (nginx.org, fixed in 1.31.9 and 1.30.7)

| CVE | What | Gate (from nginx CHANGES) | Vulnerable | Result for the 6 images |
|---|---|---|---|---|
| CVE-2026-123634 | use-after-free in resolver | `resolver` directive | 0.6.18-1.31.8 | NOT APPLICABLE, no `resolver` |
| CVE-2026-123007 | HTTP/2 flow control memory corruption | HTTP/2 | 1.9.5-1.31.8 | NOT APPLICABLE, no `http2` |
| CVE-2026-121810 | HTTP/3 use-after-free | HTTP/3 | 1.25.0-1.31.8 | NOT APPLICABLE, no `quic`/`http3` |
| CVE-2026-123633 | HTTP/2 use-after-free | HTTP/2 | 1.19.7-1.31.8 | NOT APPLICABLE, no `http2` |
| CVE-2026-118899 | infinite loop reading request body over TLS 1.3 | TLS listener | 1.13.0-1.31.8 | NOT APPLICABLE, no `ssl` listener |
| CVE-2026-113425 | use-after-free in mail proxy | mail module | 0.5.33-1.31.8 | NOT APPLICABLE, no `mail` block |
| CVE-2026-120993 | NULL dereference, PROXY protocol v2 | PROXY protocol v2 with dynamic certs | 1.31.4-1.31.8 | NOT APPLICABLE; also outside range for 1.27.5; fixed only in 1.31.9, not 1.30.7 |
| CVE-2026-125283 | buffer overflow, `alias` with `try_files` | both directives | 0.9.6-1.31.8 | NOT APPLICABLE, `try_files` present, `alias` absent |
| CVE-2026-120967 | SNI bypass with client certificates in stream | stream module | 1.25.5-1.31.8 | NOT APPLICABLE, no `stream` block |
| CVE-2026-123640 | ssl_preread inconsistency | stream module | 1.15.2-1.31.8 | NOT APPLICABLE, no `stream` block |

The gates above come from nginx's CHANGES file; the advisory page itself states
no exploitation conditions. NOT APPLICABLE follows from the effective
configuration, not from a reading of each advisory's code.

Re-evaluate this table when any NGINX configuration, module set, listener or
image changes. Run `scripts/check-nginx-effective-config.py` on the
`nginx -T` output of the changed workload: it fails on every gated feature above
and exits 2 (UNVERIFIED) when the input is not a readable configuration.

## Images that were not verified (39 of 103)

Not "absent": "not observed".

- 24 images without a shell (distroless Go components, for example cert-manager,
  Argo, CSI sidecars, coredns, zitadel, cloudflared, tempo, otel): exec is
  impossible; evidence is vendor provenance only.
- 4 images that exist only in completed pods (terraform, two python images, argoexec).
- 11 images used only by init containers or non-running pods: alpine/k8s, aws-cli,
  postgres, klipper-helm, wait4x, the barman-cloud sidecar, grafana-iac,
  mctl-workflow-tools, vault-iac, zitadel-iac, descheduler.

Closing this backlog needs an SBOM or a layer listing per image, not exec.

## Scanner blind spot

The RedLoop image `chainguard-nginx@sha256:d1007c59...` is nginx 1.31.8, inside the
vulnerable range of CVE-2026-123007, yet the Trivy run `44416504118` on
2026-11-18 reported 0 findings at every severity. The vulnerability database it
used (`trivy-db:2` from `mirror.gcr.io`, manifest created 2026-11-18T19:18:08Z at
the time of reading) therefore did not carry those advisories for this image.
"0 findings" is not a security clearance for these CVEs. Re-scan after the
database catches up, and do not use the result as evidence of absence.

## Fixed images available (2026-11-18)

- `nginx/nginx-unprivileged:1.31.9-alpine`, index digest
  `sha256:60214a103e6f38e953ff957f34b1f2e97a9db801ab2df3821da955d0fe6cadd6`:
  nginx 1.31.9, uid/gid 101, Alpine 3.24.4, same compiled modules as the
  1.31.7 base. The unprivileged images moved from the `nginxinc/` namespace.
- `docker.io/chainguard/nginx`, amd64 manifest
  `sha256:4841077f54db8761ca74942fa759f33b1e94d7b63cd7b1719338366b4e7003a9`:
  nginx 1.31.9, uid 65532, created 2026-11-18T18:39:15Z.

Draft pull requests: mctl-web#258, mctl-docs#227, mctl-design#232,
portfolio#216 (static sites), and the RedLoop mirror entry in this repository.
`genai-leader` has no PR: its source is unknown. RedLoop Stage 3 stays NO-GO.

## Sources

- https://nginx.org/en/security_advisories.html
- https://nginx.org/en/CHANGES
- Trivy workflow run 44416504118 (this repository, `redloop-image-scan.yml`)
