"""Verify Auth0 RS256 JWT tokens using JWKS."""

import time
import httpx
from jose import jwt, JWTError
from cachetools import TTLCache

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


_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
_JWKS_CACHE_KEY = "jwks"


def _fetch_jwks() -> dict:
    """Fetch Auth0 JWKS with 1-hour TTL cache."""
    cached = _jwks_cache.get(_JWKS_CACHE_KEY)
    if cached is not None:
        return cached
    resp = httpx.get(AUTH0_JWKS_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _jwks_cache[_JWKS_CACHE_KEY] = data
    return data


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
