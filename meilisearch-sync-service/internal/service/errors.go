package service

import "errors"

type permanentError struct {
	err error
}

func (e permanentError) Error() string { return e.err.Error() }
func (e permanentError) Unwrap() error { return e.err }

func permanent(err error) error {
	if err == nil || isPermanent(err) {
		return err
	}
	return permanentError{err: err}
}

func isPermanent(err error) bool {
	var target permanentError
	return errors.As(err, &target)
}
