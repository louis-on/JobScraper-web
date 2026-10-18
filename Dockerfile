# JobScraper web — image unique : front React compilé + API FastAPI.
# Déployable telle quelle sur un hébergeur Docker gratuit
# (Hugging Face Spaces, Render…) ou sur un VPS via docker compose.

# --- Étape 1 : compilation du front ---
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Étape 2 : application Python ---
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    JOBSCRAPER_FRONTEND_DIST=/app/frontend/dist

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install ".[web]"

COPY --from=frontend /build/dist ./frontend/dist

# Utilisateur non-root (recommandé, et attendu par Hugging Face Spaces)
RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 7860
CMD ["jobscraper-web"]
