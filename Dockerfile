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

# Install Node.js 20 + Claude Code CLI (needed for agent executor)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

# Allow Claude Code CLI to run with --dangerously-skip-permissions as root
ENV IS_SANDBOX=1

# Ensure data directory exists (Railway volume mounts here)
RUN mkdir -p /app/data

COPY start.sh .
RUN chmod +x start.sh
ENTRYPOINT ["./start.sh"]
