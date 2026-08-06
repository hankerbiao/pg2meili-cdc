package apikey

import "errors"

// permanentError marks an event that cannot succeed if retried unchanged.
type permanentError struct {
	err error
}

func (e permanentError) Error() string { return e.err.Error() }
func (e permanentError) Unwrap() error { return e.err }

func permanent(err error) error {
	if err == nil || IsPermanent(err) {
		return err
	}
	return permanentError{err: err}
}

// IsPermanent reports whether an event is safe to route to the DLQ.
func IsPermanent(err error) bool {
	var target permanentError
	return errors.As(err, &target)
}
