FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN pip install --no-cache-dir uv==0.12.23 && UV_PROJECT_ENVIRONMENT=/app/.venv-m uv sync --locked
COPY platform_m /app/platform_m
COPY scripts /app/scripts
COPY dist /app/dist
RUN mkdir -p /app/.local/m && chown -R 65534:65534 /app/.local
USER 65534:65534
ENV PATH="/app/.venv-m/bin:${PATH}"
CMD ["python", "scripts/serve_m.py", "--port", "8767"]
