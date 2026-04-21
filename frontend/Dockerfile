# syntax=docker/dockerfile:1.7
# Multi-stage: `dev` target for local Compose, `prod` target for GHCR.

FROM node:20-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# ---------- dev ----------
FROM base AS dev
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]

# ---------- build (shared by prod) ----------
FROM base AS build
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- prod ----------
FROM base AS prod
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nodejs && adduser -S -u 1001 -G nodejs nextjs
# This project has no /frontend/public directory, so skip copying it.
# If static assets are added later, restore: COPY --from=build --chown=nextjs:nodejs /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next ./.next
COPY --from=build --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=build --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=build --chown=nextjs:nodejs /app/next.config.mjs ./next.config.mjs
USER nextjs
EXPOSE 3000
CMD ["npm", "run", "start"]
