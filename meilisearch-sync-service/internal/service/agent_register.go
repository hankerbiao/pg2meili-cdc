package service

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"meilisearch-sync-service/internal/config"
)

type agentRegisterPayload struct {
	IP       string                 `json:"ip"`
	Port     int                    `json:"port"`
	Hostname string                 `json:"hostname,omitempty"`
	Version  string                 `json:"version,omitempty"`
	Meta     map[string]interface{} `json:"meta,omitempty"`
}

// RegisterAgent 尝试向 UniData 注册代理节点信息。
// 若 UNIDATA_URL 未配置，则直接跳过。
func RegisterAgent(cfg config.AppConfig) {
	if strings.TrimSpace(cfg.UniDataURL) == "" {
		log.Printf("未配置 UNIDATA_URL，跳过代理注册")
		return
	}

	agentIP := cfg.AgentIP
	if agentIP == "" {
		if ip, err := detectLocalIP(); err == nil {
			agentIP = ip
		}
	}

	agentPort := cfg.AgentPort
	if agentPort == 0 {
		if p, err := parsePort(cfg.HTTPAddr); err == nil {
			agentPort = p
		}
	}

	if agentIP == "" || agentPort == 0 {
		log.Printf("代理注册信息不完整（AGENT_IP/HTTP_ADDR），跳过注册")
		return
	}

	hostname := cfg.AgentName
	if hostname == "" {
		if h, err := os.Hostname(); err == nil {
			hostname = h
		}
	}

	var meta map[string]interface{}
	if cfg.AgentMeta != "" {
		if err := json.Unmarshal([]byte(cfg.AgentMeta), &meta); err != nil {
			log.Printf("AGENT_META 解析失败，忽略该字段: %v", err)
		}
	}
	if meta == nil {
		meta = make(map[string]interface{})
	}
	publicURL := cfg.AgentPublicURL
	if publicURL == "" {
		publicURL = fmt.Sprintf("http://%s:%d", agentIP, agentPort)
	}
	meta["region"] = cfg.RegionID
	meta["base_url"] = publicURL
	if _, ok := meta["weight"]; !ok {
		meta["weight"] = 100
	}

	payload := agentRegisterPayload{
		IP:       agentIP,
		Port:     agentPort,
		Hostname: hostname,
		Version:  cfg.AgentVersion,
		Meta:     meta,
	}

	body, _ := json.Marshal(payload)
	url := config.JoinURL(normalizeURL(cfg.UniDataURL), "api/v1/agents/register")

	client := &http.Client{Timeout: 5 * time.Second}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		log.Printf("构造代理注册请求失败: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Agent-Token", cfg.AgentRegistrationToken)

	resp, err := client.Do(req)
	if err != nil {
		log.Printf("代理注册请求失败: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		log.Printf("代理注册成功 region=%s base_url=%s", cfg.RegionID, publicURL)
		return
	}
	log.Printf("代理注册失败 status=%d", resp.StatusCode)
}

func parsePort(addr string) (int, error) {
	addr = strings.TrimSpace(addr)
	if addr == "" {
		return 0, strconv.ErrSyntax
	}
	// 兼容 ":8091" 或 "0.0.0.0:8091"
	if strings.HasPrefix(addr, ":") {
		return strconv.Atoi(strings.TrimPrefix(addr, ":"))
	}
	_, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(portStr)
}

func detectLocalIP() (string, error) {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "", err
	}
	for _, addr := range addrs {
		var ip net.IP
		switch v := addr.(type) {
		case *net.IPNet:
			ip = v.IP
		case *net.IPAddr:
			ip = v.IP
		}
		if ip == nil || ip.IsLoopback() {
			continue
		}
		ip = ip.To4()
		if ip == nil {
			continue
		}
		return ip.String(), nil
	}
	return "", fmt.Errorf("no suitable local IP address found")
}

func normalizeURL(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return raw
	}
	if strings.HasPrefix(raw, "http://") || strings.HasPrefix(raw, "https://") {
		return raw
	}
	return "http://" + raw
}
