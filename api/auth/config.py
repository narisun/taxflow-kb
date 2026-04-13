# api/auth/config.py
"""Auth0 configuration — loaded from environment variables."""

import os

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "dev-whd0hxxsqq67rrq8.us.auth0.com")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE", "https://api.taxflow.ai")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "bQLgF5zoUZS0tO5V36PXd4Q6ohHzhUIE")
AUTH0_REDIRECT_URI = os.getenv("AUTH0_REDIRECT_URI", "http://localhost:3000/")
AUTH0_ALGORITHMS = ["RS256"]
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"
AUTH0_JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
