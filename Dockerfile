# Linux/amd64 application package. Configure database access at runtime.
FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt requirements-linux.lock ./
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements-linux.lock \
    && python -m pip check \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin speedlocal

COPY app.py ./
COPY apps/ ./apps/
COPY speedlocal/ ./speedlocal/
COPY regions/ ./regions/
COPY schemas/ ./schemas/
COPY tutorials/skaraborg/steps.json ./tutorials/skaraborg/steps.json

ARG APP_REVISION=uncommitted
LABEL org.opencontainers.image.source="https://github.com/gislab-se/speedlocal-GIS" \
      org.opencontainers.image.revision="${APP_REVISION}"

USER 10001:10001
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).read() == b'ok'"]
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
