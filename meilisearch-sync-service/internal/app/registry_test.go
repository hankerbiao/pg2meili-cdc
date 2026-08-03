package app

import (
	"reflect"
	"testing"

	"meilisearch-sync-service/internal/apikey"
	"meilisearch-sync-service/internal/service"
)

func TestUniqueTopics(t *testing.T) {
	topics := Topics{
		CDC:     []string{"cdc-a", "", "cdc-a", "cdc-b"},
		Command: "commands",
		APIKey:  "api-keys",
	}

	want := []string{"cdc-a", "cdc-b", "commands", "api-keys"}
	if got := uniqueTopics(topics); !reflect.DeepEqual(got, want) {
		t.Fatalf("uniqueTopics() = %v, want %v", got, want)
	}
}

func TestBuildHandlers(t *testing.T) {
	registry := &apikey.Registry{}
	handlers := BuildHandlers(Topics{
		CDC:     []string{"cdc"},
		Command: "commands",
		APIKey:  "api-keys",
	}, nil, registry)

	tests := []struct {
		topic string
		want  any
	}{
		{topic: "cdc", want: service.DebeziumHandler{}},
		{topic: "commands", want: service.MeiliCommandHandler{}},
		{topic: "api-keys", want: service.APIKeyEventHandler{}},
	}
	for _, tt := range tests {
		if got := handlers[tt.topic]; reflect.TypeOf(got) != reflect.TypeOf(tt.want) {
			t.Errorf("handler for %q has type %T, want %T", tt.topic, got, tt.want)
		}
	}
}

func TestBuildHandlersRejectsDuplicateTopic(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("BuildHandlers() did not reject duplicate topic")
		}
	}()

	BuildHandlers(Topics{CDC: []string{"shared"}, Command: "shared"}, nil, nil)
}
