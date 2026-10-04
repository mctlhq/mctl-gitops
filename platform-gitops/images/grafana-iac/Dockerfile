# syntax=docker/dockerfile:1
#
# Runtime for the in-cluster OpenTofu Job that applies the declarative
# Grafana configuration (helm-charts/grafana-iac, mctlhq/mctl-gitops#1601).
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/grafana-iac/Dockerfile
#   image_name=ghcr.io/mctlhq/grafana-iac  image_tag=<tofu version>-<GRAFANA_PROVIDER_VERSION>
#
# Same shape as images/zitadel-iac: the official OpenTofu image is only a
# source for the binary, the provider is baked in as a filesystem mirror and
# registry access is excluded at runtime, so the Job needs no egress beyond
# Grafana and the Kubernetes API (state). To bump OpenTofu, edit the tag AND
# digest on the FROM line; bump the provider together with the root's
# .terraform.lock.hcl.

ARG GRAFANA_PROVIDER_VERSION=4.47.0

FROM ghcr.io/opentofu/opentofu:1.13.1-minimal@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6 AS tofu

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS mirror
ARG GRAFANA_PROVIDER_VERSION
RUN apk add --no-cache ca-certificates
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
WORKDIR /mirror-src
RUN printf 'terraform {\n  required_providers {\n    grafana = {\n      source  = "grafana/grafana"\n      version = "%s"\n    }\n  }\n}\n' "${GRAFANA_PROVIDER_VERSION}" > versions.tf \
 && tofu providers mirror -platform=linux_amd64 /usr/share/tofu/providers \
 && test -n "$(find /usr/share/tofu/providers/registry.opentofu.org/grafana/grafana -name '*.zip')"

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
ARG GRAFANA_PROVIDER_VERSION
LABEL org.opencontainers.image.title="grafana-iac" \
      org.opencontainers.image.description="OpenTofu with the grafana ${GRAFANA_PROVIDER_VERSION} provider pre-installed" \
      org.opencontainers.image.source="https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/images/grafana-iac" \
      org.opencontainers.image.licenses="MPL-2.0"
RUN apk add --no-cache ca-certificates
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
COPY --from=mirror /usr/share/tofu/providers /usr/share/tofu/providers
COPY --from=mirror /mirror-src/versions.tf /usr/share/tofu/versions.tf
# Only the mirror, no `direct` block: no network installation at all.
RUN printf 'provider_installation {\n  filesystem_mirror {\n    path = "/usr/share/tofu/providers"\n  }\n}\n' > /etc/tofurc \
 && tofu version
ENV TF_CLI_CONFIG_FILE=/etc/tofurc \
    TF_IN_AUTOMATION=1 \
    TF_INPUT=0
# Prove at build time that init works with no network at all.
RUN --network=none mkdir /tmp/offline-check && cd /tmp/offline-check \
 && cp /usr/share/tofu/versions.tf . \
 && tofu init -backend=false \
 && tofu providers | grep -q "grafana/grafana\] ${GRAFANA_PROVIDER_VERSION}" \
 && cd / && rm -rf /tmp/offline-check
RUN adduser -D -u 65532 -h /home/tofu tofu
USER 65532
WORKDIR /home/tofu
ENTRYPOINT ["/usr/local/bin/tofu"]
