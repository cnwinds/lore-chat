import pytest
from pathlib import Path

from app.auth.passwords import hash_password, verify_password
from app.auth.store import AuthAlreadySetupError, AuthStore


def test_hash_and_verify_roundtrip():
    h = hash_password("secret-pass-1")
    assert h != "secret-pass-1"
    assert verify_password("secret-pass-1", h)
    assert not verify_password("wrong", h)


def test_auth_store_setup_and_verify(tmp_path: Path):
    store = AuthStore(tmp_path)
    assert store.is_setup_required() is True
    store.set_password("admin-pass-123")
    assert store.is_setup_required() is False
    assert (tmp_path / ".kb" / "auth.json").is_file()
    assert store.verify("admin-pass-123")
    assert not store.verify("nope")


def test_auth_store_rejects_second_setup(tmp_path: Path):
    store = AuthStore(tmp_path)
    store.set_password("admin-pass-123")
    with pytest.raises(AuthAlreadySetupError):
        store.set_password("other")


def test_change_password(tmp_path: Path):
    store = AuthStore(tmp_path)
    store.set_password("old-pass-1234")
    store.change_password("old-pass-1234", "new-pass-5678")
    assert store.verify("new-pass-5678")
    assert not store.verify("old-pass-1234")
