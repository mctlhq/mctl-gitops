# syntax=docker/dockerfile:1
#
# Non-root tool image for Argo Workflow steps that run in tenant namespaces
# (deploy-service, preview-deploy, provision-database, retire-service,
# smoke-test, tpl-git-commit, tpl-vault-write). Those steps install packages
# with `apk add` and drop yq/helm into /usr/local/bin at runtime, which needs
# root, so they cannot run under Pod Security "restricted" (handoff audit,
# block B steps 2-3). Everything they install is baked in here instead.
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/mctl-workflow-tools/Dockerfile
#   image_name=ghcr.io/mctlhq/mctl-workflow-tools  team_name=platform
#   image_tag=<alpine>-<n>, bumped on every change to this file
#
# Downloaded binaries are pinned by sha256: these steps carry the gitops
# deploy key and Vault tokens. yq matches the version and digest the
# templates verify today.

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8

ARG YQ_VERSION=v4.52.4
ARG YQ_SHA256=0c4d965ea944b64b8fddaf7f27779ee3034e5693263786506ccd1c120f184e8c
ARG HELM_VERSION=v3.16.4
ARG HELM_SHA256=fc307327959aa38ed8f9f7e66d45492bb022a66c3e5da6063958254b9767d179
ARG KUBECTL_VERSION=v1.33.12
ARG KUBECTL_SHA256=fe80ae4133b44fa2077db4af144e80765eb1b3b2eede55fbff6933c4374d8c6e

LABEL org.opencontainers.image.title="mctl-workflow-tools" \
      org.opencontainers.image.description="Non-root tools for mctl Argo Workflow steps: git, ssh, curl, openssl, python3, jq, yq, helm, kubectl" \
      org.opencontainers.image.source="https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/images/mctl-workflow-tools"

RUN apk add --no-cache \
      bash ca-certificates curl git jq openssh-client openssl python3 py3-yaml

RUN set -eu; cd /tmp; \
    curl -fsSL --retry 5 -o yq "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_amd64"; \
    echo "${YQ_SHA256}  yq" | sha256sum -c -; \
    install -m 0755 yq /usr/local/bin/yq; \
    curl -fsSL --retry 5 -o helm.tgz "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"; \
    echo "${HELM_SHA256}  helm.tgz" | sha256sum -c -; \
    tar -xzf helm.tgz linux-amd64/helm; \
    install -m 0755 linux-amd64/helm /usr/local/bin/helm; \
    curl -fsSL --retry 5 -o kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"; \
    echo "${KUBECTL_SHA256}  kubectl" | sha256sum -c -; \
    install -m 0755 kubectl /usr/local/bin/kubectl; \
    rm -rf /tmp/*; \
    yq --version && helm version --short && kubectl version --client

# uid/gid 1000 is the workflow convention (cwft-mctl-agents-run). Templates
# still pin runAsUser explicitly; kubelet checks runAsNonRoot against a
# numeric user only. HOME is /tmp itself (mode 1777), so ~/.ssh,
# `git config --global` and the helm/kubectl caches work for any uid,
# including one the image has no passwd entry for.
RUN addgroup -g 1000 workflow && adduser -D -H -u 1000 -G workflow -h /tmp workflow
ENV HOME=/tmp
USER 1000:1000
WORKDIR /tmp
