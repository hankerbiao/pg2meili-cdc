package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// AppIdentity 表示从 JWT 中解析出的应用身份信息
type AppIdentity struct {
	AppName string
	Scopes  []string
	JTI     string
}

// RequireScopes 校验当前身份是否具备所需权限
func RequireScopes(identity AppIdentity, required []string) error {
	if len(required) == 0 {
		return nil
	}
	scopeSet := make(map[string]struct{}, len(identity.Scopes))
	for _, s := range identity.Scopes {
		scopeSet[s] = struct{}{}
	}
	for _, s := range required {
		if _, ok := scopeSet[s]; !ok {
			return fmt.Errorf("缺少权限: %s", s)
		}
	}
	return nil
}

// base64URLDecode 对不带填充的 URL 安全 Base64 字符串做补齐并解码
func base64URLDecode(s string) ([]byte, error) {
	if l := len(s) % 4; l != 0 {
		// JWT 中的 Base64URL 编码可以省略 '='，这里按长度补齐
		s += strings.Repeat("=", 4-l)
	}
	return base64.URLEncoding.DecodeString(s)
}

// DecodeJWT 手工验证 HS256 JWT 的签名与过期时间，并返回载荷
func DecodeJWT(token string, secret string) (map[string]interface{}, error) {
	// JWT 由三部分组成：header.payload.signature
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, fmt.Errorf("令牌格式无效")
	}
	headerB64, payloadB64, signatureB64 := parts[0], parts[1], parts[2]

	// 解码并解析 header
	headerBytes, err := base64URLDecode(headerB64)
	if err != nil {
		return nil, fmt.Errorf("解析令牌头失败")
	}
	var header map[string]interface{}
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return nil, fmt.Errorf("解析令牌头 JSON 失败")
	}

	// 仅支持 HS256 算法
	alg, _ := header["alg"].(string)
	if alg != "HS256" {
		return nil, fmt.Errorf("不支持的签名算法")
	}

	// 使用 secret 重新计算签名，并与令牌中的签名做对比
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(headerB64 + "." + payloadB64))
	expected := mac.Sum(nil)
	expectedB64 := base64.RawURLEncoding.EncodeToString(expected)

	if !hmac.Equal([]byte(expectedB64), []byte(signatureB64)) {
		return nil, fmt.Errorf("令牌签名无效")
	}

	// 解码并解析 payload
	payloadBytes, err := base64URLDecode(payloadB64)
	if err != nil {
		return nil, fmt.Errorf("解析令牌载荷失败")
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return nil, fmt.Errorf("解析令牌载荷 JSON 失败")
	}

	// 校验 exp 过期时间，允许不同 JSON 类型
	if expRaw, ok := payload["exp"]; ok {
		var exp int64
		switch v := expRaw.(type) {
		case float64:
			exp = int64(v)
		case int64:
			exp = v
		case json.Number:
			n, err := v.Int64()
			if err != nil {
				return nil, fmt.Errorf("令牌过期时间无效")
			}
			exp = n
		default:
			return nil, fmt.Errorf("令牌过期时间无效")
		}
		now := time.Now().Unix()
		if now >= exp {
			return nil, fmt.Errorf("令牌已过期")
		}
	}

	return payload, nil
}

// IdentityFromToken 从 JWT 中提取应用名称和权限范围（scopes）
func IdentityFromToken(token string, secret string) (AppIdentity, error) {
	payload, err := DecodeJWT(token, secret)
	if err != nil {
		return AppIdentity{}, err
	}

	// 优先从 app_name 字段读取应用名；若为空则回退到标准的 sub 字段
	appName, _ := payload["app_name"].(string)
	if appName == "" {
		if v, ok := payload["sub"].(string); ok {
			appName = v
		}
	}
	if appName == "" {
		return AppIdentity{}, fmt.Errorf("令牌中缺少 app_name")
	}

	// scopes 支持多种格式：空格分隔字符串或数组，并兼容 scope / scopes 两种命名
	scopes := []string{}
	if raw, ok := payload["scopes"]; ok {
		switch v := raw.(type) {
		case string:
			for _, s := range strings.Split(v, " ") {
				if s != "" {
					scopes = append(scopes, s)
				}
			}
		case []interface{}:
			for _, s := range v {
				scopes = append(scopes, fmt.Sprint(s))
			}
		}
	} else if raw, ok := payload["scope"]; ok {
		switch v := raw.(type) {
		case string:
			for _, s := range strings.Split(v, " ") {
				if s != "" {
					scopes = append(scopes, s)
				}
			}
		case []interface{}:
			for _, s := range v {
				scopes = append(scopes, fmt.Sprint(s))
			}
		}
	}

	jti, _ := payload["jti"].(string)
	if jti == "" {
		return AppIdentity{}, fmt.Errorf("令牌中缺少 jti")
	}

	return AppIdentity{
		AppName: appName,
		Scopes:  scopes,
		JTI:     jti,
	}, nil
}
