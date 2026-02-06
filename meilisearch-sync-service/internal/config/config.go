package config

import (
	"os"
	"strconv"
	"strings"
)

// AppConfig 定义了服务运行所需的所有配置项
// 配置通过环境变量读取，支持默认值配置
type AppConfig struct {
	Brokers      []string // Kafka 集群地址列表，多个地址用逗号分隔
	Topics       []string // 需要订阅的 Kafka Topic 列表（通用）
	CommandTopic string   // Meilisearch 设置命令 topic
	RevokeTopic  string   // Token 撤销广播 topic
	DLQTopic     string   // 失败消息 DLQ topic
	GroupID      string   // Kafka 消费者组 ID，同一组内的消费者会协同消费分区
	MeiliHost    string   // Meilisearch 服务地址，格式如 http://localhost:7700
	MeiliAPIKey  string   // Meilisearch API 密钥，为空时表示无需认证
	Debug        bool
	JWTSecret    string
	HTTPAddr     string
	UniDataURL   string // UniData 服务地址，用于代理注册
	AgentIP      string // 代理节点对外 IP
	AgentPort    int    // 代理节点对外端口
	AgentName    string // 代理节点名称/主机名
	AgentVersion string // 代理程序版本
	AgentMeta    string // 代理扩展元信息（JSON 字符串）
	RedisAddr    string // Redis 地址，默认本机
	RedisPass    string // Redis 密码
	RedisDB      int    // Redis DB
	RevokeTTL    int    // 撤销缓存 TTL（秒）
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
	// 支持通过环境变量配置多类 Kafka topics。
	brokersEnv := getenv("KAFKA_BROKERS", "10.17.154.252:9092")
	topicEnv := getenv("KAFKA_TOPIC", "test_case.public.test_cases")
	commandTopic := getenv("KAFKA_COMMAND_TOPIC", "meili.commands")
	revokeTopic := getenv("KAFKA_TOKEN_REVOKE_TOPIC", "token.revocations")
	dlqTopic := getenv("KAFKA_DLQ_TOPIC", "meili.dlq")
	debugEnv := getenv("DEBUG", "false")
	debug := debugEnv == "1" || strings.EqualFold(debugEnv, "true")
	agentPortEnv := getenv("AGENT_PORT", "0")
	agentPort := 0
	if v, err := strconv.Atoi(agentPortEnv); err == nil {
		agentPort = v
	}
	redisDB := 0
	if v, err := strconv.Atoi(getenv("REDIS_DB", "0")); err == nil {
		redisDB = v
	}
	revokeTTL := 0
	if v, err := strconv.Atoi(getenv("REVOKE_CACHE_TTL_SECONDS", "0")); err == nil {
		revokeTTL = v
	}

	return AppConfig{
		Brokers:      strings.Split(brokersEnv, ","),
		Topics:       strings.Split(topicEnv, ","),
		CommandTopic: commandTopic,
		RevokeTopic:  revokeTopic,
		DLQTopic:     dlqTopic,
		GroupID:      getenv("KAFKA_GROUP_ID", "meilisearch-sync-service"),
		MeiliHost:    getenv("MEILI_HOST", "http://10.17.154.252:7700"),
		MeiliAPIKey:  getenv("MEILI_API_KEY", ""),
		Debug:        debug,
		JWTSecret:    getenv("JWT_SECRET", "dYAj4kPbhIdCM35XhcDW9HJX53xT3iux"),
		HTTPAddr:     getenv("HTTP_ADDR", ":8091"),
		UniDataURL:   getenv("UNIDATA_URL", ""),
		AgentIP:      getenv("AGENT_IP", ""),
		AgentPort:    agentPort,
		AgentName:    getenv("AGENT_NAME", ""),
		AgentVersion: getenv("AGENT_VERSION", ""),
		AgentMeta:    getenv("AGENT_META", ""),
		RedisAddr:    getenv("REDIS_ADDR", "127.0.0.1:6379"),
		RedisPass:    getenv("REDIS_PASSWORD", ""),
		RedisDB:      redisDB,
		RevokeTTL:    revokeTTL,
	}
}
