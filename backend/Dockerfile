FROM python:3.12-slim

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
# alembic.ini declares `script_location = migrations` — the migration package lives
# in ./migrations (there is no ./alembic directory), so this must match it or
# `docker compose run backend alembic upgrade head` has nothing to run.
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
