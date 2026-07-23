from collections.abc import Mapping
from typing import Any

import jwt
from jwt import PyJWKClient

GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_AUDIENCE = "pulseops-api"
EXPECTED_REPOSITORY = "franarredondom/PulseOps"
EXPECTED_REF = "refs/heads/main"
EXPECTED_WORKFLOW_REF = (
    "franarredondom/PulseOps/.github/workflows/uptime-checks.yml@refs/heads/main"
)
ALLOWED_EVENTS = {"schedule", "workflow_dispatch"}

_jwks_client = PyJWKClient(f"{GITHUB_OIDC_ISSUER}/.well-known/jwks")


class GitHubOIDCError(ValueError):
    """Raised when a token was not issued for the PulseOps scheduler."""


def validate_github_claims(claims: Mapping[str, Any]) -> None:
    expected = {
        "repository": EXPECTED_REPOSITORY,
        "ref": EXPECTED_REF,
        "workflow_ref": EXPECTED_WORKFLOW_REF,
    }
    for claim, value in expected.items():
        if claims.get(claim) != value:
            raise GitHubOIDCError(f"Unexpected GitHub OIDC claim: {claim}")
    if claims.get("event_name") not in ALLOWED_EVENTS:
        raise GitHubOIDCError("Unexpected GitHub Actions event")


def verify_github_actions_token(token: str) -> Mapping[str, Any]:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=GITHUB_OIDC_AUDIENCE,
            issuer=GITHUB_OIDC_ISSUER,
            options={
                "require": [
                    "aud",
                    "exp",
                    "iat",
                    "iss",
                    "repository",
                    "ref",
                    "workflow_ref",
                    "event_name",
                ]
            },
        )
    except jwt.PyJWTError as error:
        raise GitHubOIDCError("Invalid GitHub Actions identity token") from error
    validate_github_claims(claims)
    return claims
