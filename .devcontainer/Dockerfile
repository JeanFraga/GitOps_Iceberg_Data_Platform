FROM python:3.11-slim-bookworm

LABEL maintainer="GitOps Iceberg Data Platform"
LABEL description="Development container with PySpark, dbt, Terraform, and GCP tooling"

# ---------- System dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        gnupg \
        jq \
        lsb-release \
        procps \
        unzip \
        wget \
        default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# ---------- Python dependencies ----------
COPY src/dbt_project/requirements.txt /tmp/dbt-requirements.txt
COPY src/spark_jobs/requirements.txt   /tmp/spark-requirements.txt 2>/dev/null || true

RUN pip install --no-cache-dir \
        pyspark==3.5.1 \
        "dbt-core>=1.7,<2.0" \
        "dbt-bigquery>=1.7,<2.0" \
        pytest \
        black \
        ruff

# ---------- Java (required by PySpark) ----------
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# ---------- Spark environment ----------
ENV SPARK_HOME=/usr/local/lib/python3.11/dist-packages/pyspark
ENV PYSPARK_PYTHON=python3

WORKDIR /workspace

CMD ["/bin/bash"]
