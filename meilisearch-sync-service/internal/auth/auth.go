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

type AppIdentity struct {
	AppName string
	Scopes  []string
}

func base64URLDecode(s string) ([]byte, error) {
	if l := len(s) % 4; l != 0 {
		s += strings.Repeat("=", 4-l)
	}
	return base64.URLEncoding.DecodeString(s)
}

func DecodeJWT(token string, secret string) (map[string]interface{}, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, fmt.Errorf("令牌格式无效")
	}
	headerB64, payloadB64, signatureB64 := parts[0], parts[1], parts[2]

	headerBytes, err := base64URLDecode(headerB64)
	if err != nil {
		return nil, fmt.Errorf("解析令牌头失败")
	}
	var header map[string]interface{}
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return nil, fmt.Errorf("解析令牌头 JSON 失败")
	}

	alg, _ := header["alg"].(string)
	if alg != "HS256" {
		return nil, fmt.Errorf("不支持的签名算法")
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(headerB64 + "." + payloadB64))
	expected := mac.Sum(nil)
	expectedB64 := base64.RawURLEncoding.EncodeToString(expected)

	if !hmac.Equal([]byte(expectedB64), []byte(signatureB64)) {
		return nil, fmt.Errorf("令牌签名无效")
	}

	payloadBytes, err := base64URLDecode(payloadB64)
	if err != nil {
		return nil, fmt.Errorf("解析令牌载荷失败")
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return nil, fmt.Errorf("解析令牌载荷 JSON 失败")
	}

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

func IdentityFromToken(token string, secret string) (AppIdentity, error) {
	payload, err := DecodeJWT(token, secret)
	if err != nil {
		return AppIdentity{}, err
	}

	appName, _ := payload["app_name"].(string)
	if appName == "" {
		if v, ok := payload["sub"].(string); ok {
			appName = v
		}
	}
	if appName == "" {
		return AppIdentity{}, fmt.Errorf("令牌中缺少 app_name")
	}

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

	return AppIdentity{
		AppName: appName,
		Scopes:  scopes,
	}, nil
}
