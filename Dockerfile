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
    STECH_HEADLESS=true \
    STECH_RUNTIME_DIR=/tmp/stech-product-intelligence
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY legacy_core_bundle/ /tmp/legacy_core_bundle/
# part-11 already contains the final tail of the archive; part-12 is intentionally not consumed.
RUN cat /tmp/legacy_core_bundle/part-0?.b64 /tmp/legacy_core_bundle/part-10.b64 /tmp/legacy_core_bundle/part-11.b64 | base64 -d > /tmp/legacy_core.tar.gz && \
    tar -xzf /tmp/legacy_core.tar.gz -C /app && \
    rm -rf /tmp/legacy_core_bundle /tmp/legacy_core.tar.gz
COPY --from=frontend-build /web/dist ./backend/static
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
