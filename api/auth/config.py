# api/auth/config.py
"""Auth0 configuration — thin compatibility shim over :class:`api.config.Settings`.

Legacy modules import names directly from here (``APP_ENV``, ``AUTH0_DOMAIN``,
etc.). Those imports still work because they proxy through to the central
settings object at import time. New code should inject
:class:`api.config.Settings` via FastAPI ``Depends`` instead.
"""
from __future__ import annotations

from api.config import get_settings

_settings = get_settings()

APP_ENV = _settings.app_env
AUTH0_DOMAIN = _settings.auth0_domain
AUTH0_API_AUDIENCE = _settings.auth0_api_audience
AUTH0_CLIENT_ID = _settings.auth0_client_id
AUTH0_REDIRECT_URI = _settings.auth0_redirect_uri
AUTH0_ALGORITHMS = _settings.auth0_algorithms
AUTH0_ISSUER = _settings.auth0_issuer
AUTH0_JWKS_URL = _settings.auth0_jwks_url
