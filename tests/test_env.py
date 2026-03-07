from dokployctl.env import build_env_from_compose, extract_env_vars


def test_extract_env_vars():
    compose = "image: ${IMAGE_TAG}\npassword: ${DB_PASS}"
    assert extract_env_vars(compose) == ["DB_PASS", "IMAGE_TAG"]


def test_extract_env_vars_empty():
    assert extract_env_vars("image: nginx:latest") == []


def test_build_env_from_compose(monkeypatch):
    monkeypatch.setenv("IMAGE_TAG", "main-abc1234")
    monkeypatch.setenv("DB_PASS", "secret")
    result = build_env_from_compose("image: ${IMAGE_TAG}\ndb: ${DB_PASS}")
    assert "DB_PASS=secret" in result
    assert "IMAGE_TAG=main-abc1234" in result


def test_build_env_missing_var(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    import pytest

    with pytest.raises(SystemExit):
        build_env_from_compose("val: ${MISSING_VAR}")
