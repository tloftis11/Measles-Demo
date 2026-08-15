# ─── Stage 1: Build React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

RUN npm install -g pnpm

COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .
# Empty VITE_API_URL = same-origin (FastAPI serves the frontend in production)
RUN VITE_API_URL="" pnpm build

# ─── Stage 2: Production runtime ────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Install Python deps first (layer-cached until pyproject.toml changes).
# --no-dev skips pytest etc.; geopandas/shapely are optional extras not needed at runtime.
WORKDIR /app/backend
COPY backend/pyproject.toml .
RUN uv sync --no-dev

# Copy backend source
COPY backend/ .

# Copy pre-seeded data (DuckDB + GeoJSON baked into image)
WORKDIR /app
COPY data/ ./data/

# Copy React build output — FastAPI serves it via StaticFiles
COPY --from=frontend-builder /app/frontend/dist ./static/

EXPOSE 8000

WORKDIR /app/backend
# Render injects $PORT; fall back to 8000 for local docker run
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
