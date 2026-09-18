FROM node:22.19.0-alpine AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.json ./
RUN pnpm install --frozen-lockfile
COPY index.html ./
COPY src ./src
RUN pnpm run check && pnpm run build

FROM nginx:1.29.1-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
