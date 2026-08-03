import pytest

from conftest import _test_database_url


def test_database_url_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("TEST_PG_CONN_STRING", raising=False)

    with pytest.raises(pytest.skip.Exception, match="TEST_PG_CONN_STRING"):
        _test_database_url()


def test_database_url_rejects_non_test_database(monkeypatch):
    monkeypatch.setenv(
        "TEST_PG_CONN_STRING",
        "postgresql://postgres:secret@127.0.0.1:5432/contest",
    )

    with pytest.raises(pytest.fail.Exception, match="必须包含独立的 'test' 段"):
        _test_database_url()


def test_database_url_accepts_isolated_test_database(monkeypatch):
    monkeypatch.setenv(
        "TEST_PG_CONN_STRING",
        "postgresql://postgres:secret@127.0.0.1:5432/unidata_test",
    )

    assert _test_database_url() == (
        "postgresql+asyncpg://postgres:secret@127.0.0.1:5432/unidata_test"
    )
