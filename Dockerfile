FROM hashicorp/terraform:1.8.0-rc2 as terraform
FROM ghcr.io/pcasteran/terraform-graph-beautifier:0.3.4-linux as beautifier

FROM python:3.12-slim

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

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "main.py"]

CMD ["--help"]