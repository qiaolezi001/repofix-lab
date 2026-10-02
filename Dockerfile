FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy REPOFIX_DATA_DIR=/data
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY examples ./examples
COPY benchmarks ./benchmarks
RUN uv sync --locked --no-dev && mkdir /data && chown 65534:65534 /data
USER 65534:65534
EXPOSE 8765
ENTRYPOINT ["/app/.venv/bin/repofix"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
