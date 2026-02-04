package logger

import (
	"io"
	"log"
	"os"
	"path/filepath"

	lumberjack "gopkg.in/natefinch/lumberjack.v2"
)

// debugEnabled 控制是否输出 Debug 日志。
var debugEnabled bool

func InitLogger(debug bool) {
	// 初始化全局日志输出（控制台 + 滚动文件）。
	debugEnabled = debug

	logDir := "logs"
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		log.Printf("创建日志目录失败: %v", err)
		return
	}

	writer := &lumberjack.Logger{
		Filename:   filepath.Join(logDir, "meilisearch-sync-service.log"),
		MaxSize:    1024,
		MaxBackups: 10,
		Compress:   true,
	}

	log.SetOutput(io.MultiWriter(os.Stdout, writer))
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
}

func DebugLogf(format string, v ...interface{}) {
	// 仅在 debugEnabled 时输出调试日志，避免干扰生产日志。
	if !debugEnabled {
		return
	}
	log.Printf("[DEBUG] "+format, v...)
}
