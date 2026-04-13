"""Tests for Auth0 JWT verification (unit tests with mocked JWKS)."""

import pytest
import time
import base64
from jose import jwt
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from api.auth.token import verify_token, decode_token_unsafe, TokenError


def _int_to_base64url(n: int) -> str:
    """Convert an integer to a base64url-encoded string (no padding)."""
    byte_length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()


# Generate a real RSA key pair for testing
_rsa_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_rsa_public = _rsa_private.public_key()
_priv_numbers = _rsa_private.private_numbers()
_pub_numbers = _rsa_public.public_numbers()

_TEST_KID = "test-kid-1"
_TEST_KEY = {
    "kty": "RSA",
    "kid": _TEST_KID,
    "n": _int_to_base64url(_pub_numbers.n),
    "e": _int_to_base64url(_pub_numbers.e),
    "d": _int_to_base64url(_priv_numbers.d),
    "p": _int_to_base64url(_priv_numbers.p),
    "q": _int_to_base64url(_priv_numbers.q),
    "dp": _int_to_base64url(_priv_numbers.dmp1),
    "dq": _int_to_base64url(_priv_numbers.dmq1),
    "qi": _int_to_base64url(_priv_numbers.iqmp),
}
_TEST_PUB = {"kty": "RSA", "kid": _TEST_KID, "n": _TEST_KEY["n"], "e": _TEST_KEY["e"]}


def _make_token(claims: dict) -> str:
    return jwt.encode(claims, _TEST_KEY, algorithm="RS256", headers={"kid": _TEST_KID})


def test_decode_token_unsafe():
    token = _make_token({"sub": "auth0|123", "email": "test@test.com"})
    payload = decode_token_unsafe(token)
    assert payload["sub"] == "auth0|123"
    assert payload["email"] == "test@test.com"


def test_verify_token_expired():
    token = _make_token({
        "sub": "auth0|123",
        "aud": "https://api.taxflow.ai",
        "iss": "https://dev-whd0hxxsqq67rrq8.us.auth0.com/",
        "exp": int(time.time()) - 3600,
    })
    with patch("api.auth.token._fetch_jwks", return_value={"keys": [_TEST_PUB]}):
        with pytest.raises(TokenError, match="expired"):
            verify_token(token)


def test_verify_token_bad_audience():
    token = _make_token({
        "sub": "auth0|123",
        "aud": "wrong-audience",
        "iss": "https://dev-whd0hxxsqq67rrq8.us.auth0.com/",
        "exp": int(time.time()) + 3600,
    })
    with patch("api.auth.token._fetch_jwks", return_value={"keys": [_TEST_PUB]}):
        with pytest.raises(TokenError, match="claims"):
            verify_token(token)
