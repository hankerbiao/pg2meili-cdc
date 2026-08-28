package config

import (
	"strings"
	"testing"
)

func TestLoadConfigDerivesConsumerGroupFromRegion(t *testing.T) {
	t.Setenv("KAFKA_BROKERS", "localhost:9092")
	t.Setenv("MEILI_HOST", "http://localhost:7700")
	t.Setenv("UNIDATA_URL", "http://unidata.test")
	t.Setenv("AGENT_REGISTRATION_TOKEN", "agent-secret")
	t.Setenv("REGION_ID", "cn-north-1")
	t.Setenv("KAFKA_GROUP_PREFIX", "meili-sync")
	t.Setenv("KAFKA_GROUP_ID", "")

	cfg := LoadConfig()
	if cfg.GroupID != "meili-sync-cn-north-1" {
		t.Fatalf("unexpected consumer group: %q", cfg.GroupID)
	}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	if !cfg.MeiliBatchEnabled || cfg.MeiliBatchSize != 100 || cfg.MeiliBatchFlushMS != 100 || cfg.MeiliBatchMaxBytes != 5242880 {
		t.Fatalf("unexpected batch defaults: %+v", cfg)
	}
}

func TestValidateRejectsInvalidBatchConfig(t *testing.T) {
	cfg := AppConfig{
		Brokers:            []string{"localhost:9092"},
		MeiliHost:          "http://localhost:7700",
		GroupPrefix:        "meili-sync",
		GroupID:            "meili-sync",
		MeiliBatchSize:     0,
		MeiliBatchFlushMS:  100,
		MeiliBatchMaxBytes: 1024,
	}
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "MEILI_BATCH_SIZE") {
		t.Fatalf("Validate() error = %v, want MEILI_BATCH_SIZE", err)
	}
}

func TestConsumerGroupTopology(t *testing.T) {
	beijingPrimary := ConsumerGroupID("meili-sync", "beijing")
	beijingReplica := ConsumerGroupID("meili-sync", "beijing")
	shanghai := ConsumerGroupID("meili-sync", "shanghai")

	if beijingPrimary != beijingReplica {
		t.Fatalf("same-region replicas must share a group: %q != %q", beijingPrimary, beijingReplica)
	}
	if beijingPrimary == shanghai {
		t.Fatalf("different regions must use different groups: %q", beijingPrimary)
	}
}

func TestLoadConfigKeepsLegacyGroupWithoutRegion(t *testing.T) {
	t.Setenv("KAFKA_BROKERS", "localhost:9092")
	t.Setenv("MEILI_HOST", "http://localhost:7700")
	t.Setenv("UNIDATA_URL", "http://unidata.test")
	t.Setenv("AGENT_REGISTRATION_TOKEN", "agent-secret")
	t.Setenv("REGION_ID", "")
	t.Setenv("KAFKA_GROUP_PREFIX", "meili-sync")
	t.Setenv("KAFKA_GROUP_ID", "legacy-sync-group")

	cfg := LoadConfig()
	if cfg.GroupID != "legacy-sync-group" {
		t.Fatalf("unexpected legacy consumer group: %q", cfg.GroupID)
	}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestLoadConfigUsesPrefixAsLegacyDefaultGroup(t *testing.T) {
	t.Setenv("KAFKA_BROKERS", "localhost:9092")
	t.Setenv("MEILI_HOST", "http://localhost:7700")
	t.Setenv("UNIDATA_URL", "http://unidata.test")
	t.Setenv("AGENT_REGISTRATION_TOKEN", "agent-secret")
	t.Setenv("REGION_ID", "")
	t.Setenv("KAFKA_GROUP_PREFIX", "meili-sync")
	t.Setenv("KAFKA_GROUP_ID", "")

	cfg := LoadConfig()
	if cfg.GroupID != "meili-sync" {
		t.Fatalf("unexpected default consumer group: %q", cfg.GroupID)
	}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestValidateRejectsConflictingLegacyGroupID(t *testing.T) {
	cfg := AppConfig{
		Brokers:       []string{"localhost:9092"},
		MeiliHost:     "http://localhost:7700",
		RegionID:      "beijing",
		GroupPrefix:   "meili-sync",
		GroupID:       "meili-sync-beijing",
		legacyGroupID: "shared-across-all-regions",
	}

	err := cfg.Validate()
	if err == nil || !strings.Contains(err.Error(), "KAFKA_GROUP_ID") {
		t.Fatalf("Validate() error = %v, want legacy group conflict", err)
	}
}

func TestValidateAllowsMatchingLegacyGroupDuringMigration(t *testing.T) {
	cfg := AppConfig{
		Brokers:            []string{"localhost:9092"},
		MeiliHost:          "http://localhost:7700",
		RegionID:           "beijing",
		GroupPrefix:        "meili-sync",
		GroupID:            "meili-sync-beijing",
		legacyGroupID:      "meili-sync-beijing",
		MeiliBatchSize:     100,
		MeiliBatchFlushMS:  100,
		MeiliBatchMaxBytes: 1024,
	}

	if err := cfg.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestValidateRequiresAgentRegistrationToken(t *testing.T) {
	cfg := AppConfig{
		Brokers:     []string{"localhost:9092"},
		MeiliHost:   "http://localhost:7700",
		RegionID:    "beijing",
		GroupPrefix: "meili-sync",
		GroupID:     "meili-sync-beijing",
		UniDataURL:  "http://unidata.test",
	}

	err := cfg.Validate()
	if err == nil || !strings.Contains(err.Error(), "AGENT_REGISTRATION_TOKEN") {
		t.Fatalf("Validate() error = %v, want registration token error", err)
	}
}

func TestValidateRejectsEmptyBrokers(t *testing.T) {
	cfg := AppConfig{
		Brokers:     nil,
		MeiliHost:   "http://localhost:7700",
		GroupPrefix: "meili-sync",
		GroupID:     "meili-sync",
	}
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "KAFKA_BROKERS") {
		t.Fatalf("Validate() error = %v, want KAFKA_BROKERS error", err)
	}

	// splitAndTrim 过滤空项后也应为空
	cfg.Brokers = splitAndTrim(" , , ")
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "KAFKA_BROKERS") {
		t.Fatalf("Validate() error = %v, want KAFKA_BROKERS error for whitespace-only input", err)
	}
}

func TestValidateRejectsEmptyMeiliHost(t *testing.T) {
	cfg := AppConfig{
		Brokers:     []string{"localhost:9092"},
		MeiliHost:   "",
		GroupPrefix: "meili-sync",
		GroupID:     "meili-sync",
	}
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "MEILI_HOST") {
		t.Fatalf("Validate() error = %v, want MEILI_HOST error", err)
	}
}

func TestValidateRejectsMalformedMeiliHost(t *testing.T) {
	cfg := AppConfig{
		Brokers:     []string{"localhost:9092"},
		MeiliHost:   "localhost:7700",
		GroupPrefix: "meili-sync",
		GroupID:     "meili-sync",
	}
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "http://") {
		t.Fatalf("Validate() error = %v, want scheme error", err)
	}
}

func TestSplitAndTrimFiltersEmptyEntries(t *testing.T) {
	got := splitAndTrim(" host1:9092 , ,host2:9092, ")
	want := []string{"host1:9092", "host2:9092"}
	if len(got) != len(want) {
		t.Fatalf("splitAndTrim() = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("splitAndTrim()[%d] = %q, want %q", i, got[i], want[i])
		}
	}

	if result := splitAndTrim(""); len(result) != 0 {
		t.Fatalf("splitAndTrim(\"\") = %v, want empty", result)
	}
}
