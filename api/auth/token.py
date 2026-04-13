"""Verify Auth0 RS256 JWT tokens using JWKS."""

import httpx
from jose import jwt, JWTError
from functools import lru_cache

from api.auth.config import (
    AUTH0_ALGORITHMS,
    AUTH0_API_AUDIENCE,
    AUTH0_ISSUER,
    AUTH0_JWKS_URL,
)


class TokenError(Exception):
    """Raised when token verification fails."""
    def __init__(self, detail: str):
        self.detail = detail


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch and cache Auth0 JWKS (JSON Web Key Set)."""
    resp = httpx.get(AUTH0_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_signing_key(token: str) -> dict:
    """Extract the signing key from JWKS that matches the token's kid."""
    jwks = _fetch_jwks()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise TokenError("Invalid token header")

    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header.get("kid"):
            return key

    raise TokenError("Signing key not found in JWKS")


def verify_token(token: str) -> dict:
    """Verify an Auth0 JWT and return the decoded payload."""
    signing_key = _get_signing_key(token)

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=AUTH0_ALGORITHMS,
            audience=AUTH0_API_AUDIENCE,
            issuer=AUTH0_ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.JWTClaimsError:
        raise TokenError("Invalid token claims")
    except JWTError:
        raise TokenError("Token verification failed")

    return payload


def decode_token_unsafe(token: str) -> dict:
    """Decode a JWT WITHOUT verification — for testing/dev only."""
    return jwt.get_unverified_claims(token)
