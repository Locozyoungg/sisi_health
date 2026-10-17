# SISI Health — staff console (React + Vite), served as static files by nginx.
#
# BUILD CONTEXT IS ./web (see docker-compose.prod.yml): `docker build ./web`.
# Validated by `npm run build` (tsc -b && vite build), so a type error fails the
# image build rather than shipping a broken bundle.

# ---- stage 1: build ----
FROM node:22-alpine AS build

WORKDIR /app

# Lockfile-installed dependencies first: this layer is cached until package-lock.json
# changes, so application edits do not re-download node_modules.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src

RUN npm run build

# ---- stage 2: serve ----
FROM nginx:1.27-alpine

# nginx only serves the SPA; TLS and path routing to the API live in Caddy
# (deploy/Caddyfile), which reverse-proxies / -> web:80.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
