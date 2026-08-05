FROM python:3.11-slim-bookworm

LABEL maintainer="GitOps Iceberg Data Platform"
LABEL description="Development container with PySpark, dbt, and Java; Terraform and gcloud come from devcontainer features"

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

# ---------- Python dependencies (single source: the requirements files) ----------
COPY src/dbt_project/requirements.txt /tmp/dbt-requirements.txt
COPY src/spark_jobs/requirements.txt /tmp/spark-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dbt-requirements.txt -r /tmp/spark-requirements.txt \
    && rm /tmp/dbt-requirements.txt /tmp/spark-requirements.txt

# ---------- Java (required by PySpark) ----------
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV PYSPARK_PYTHON=python3

WORKDIR /workspace

CMD ["/bin/bash"]
