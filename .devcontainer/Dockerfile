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
    && rm -rf /var/lib/apt/lists/*

# ---------- Java 21 (Dataproc runtime 3.0, AD-17; bookworm main ships only 17) ----------
RUN wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /usr/share/keyrings/adoptium.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb bookworm main" \
        > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update && apt-get install -y --no-install-recommends temurin-21-jdk \
    && rm -rf /var/lib/apt/lists/*

# ---------- uv (BMad skills run scripts with 'uv run') ----------
RUN pip install --no-cache-dir uv==0.12.23

# ---------- Java ----------
ENV JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /workspace

CMD ["/bin/bash"]
