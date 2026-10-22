# Dev/test image for a machine that has only Docker.
#
# Official uv image, pinned to the same uv release the service Dockerfiles copy
# (0.13.5) and to CPython 3.12. uv 0.13.5 publishes that combination on Debian
# trixie slim. The tag is a multi-arch manifest (linux/amd64 and linux/arm64).
#
# Tool versions match the GitHub Actions jobs:
# - Terraform 1.17.0: hashicorp/setup-terraform@v3 with terraform_version latest,
#   which resolved to 1.17.0 on the 2026-10-22 main run.
# - tflint v0.55.1
# - checkov 3.3.30: the version `pip install checkov` installed on that run.
FROM ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim

ARG TERRAFORM_VERSION=1.17.0
ARG TFLINT_VERSION=0.55.1
ARG CHECKOV_VERSION=3.3.30

# The checkout is bind-mounted at runtime. Keep the virtualenv off that mount
# so a Linux .venv is never written into the host tree.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}" \
    RUFF_CACHE_DIR=/tmp/ruff-cache \
    PYTHONPYCACHEPREFIX=/tmp/pycache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
      amd64) platform_arch=amd64 ;; \
      arm64) platform_arch=arm64 ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    tmp="$(mktemp -d)"; \
    terraform_zip="terraform_${TERRAFORM_VERSION}_linux_${platform_arch}.zip"; \
    tflint_zip="tflint_linux_${platform_arch}.zip"; \
    curl -fsSL -o "${tmp}/${terraform_zip}" \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/${terraform_zip}"; \
    curl -fsSL -o "${tmp}/terraform.sha256" \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS"; \
    grep "${terraform_zip}" "${tmp}/terraform.sha256" > "${tmp}/terraform.want"; \
    (cd "${tmp}" && sha256sum -c terraform.want); \
    unzip -d /usr/local/bin "${tmp}/${terraform_zip}"; \
    curl -fsSL -o "${tmp}/${tflint_zip}" \
      "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/${tflint_zip}"; \
    curl -fsSL -o "${tmp}/tflint.sha256" \
      "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/checksums.txt"; \
    grep "${tflint_zip}" "${tmp}/tflint.sha256" > "${tmp}/tflint.want"; \
    (cd "${tmp}" && sha256sum -c tflint.want); \
    unzip -d /usr/local/bin "${tmp}/${tflint_zip}"; \
    chmod 755 /usr/local/bin/terraform /usr/local/bin/tflint; \
    rm -rf "${tmp}"; \
    terraform version; \
    tflint --version

WORKDIR /opt/ledgerguard
COPY pyproject.toml uv.lock ./
COPY services/erp_mcp/pyproject.toml services/erp_mcp/pyproject.toml
COPY services/invoice_mcp/pyproject.toml services/invoice_mcp/pyproject.toml
COPY services/matching_agent/pyproject.toml services/matching_agent/pyproject.toml
COPY services/ap_orchestrator/pyproject.toml services/ap_orchestrator/pyproject.toml

RUN uv sync --all-packages --group dev --frozen \
    && env -u UV_PROJECT_ENVIRONMENT uv venv /opt/checkov \
    && env -u UV_PROJECT_ENVIRONMENT uv pip install --python /opt/checkov/bin/python "checkov==${CHECKOV_VERSION}" \
    && ln -s /opt/checkov/bin/checkov /usr/local/bin/checkov \
    && checkov --version

# Install the google ruleset from the GitHub release asset named in .tflint.hcl.
# `tflint --init` looks up that release through the GitHub API, which is easy to
# rate-limit while building. The asset URL is the same file --init would unpack.
COPY .tflint.hcl /tmp/tflint-init/.tflint.hcl
RUN set -eu; \
    version="$(sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' /tmp/tflint-init/.tflint.hcl)"; \
    test -n "${version}"; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
      amd64|arm64) ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    zip="tflint-ruleset-google_linux_${arch}.zip"; \
    tmp="$(mktemp -d)"; \
    curl -fsSL -o "${tmp}/${zip}" \
      "https://github.com/terraform-linters/tflint-ruleset-google/releases/download/v${version}/${zip}"; \
    curl -fsSL -o "${tmp}/checksums.txt" \
      "https://github.com/terraform-linters/tflint-ruleset-google/releases/download/v${version}/checksums.txt"; \
    grep "${zip}" "${tmp}/checksums.txt" > "${tmp}/checksums.want"; \
    (cd "${tmp}" && sha256sum -c checksums.want); \
    dest="/root/.tflint.d/plugins/github.com/terraform-linters/tflint-ruleset-google/${version}"; \
    mkdir -p "${dest}"; \
    unzip -d "${dest}" "${tmp}/${zip}"; \
    chmod 755 "${dest}/tflint-ruleset-google"; \
    rm -rf "${tmp}" /tmp/tflint-init; \
    test -x "${dest}/tflint-ruleset-google"

# Login shells reset PATH. Keep the venv visible for `bash -l` as well as
# the non-login shell Compose uses.
RUN printf '%s\n' 'export PATH="/opt/venv/bin:/usr/local/bin:${PATH}"' > /etc/profile.d/ledgerguard-path.sh

WORKDIR /workspace
CMD ["bash", "scripts/ci_in_docker.sh"]
