FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/meilisearch-sync-service ./main.go

FROM alpine:3.21
RUN addgroup -S melidata && adduser -S -G melidata melidata
WORKDIR /app
COPY --from=build /out/meilisearch-sync-service /app/meilisearch-sync-service
USER melidata
ENTRYPOINT ["/app/meilisearch-sync-service"]
