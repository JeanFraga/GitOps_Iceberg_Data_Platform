FROM python:3.12-slim-bookworm

LABEL maintainer="GitOps Iceberg Data Platform"
LABEL description="Development container with Python and Java; Terraform, gcloud, Node.js and Claude Code come from devcontainer features"

# ---------- System dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        gnupg \
        jq \
        lsb-release \
        make \
        procps \
        unzip \
        wget \
        default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# ---------- uv (BMad skills run scripts with 'uv run') ----------
RUN pip install --no-cache-dir uv==0.12.23

# ---------- Java ----------
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /workspace

CMD ["/bin/bash"]
