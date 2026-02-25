FROM hashicorp/terraform:1.8.0-rc2 as terraform
FROM ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux as beautifier

# Use full python image (not slim) - slim lacks setuptools/pkg_resources needed by Semgrep/OpenTelemetry
FROM python:3.12

ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENV=1
ENV MEMGRAPH_URI=bolt://localhost:7687

RUN apt-get update && apt-get install -y default-jdk graphviz

COPY --from=terraform /bin/terraform /usr/local/bin/terraform
COPY --from=beautifier /usr/local/bin/terraform-graph-beautifier /usr/local/bin/terraform-graph-beautifier

RUN mkdir /output
RUN mkdir /project
WORKDIR /app

COPY . /app

# Upgrade pip first to ensure latest package resolution
RUN pip install --upgrade pip

# Semgrep/OpenTelemetry require pkg_resources (from setuptools). 
# IMPORTANT: setuptools 82.0.0+ removed pkg_resources entirely!
# requirements.txt already pins setuptools<82.0.0, but install it first to ensure
# it's available before other packages that might depend on it
RUN pip install --no-cache-dir "setuptools<82.0.0,>=65.0.0" && \
    pip install --no-cache-dir -r requirements.txt && \
    python -c "import pkg_resources; print(f'✓ setuptools version: {pkg_resources.get_distribution(\"setuptools\").version}')" && \
    python -c "import pkg_resources; print(f'✓ pkg_resources available: {pkg_resources.__file__}')"

ENTRYPOINT ["python", "main.py"]

CMD ["--help"]