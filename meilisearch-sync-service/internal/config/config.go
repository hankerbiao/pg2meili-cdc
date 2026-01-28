package config

import (
	"os"
	"strings"
)

// AppConfig 定义了服务运行所需的所有配置项
// 配置通过环境变量读取，支持默认值配置
type AppConfig struct {
	Brokers     []string // Kafka 集群地址列表，多个地址用逗号分隔
	Topics      []string // 需要订阅的 Kafka Topic 列表，用于消费 Debezium CDC 消息
	GroupID     string   // Kafka 消费者组 ID，同一组内的消费者会协同消费分区
	MeiliHost   string   // Meilisearch 服务地址，格式如 http://localhost:7700
	MeiliAPIKey string   // Meilisearch API 密钥，为空时表示无需认证
	MeiliIndex  string   // 基础索引名称，实际索引名可能根据配置动态生成
	Debug       bool
	JWTSecret   string
	HTTPAddr    string
}

// getenv 安全地从环境变量读取配置值
func getenv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

// LoadConfig 从环境变量加载所有配置项
func LoadConfig() AppConfig {
	brokersEnv := getenv("KAFKA_BROKERS", "10.17.154.252:9092")
	topicEnv := getenv("KAFKA_TOPIC", "test_case.public.test_cases")
	debugEnv := getenv("DEBUG", "false")
	debug := debugEnv == "1" || strings.EqualFold(debugEnv, "true")

	return AppConfig{
		Brokers:     strings.Split(brokersEnv, ","),
		Topics:      strings.Split(topicEnv, ","),
		GroupID:     getenv("KAFKA_GROUP_ID", "meilisearch-sync-service"),
		MeiliHost:   getenv("MEILI_HOST", "http://10.17.154.252:7700"),
		MeiliAPIKey: getenv("MEILI_API_KEY", ""),
		MeiliIndex:  getenv("MEILI_INDEX", "testcases"),
		Debug:       debug,
		JWTSecret:   getenv("JWT_SECRET", "please-change-me-in-prod"),
		HTTPAddr:    getenv("HTTP_ADDR", ":8091"),
	}
}
