# Vite 8 requires Node 20.19+; lock to 22 LTS for predictable Railway builds.
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
RUN npm install -g serve@14.2.6

COPY --from=build /app/dist ./dist

EXPOSE 8080
CMD ["sh", "-c", "exec serve -s dist -l tcp://0.0.0.0:${PORT:-8080}"]
