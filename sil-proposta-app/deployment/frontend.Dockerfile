# Build context is the sil-proposta-app/ root (set in docker-compose.yml)
# so we can COPY both frontend/ sources and deployment/nginx.conf.

FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
# `npm install` (not `npm ci`) because there's no package-lock.json yet.
# Once the project stabilises, generate the lock file and switch to `npm ci`
# for deterministic builds.
RUN npm install
COPY frontend/ .
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deployment/nginx.conf /etc/nginx/nginx.conf
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
