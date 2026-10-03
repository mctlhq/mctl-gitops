# syntax=docker/dockerfile:1
#
# Runtime for the in-cluster OpenTofu Job that applies the declarative ZITADEL
# configuration (mctlhq/mctl-gitops#1520).
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/zitadel-iac/Dockerfile
#   image_name=ghcr.io/mctlhq/zitadel-iac  image_tag=<TOFU_VERSION>-<ZITADEL_PROVIDER_VERSION>
#
# The official OpenTofu image is meant to have its binary copied out, not to
# be run, so it is used only as a source here. The zitadel provider is baked
# in as a filesystem mirror and registry access is excluded at runtime: the
# Job then needs no egress beyond the ZITADEL API, and what it runs is exactly
# what this file pins. Bump TOFU_VERSION with its digest, and the provider
# version together with the root's .terraform.lock.hcl.

ARG TOFU_VERSION=1.13.1
ARG ZITADEL_PROVIDER_VERSION=3.8.7

FROM ghcr.io/opentofu/opentofu:1.13.1-minimal@sha256:dfbc3f0a8bed0adfa2cf49ff418f158afe24080eea6d6e748db8799fc4553db6 AS tofu

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS mirror
ARG ZITADEL_PROVIDER_VERSION
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
WORKDIR /mirror-src
RUN printf 'terraform {\n  required_providers {\n    zitadel = {\n      source  = "zitadel/zitadel"\n      version = "%s"\n    }\n  }\n}\n' "${ZITADEL_PROVIDER_VERSION}" > versions.tf \
 && tofu providers mirror -platform=linux_amd64 /usr/share/tofu/providers \
 && test -n "$(find /usr/share/tofu/providers -name '*.zip')"

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
ARG TOFU_VERSION
ARG ZITADEL_PROVIDER_VERSION
LABEL org.opencontainers.image.title="zitadel-iac" \
      org.opencontainers.image.description="OpenTofu ${TOFU_VERSION} with the zitadel provider ${ZITADEL_PROVIDER_VERSION} pre-installed" \
      org.opencontainers.image.source="https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/images/zitadel-iac" \
      org.opencontainers.image.licenses="MPL-2.0"
RUN apk add --no-cache ca-certificates
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu
COPY --from=mirror /usr/share/tofu/providers /usr/share/tofu/providers
RUN printf 'provider_installation {\n  filesystem_mirror {\n    path    = "/usr/share/tofu/providers"\n    include = ["registry.opentofu.org/zitadel/*"]\n  }\n  direct {\n    exclude = ["registry.opentofu.org/*/*"]\n  }\n}\n' > /etc/tofurc \
 && tofu version
ENV TF_CLI_CONFIG_FILE=/etc/tofurc \
    TF_IN_AUTOMATION=1 \
    TF_INPUT=0
# Non-root, with a writable HOME for tofu's plugin cache and .terraform.d.
RUN adduser -D -u 65532 -h /home/tofu tofu
USER 65532
WORKDIR /home/tofu
ENTRYPOINT ["/usr/local/bin/tofu"]
