package apikey

import (
	"errors"
	"testing"
)

func TestPermanentErrorClassification(t *testing.T) {
	sentinel := errors.New("invalid event")
	marked := permanent(sentinel)
	if !IsPermanent(marked) {
		t.Fatal("permanent() error was not classified as permanent")
	}
	if !errors.Is(marked, sentinel) {
		t.Fatal("permanent() error did not preserve its cause")
	}
	if IsPermanent(sentinel) {
		t.Fatal("ordinary errors must remain retryable")
	}
}
