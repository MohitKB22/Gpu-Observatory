FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# Leave empty to call /api on the same origin (served through nginx below).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:1.27-alpine

# Where nginx forwards /api requests. The official image renders templates in
# /etc/nginx/templates with envsubst at startup.
ENV BACKEND_URL=http://backend:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/healthz || exit 1
