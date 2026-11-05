FROM python:3.13-alpine AS builder
RUN apk update && apk add uv
WORKDIR /app/
COPY pyproject.toml uv.lock README.md ./
COPY ./src ./src
RUN uv sync --no-cache

FROM python:3.13-alpine
WORKDIR /app/
COPY --from=builder /app/.venv /app/.venv
COPY ./src ./src
RUN adduser -D appuser && chown -R appuser:appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["gunicorn", "slot_api.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker"]
