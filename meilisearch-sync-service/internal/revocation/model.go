package revocation

type RevocationEvent struct {
	Version int    `json:"version"`
	Event   string `json:"event"`
	AppName string `json:"app_name"`
	JTI     string `json:"jti"`
	Reason  string `json:"reason"`
	TS      int64  `json:"ts"`
}
