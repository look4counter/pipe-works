ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ARG PIPEWORKS_EXTRAS=

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY docs ./docs

RUN if [ -n "${PIPEWORKS_EXTRAS}" ]; then \
      python -m pip install --no-cache-dir ".[${PIPEWORKS_EXTRAS}]"; \
    else \
      python -m pip install --no-cache-dir .; \
    fi

EXPOSE 8080
CMD ["python", "examples/06_observability_server.py", "--host", "0.0.0.0", "--port", "8080"]
