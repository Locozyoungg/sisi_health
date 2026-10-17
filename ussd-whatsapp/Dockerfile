# SISI Health — USSD + WhatsApp gateway (port 8001).
#
# BUILD CONTEXT IS THE REPO ROOT (see docker-compose.prod.yml):
#     docker build -f ussd-whatsapp/Dockerfile .
# The gateway imports the backend's `app` package (settings, envelope key provider and
# the deterministic rules engine), so both trees have to be in the image; a
# `./ussd-whatsapp` context could not reach `backend/`.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Backend first: the gateway depends on it for app.config, app.crypto and app.rules.
COPY backend/pyproject.toml /srv/backend/pyproject.toml
COPY backend/app /srv/backend/app
COPY ussd-whatsapp/pyproject.toml /srv/ussd-whatsapp/pyproject.toml
COPY ussd-whatsapp/gateway /srv/ussd-whatsapp/gateway

RUN pip install --no-cache-dir /srv/backend /srv/ussd-whatsapp

# The ontology (rules, red-flag scripts, content) is deployment content, not code:
# docker-compose.prod.yml mounts it read-only at /srv/ontology and points
# SISI_ONTOLOGY_DIR at it, so content can be updated without rebuilding the image.
# /srv/ontology is created here only so a missing mount fails loudly at load time
# instead of the container refusing to start.

EXPOSE 8001

# No --reload, no dev flags: one worker per container, scaled by compose replicas.
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8001"]
