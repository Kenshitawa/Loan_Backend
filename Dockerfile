FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "if [ \"${MIGRATE_TO_SUPABASE:-}\" = \"1\" ]; then DATABASE_URL=\"$SUPABASE_DATABASE_URL\" alembic upgrade head && python scripts/migrate_to_supabase.py; fi && alembic upgrade head && python scripts/bootstrap_admin.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
