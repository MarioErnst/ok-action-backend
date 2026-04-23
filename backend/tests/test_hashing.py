from app.infrastructure.security.hashing import hash_password, verify_password


def test_hash_password_returns_bcrypt_hash():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("password123")
    assert verify_password("password123", hashed) is True


def test_verify_password_incorrect():
    hashed = hash_password("password123")
    assert verify_password("wrong", hashed) is False
