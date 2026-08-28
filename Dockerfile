FROM node:22-bookworm-slim AS frontend-build
WORKDIR /web
RUN apt-get update && apt-get install -y --no-install-recommends xz-utils ca-certificates && rm -rf /var/lib/apt/lists/*
COPY frontend_bundle/ /tmp/frontend_bundle/
RUN cat /tmp/frontend_bundle/part-*.b64 | base64 -d > /tmp/frontend.tar.xz && \
    tar -xJf /tmp/frontend.tar.xz -C /web && \
    rm -rf /tmp/frontend_bundle /tmp/frontend.tar.xz
RUN npm install --no-audit --no-fund
RUN npm run build

FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STECH_HEADLESS=false \
    STECH_RUNTIME_DIR=/tmp/stech-product-intelligence
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY legacy_core_bundle_v2/ /tmp/legacy_core_bundle/
RUN cat /tmp/legacy_core_bundle/part-*.b64 | base64 -d > /tmp/legacy_core.tar.gz && \
    gzip -t /tmp/legacy_core.tar.gz && \
    tar -xzf /tmp/legacy_core.tar.gz -C /app && \
    python -c "import hashlib; from pathlib import Path; root=Path('/app/backend/legacy_core'); files=sorted(root.glob('*.py')); h=hashlib.sha256(); [h.update(p.name.encode()+b'\\0'+p.read_bytes()+b'\\0') for p in files]; got=h.hexdigest(); assert len(files)==26 and got=='79c347b60206149cfbdaeb26162fb5b1644b0a38f5feeb5a3cafc17dded6e01b', f'legacy_core corrupto/incompleto: files={len(files)} sha256={got}'; print('LEGACY_CORE_26_FILES_SHA256_OK')" && \
    python -m compileall -q /app/backend/legacy_core && \
    rm -rf /tmp/legacy_core_bundle /tmp/legacy_core.tar.gz
COPY --from=frontend-build /web/dist ./backend/static
EXPOSE 8080
CMD ["sh", "-c", "xvfb-run -a uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
