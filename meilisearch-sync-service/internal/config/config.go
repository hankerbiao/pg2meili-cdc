package config

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
)

const defaultKafkaGroupPrefix = "meilisearch-sync-service"

var kafkaIdentifierPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

// AppConfig 定义了服务运行所需的所有配置项
// 配置通过环境变量读取，支持默认值配置
type AppConfig struct {
	Brokers                []string // Kafka 集群地址列表，多个地址用逗号分隔
	Topics                 []string // 需要订阅的 Kafka Topic 列表（通用）
	CommandTopic           string   // Meilisearch 设置命令 topic
	APIKeyTopic            string   // 开放平台 API Key 变更 topic
	DLQTopic               string   // 失败消息 DLQ topic
	RegionID               string   // 当前部署区域，同一区域的副本必须使用相同值
	GroupPrefix            string   // Kafka 消费者组前缀
	GroupID                string   // 由 GroupPrefix 和 RegionID 派生的有效消费者组 ID
	MeiliHost              string   // Meilisearch 服务地址，格式如 http://localhost:7700
	MeiliAPIKey            string   // Meilisearch API 密钥，为空时表示无需认证
	Debug                  bool
	HTTPAddr               string
	UniDataURL             string // UniData 服务地址，用于代理注册
	AgentIP                string // 代理节点对外 IP
	AgentPort              int    // 代理节点对外端口
	AgentName              string // 代理节点名称/主机名
	AgentVersion           string // 代理程序版本
	AgentMeta              string // 代理扩展元信息（JSON 字符串）
	AgentPublicURL         string // 外部服务访问 Agent 的稳定地址
	AgentRegistrationToken string // Agent 向 UniData 注册时使用的共享凭证
	RedisAddr              string // Redis 地址，默认本机
	RedisPass              string // Redis 密码
	RedisDB                int    // Redis DB
	CORSAllowedOrigins     []string // 允许跨域的 Origin 白名单；为空表示开发模式允许任意（*）
	CORSRequireAllowlist   bool     // 生产环境置 true 时，白名单为空则启动校验失败
	legacyGroupID          string // 仅用于校验遗留 KAFKA_GROUP_ID，禁止其覆盖派生结果
}

// getenv 安全地从环境变量读取配置值
func getenv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

// splitAndTrim 按逗号分割字符串，去除每项首尾空白并过滤空项。
func splitAndTrim(s string) []string {
	parts := strings.Split(s, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

// JoinURL 拼接 base 与 path，规整首尾多余的斜杠。
// base 视为已含 scheme（如 http://host:7700）；如需补 scheme 请先规范化。
func JoinURL(base, path string) string {
	return strings.TrimRight(strings.TrimSpace(base), "/") + "/" + strings.TrimLeft(path, "/")
}

// ConsumerGroupID 为一个区域生成稳定的 Kafka consumer group。
// 同一区域的多个副本会共享 group；不同区域会得到不同的 group，从而各自消费完整消息流。
func ConsumerGroupID(prefix, regionID string) string {
	prefix = strings.TrimSpace(prefix)
	regionID = strings.TrimSpace(regionID)
	if prefix == "" {
		return ""
	}
	if regionID == "" {
		return prefix
	}
	return prefix + "-" + regionID
}

// Validate 校验配置完整性与一致性，启动时调用。
func (c AppConfig) Validate() error {
	// 必填外部服务地址
	if len(c.Brokers) == 0 {
		return fmt.Errorf("KAFKA_BROKERS 未配置")
	}
	if strings.TrimSpace(c.MeiliHost) == "" {
		return fmt.Errorf("MEILI_HOST 未配置")
	}
	if !strings.HasPrefix(c.MeiliHost, "http://") && !strings.HasPrefix(c.MeiliHost, "https://") {
		return fmt.Errorf("MEILI_HOST 必须以 http:// 或 https:// 开头，当前值: %q", c.MeiliHost)
	}

	if err := validateKafkaIdentifier("KAFKA_GROUP_PREFIX", c.GroupPrefix, 128); err != nil {
		return err
	}

	if strings.TrimSpace(c.GroupID) == "" {
		return fmt.Errorf("Kafka consumer group 未配置")
	}
	if len(c.GroupID) > 255 {
		return fmt.Errorf("派生的 Kafka consumer group 超过 255 个字符")
	}

	if strings.TrimSpace(c.RegionID) != "" {
		if err := validateKafkaIdentifier("REGION_ID", c.RegionID, 64); err != nil {
			return err
		}
		expectedGroupID := ConsumerGroupID(c.GroupPrefix, c.RegionID)
		if c.GroupID != expectedGroupID {
			return fmt.Errorf("Kafka consumer group 配置不一致: 期望 %q，实际 %q", expectedGroupID, c.GroupID)
		}
		if c.legacyGroupID != "" && c.legacyGroupID != expectedGroupID {
			return fmt.Errorf(
				"KAFKA_GROUP_ID=%q 与区域化 group %q 不一致；请删除 KAFKA_GROUP_ID，改用 REGION_ID 和 KAFKA_GROUP_PREFIX",
				c.legacyGroupID,
				expectedGroupID,
			)
		}
	}
	if (strings.TrimSpace(c.APIKeyTopic) != "" || strings.TrimSpace(c.UniDataURL) != "" || strings.TrimSpace(c.AgentRegistrationToken) != "") &&
		(strings.TrimSpace(c.UniDataURL) == "" || strings.TrimSpace(c.AgentRegistrationToken) == "") {
		return fmt.Errorf("API Key 鉴权必须配置 UNIDATA_URL 和 AGENT_REGISTRATION_TOKEN")
	}
	if c.CORSRequireAllowlist && len(c.CORSAllowedOrigins) == 0 {
		return fmt.Errorf("CORS_REQUIRE_ALLOWLIST 已启用但 CORS_ALLOWED_ORIGINS 为空；生产环境必须显式配置跨域白名单")
	}
	return nil
}

func validateKafkaIdentifier(name, value string, maxLength int) error {
	value = strings.TrimSpace(value)
	if value == "" {
		return fmt.Errorf("%s 未配置", name)
	}
	if len(value) > maxLength {
		return fmt.Errorf("%s 长度不能超过 %d 个字符", name, maxLength)
	}
	if !kafkaIdentifierPattern.MatchString(value) {
		return fmt.Errorf("%s 只能包含字母、数字、点、下划线和连字符，且必须以字母或数字开头", name)
	}
	return nil
}

// LoadConfig 从环境变量加载所有配置项
func LoadConfig() AppConfig {
	// 支持通过环境变量配置多类 Kafka topics。
	brokersEnv := getenv("KAFKA_BROKERS", "")
	topicEnv := getenv("KAFKA_TOPIC", "pg.public.search_outbox")
	commandTopic := getenv("KAFKA_COMMAND_TOPIC", "meili.commands")
	apiKeyTopic := getenv("KAFKA_API_KEY_TOPIC", "api_keys.events")
	dlqTopic := getenv("KAFKA_DLQ_TOPIC", "meili.dlq")
	regionID := strings.TrimSpace(getenv("REGION_ID", ""))
	groupPrefix := strings.TrimSpace(getenv("KAFKA_GROUP_PREFIX", defaultKafkaGroupPrefix))
	legacyGroupID := strings.TrimSpace(getenv("KAFKA_GROUP_ID", ""))
	groupID := ConsumerGroupID(groupPrefix, regionID)
	if regionID == "" && legacyGroupID != "" {
		groupID = legacyGroupID
	}
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
	corsRequire := getenv("CORS_REQUIRE_ALLOWLIST", "false")
	corsRequireBool := corsRequire == "1" || strings.EqualFold(corsRequire, "true")
	return AppConfig{
		Brokers:                splitAndTrim(brokersEnv),
		Topics:                 splitAndTrim(topicEnv),
		CommandTopic:           commandTopic,
		APIKeyTopic:            apiKeyTopic,
		DLQTopic:               dlqTopic,
		RegionID:               regionID,
		GroupPrefix:            groupPrefix,
		GroupID:                groupID,
		MeiliHost:              getenv("MEILI_HOST", ""),
		MeiliAPIKey:            getenv("MEILI_API_KEY", ""),
		Debug:                  debug,
		HTTPAddr:               getenv("HTTP_ADDR", ":8091"),
		UniDataURL:             getenv("UNIDATA_URL", ""),
		AgentIP:                getenv("AGENT_IP", ""),
		AgentPort:              agentPort,
		AgentName:              getenv("AGENT_NAME", ""),
		AgentVersion:           getenv("AGENT_VERSION", ""),
		AgentMeta:              getenv("AGENT_META", ""),
		AgentPublicURL:         strings.TrimRight(strings.TrimSpace(getenv("AGENT_PUBLIC_URL", "")), "/"),
		AgentRegistrationToken: strings.TrimSpace(getenv("AGENT_REGISTRATION_TOKEN", "")),
		RedisAddr:              getenv("REDIS_ADDR", "127.0.0.1:6379"),
		RedisPass:              getenv("REDIS_PASSWORD", ""),
		RedisDB:                redisDB,
		CORSAllowedOrigins:     splitAndTrim(getenv("CORS_ALLOWED_ORIGINS", "")),
		CORSRequireAllowlist:   corsRequireBool,
		legacyGroupID:          legacyGroupID,
	}
}
