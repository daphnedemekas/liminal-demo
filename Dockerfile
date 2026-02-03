# ── Stage 1: Build frontend ──────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# ── Stage 2: Python runtime ─────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

# Ensure data directory exists (Railway volume mounts here)
RUN mkdir -p /app/data

CMD python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
