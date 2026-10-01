FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY docs ./docs

RUN python -m pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "examples/06_observability_server.py", "--host", "0.0.0.0", "--port", "8080"]
