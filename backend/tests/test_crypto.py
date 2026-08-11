from app.crypto import decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_decrypt_roundtrip():
    plain = "sk-ant-abcdef1234567890"
    token = encrypt_secret(plain)
    assert token != plain
    assert decrypt_secret(token) == plain


def test_encrypt_empty_string():
    assert encrypt_secret("") == ""


def test_decrypt_empty_string():
    assert decrypt_secret("") == ""


def test_decrypt_invalid_token_returns_empty():
    assert decrypt_secret("not-a-valid-fernet-token") == ""


def test_mask_secret_short():
    assert mask_secret("") == ""
    assert mask_secret("abc") == "•••"


def test_mask_secret_long_keeps_head_and_tail():
    masked = mask_secret("sk-ant-abcdef1234567890")
    assert masked.startswith("sk-a")
    assert masked.endswith("7890")
    assert "•" in masked
