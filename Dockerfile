ARG PYTHON_IMAGE=python:3.12-slim
ARG PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple

FROM ${PYTHON_IMAGE} AS sdk-builder
WORKDIR /build/python-sdk
COPY python-sdk/pyproject.toml python-sdk/README.md ./
COPY python-sdk/src ./src
COPY python-sdk/scripts ./scripts
RUN python scripts/build_source_zip.py --output-dir /out


FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS uv-source


FROM ${PYTHON_IMAGE} AS python-builder
ARG PYTHON_PACKAGE_INDEX
COPY --from=uv-source /usr/local/bin/uv /usr/local/bin/uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_INDEX_URL=${PYTHON_PACKAGE_INDEX}
WORKDIR /build/UniData
COPY UniData/pyproject.toml UniData/uv.lock UniData/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project \
      --format requirements-txt --output-file /tmp/requirements.txt \
    && uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
      --index-url "${PYTHON_PACKAGE_INDEX}" \
      --require-hashes --requirements /tmp/requirements.txt
COPY UniData/app ./app


FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/unidata/UniData \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_SDK_ARCHIVE=/opt/unidata/downloads/unidata-sdk.zip \
    LOG_FILE_ENABLED=false

RUN groupadd --system --gid 10001 unidata \
    && useradd --system --uid 10001 --gid unidata --home-dir /opt/unidata unidata \
    && mkdir -p /opt/unidata/UniData /opt/unidata/downloads /opt/unidata/logs \
    && chown -R unidata:unidata /opt/unidata

COPY --from=python-builder /opt/venv /opt/venv
COPY --chown=unidata:unidata UniData/app /opt/unidata/UniData/app
COPY --chown=unidata:unidata UniData/scripts /opt/unidata/UniData/scripts
COPY --chown=unidata:unidata UniData/migrations /opt/unidata/UniData/migrations
COPY --chown=unidata:unidata UniData/pyproject.toml UniData/README.md /opt/unidata/UniData/
COPY --from=sdk-builder --chown=unidata:unidata /out /opt/unidata/downloads

WORKDIR /opt/unidata/UniData
USER unidata
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
