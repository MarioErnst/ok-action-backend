from app.infrastructure.security.jwt import create_access_token, decode_access_token


def test_create_and_decode_token():
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


def test_decode_invalid_token():
    payload = decode_access_token("invalid.token.here")
    assert payload is None
