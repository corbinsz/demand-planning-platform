# One image for the hosted demo: API and the built website on the same URL.
# Render (or any host) runs this. A laptop does not need Docker.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./static

ENV DEMO_MODE=true \
    AUTO_SEED=true \
    USE_SQLITE=true \
    SQLITE_PATH=/tmp/inventory.db \
    WARM_FORECASTS=true \
    SCHEDULER_ENABLED=false \
    SECRET_KEY=demo-only-not-for-production \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
