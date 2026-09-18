FROM node:20-alpine AS build

# Alpine apk 国内源
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories

WORKDIR /app

COPY frontend/package.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm install

COPY frontend/ .

ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

FROM nginx:1.27-alpine

ARG LORECHAT_VERSION=0.0.0
ARG LORECHAT_REVISION=""
ARG LORECHAT_COMMITS_AHEAD=0
ARG LORECHAT_CHANNEL=development
ARG LORECHAT_DIRTY=0
LABEL org.opencontainers.image.title="Lore Chat web" \
      org.opencontainers.image.version="$LORECHAT_VERSION" \
      org.opencontainers.image.revision="$LORECHAT_REVISION"

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
