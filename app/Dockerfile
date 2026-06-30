# IoTAPS backend image (FastAPI API + background workers)
# Used by both the `fastapi-api` and `workers` Compose services. The runtime
# command differs per service (gunicorn vs supervisord) but the image is shared.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps:
#   - supervisor: worker supervision
#   - build-essential: building any wheels
#   - postgresql-client-16: pg_dump / pg_restore for the admin backup & restore
#     feature. Must match the TimescaleDB server major version (pg16), so we
#     pull the client from the official PGDG apt repo rather than Debian's
#     older default.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        supervisor build-essential curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/supervisor

WORKDIR /srv

# Install Python dependencies first for layer caching.
COPY requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt

# Copy the application package.
COPY . /srv/app

ENV PYTHONPATH=/srv

EXPOSE 8000

# Default command runs the API; the workers service overrides this with
# supervisord in docker-compose.yml.
CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
