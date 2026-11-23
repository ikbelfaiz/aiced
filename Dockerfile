FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /frontend/dist ./frontend_dist/
RUN DJANGO_SECRET_KEY=build-only-secret-key-not-used-in-runtime-123456 \
    python manage.py collectstatic --noinput
RUN useradd --create-home app && chown -R app:app /app
USER app
EXPOSE 10000
CMD ["sh", "-c", "python manage.py prepare_render && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120"]
