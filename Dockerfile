# ── Stage 1: build Svelte frontend ────────────────────────────────────────────
FROM node:26-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build
# Output lands in /build/backend/static (per vite.config.js outDir)


# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.14-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /build/backend/static ./static

# Run as a non-root user to limit blast radius if the process is compromised.
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8765

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
