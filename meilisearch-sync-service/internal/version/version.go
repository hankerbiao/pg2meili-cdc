// Package version 提供服务构建版本标识，便于在启动日志与线上环境确认运行版本。
package version

// Version 随发布更新；构建时可用 -ldflags "-X meilisearch-sync-service/internal/version.Version=x.y.z" 覆盖。
var Version = "1.1.0"
