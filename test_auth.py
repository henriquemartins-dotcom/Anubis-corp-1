from app.auth import create_session_token, credentials_match, decode_session_token


def test_session_token_round_trip():
    token, created = create_session_token("admin", "test-secret", issued_at=1_700_000_000)
    decoded = decode_session_token(token, "test-secret", max_age_seconds=999_999_999)
    assert decoded == created


def test_session_token_rejects_tampering():
    token, _ = create_session_token("admin", "test-secret")
    payload, signature = token.split(".", 1)
    tampered = f"{payload[:-1]}A.{signature}"
    assert decode_session_token(tampered, "test-secret", max_age_seconds=3600) is None


def test_session_token_rejects_wrong_secret():
    token, _ = create_session_token("admin", "test-secret")
    assert decode_session_token(token, "other-secret", max_age_seconds=3600) is None


def test_credentials_match():
    assert credentials_match("admin", "safe-password", "admin", "safe-password")
    assert not credentials_match("admin", "wrong", "admin", "safe-password")
