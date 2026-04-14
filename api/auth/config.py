# api/auth/config.py
"""Auth0 configuration — loaded from environment variables."""

import os

APP_ENV = os.getenv("APP_ENV", "development")

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE", "")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_REDIRECT_URI = os.getenv("AUTH0_REDIRECT_URI", "http://localhost:3000/")
AUTH0_ALGORITHMS = ["RS256"]
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"
AUTH0_JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
