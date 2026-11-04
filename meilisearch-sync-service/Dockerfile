FROM golang:1.25-alpine AS build
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG all_proxy
ARG no_proxy
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    ALL_PROXY=$ALL_PROXY \
    NO_PROXY=$NO_PROXY \
    http_proxy=$http_proxy \
    https_proxy=$https_proxy \
    all_proxy=$all_proxy \
    no_proxy=$no_proxy
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/meilisearch-sync-service ./main.go

FROM alpine:3.21
RUN addgroup -S melidata && adduser -S -G melidata melidata
WORKDIR /app
COPY --from=build /out/meilisearch-sync-service /app/meilisearch-sync-service
# 容器以非 root 用户运行，必须预建可写日志目录，否则启动时 mkdir logs 会 permission denied
RUN mkdir -p /app/logs && chown melidata:melidata /app/logs
USER melidata
ENTRYPOINT ["/app/meilisearch-sync-service"]
