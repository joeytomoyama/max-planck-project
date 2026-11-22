# One app image: React is built in stage 1 and served by FastAPI in stage 2.

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static
# Default config baked in; docker-compose mounts ./config.yml over it so edits
# only need a restart, not a rebuild.
COPY config.yml ./config.yml
ENV CONFIG_PATH=/app/config.yml STATIC_DIR=/app/static PORT=8000
EXPOSE 8000
CMD ["python", "-m", "app"]
