# SISI Health — AI conversation service (port 8002).
#
# BUILD CONTEXT IS THE REPO ROOT (see docker-compose.prod.yml):
#     docker build -f ai_service/Dockerfile .
# The AI service imports the backend's `app` package (settings, the deterministic
# rules engine and red-flag matcher) so both trees have to be in the image.
#
# This service NEVER assigns a risk band: /v1/ai/rules/evaluate runs the real
# deterministic engine (non-negotiable 1). Every /v1/ai route is bearer-token gated
# by SISI_AI_INTERNAL_TOKEN.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/pyproject.toml /srv/backend/pyproject.toml
COPY backend/app /srv/backend/app
COPY ai_service/pyproject.toml /srv/ai_service/pyproject.toml
COPY ai_service/ai_service /srv/ai_service/ai_service

RUN pip install --no-cache-dir /srv/backend /srv/ai_service

# Ontology (approved content + guardrail config) is mounted read-only at runtime by
# docker-compose.prod.yml with SISI_ONTOLOGY_DIR=/srv/ontology — it is content, not
# code, and ships independently of the image.

EXPOSE 8002

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
