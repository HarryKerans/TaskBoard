# ---- Build React frontend ----
FROM node:22-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---- Final Home Assistant add-on image ----
FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock /app/backend/

RUN cd /app/backend && uv sync --frozen --no-dev

COPY backend/ /app/backend/

COPY --from=frontend-build /frontend/build /app/backend/frontend_dist

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]